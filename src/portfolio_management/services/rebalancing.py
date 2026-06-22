from __future__ import annotations

from decimal import Decimal

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from portfolio_management.db.models import Account, AccountStrategy, AssetClass, Broker, Strategy
from portfolio_management.db.session import get_session_factory
from portfolio_management.services.accounts import account_choices, parse_choice_id
from portfolio_management.services.analytics import LIVE_MODE, current_positions


def create_target_allocation(
    account_choice: str | int | None,
    asset_class: str,
    target_weight_percent: str,
) -> str:
    account_id = parse_choice_id(account_choice)
    if account_id is None:
        raise ValueError("Account is required.")

    target_weight = Decimal(str(target_weight_percent).strip()) / Decimal("100")
    if target_weight < 0 or target_weight > 1:
        raise ValueError("Target weight must be between 0 and 100.")

    asset_class = AssetClass(asset_class).value
    session_factory = get_session_factory()
    with session_factory() as session:
        account = session.get(Account, account_id)
        if account is None:
            raise ValueError(f"Account id {account_id} does not exist.")
        strategy = get_or_create_strategy(session, asset_class)
        account_strategy = session.get(
            AccountStrategy,
            {"account_id": account.id, "strategy_id": strategy.id},
        )
        if account_strategy is None:
            account_strategy = AccountStrategy(
                account=account,
                strategy=strategy,
                allocation_weight=target_weight,
            )
            session.add(account_strategy)
        else:
            account_strategy.allocation_weight = target_weight
        session.commit()

    return f"Set {asset_class} target to {target_weight_percent}%."


def get_or_create_strategy(session: Session, name: str) -> Strategy:
    strategy = session.scalar(select(Strategy).where(Strategy.name == name))
    if strategy is None:
        strategy = Strategy(name=name, description=f"Target allocation for {name}.")
        session.add(strategy)
        session.flush()
    return strategy


def target_allocations(account_choice: str | int | None) -> pd.DataFrame:
    account_id = parse_choice_id(account_choice)
    if account_id is None:
        return _target_dataframe([])

    session_factory = get_session_factory()
    with session_factory() as session:
        rows = session.execute(
            select(AccountStrategy, Strategy)
            .join(AccountStrategy.strategy)
            .where(AccountStrategy.account_id == account_id)
            .order_by(Strategy.name)
        ).all()

    return _target_dataframe(
        [
            {
                "Asset Class": strategy.name,
                "Target %": str(account_strategy.allocation_weight * Decimal("100")),
            }
            for account_strategy, strategy in rows
        ]
    )


def rebalance_report(
    account_choice: str | int | None,
    account_mode: str = LIVE_MODE,
) -> pd.DataFrame:
    account_id = parse_choice_id(account_choice)
    if account_id is None:
        return _rebalance_dataframe([])

    session_factory = get_session_factory()
    with session_factory() as session:
        account = session.get(Account, account_id)
        if account is None:
            return _rebalance_dataframe([])
        broker_name = account.broker.name
        account_name = account.name
        target_rows = session.execute(
            select(AccountStrategy, Strategy)
            .join(AccountStrategy.strategy)
            .where(AccountStrategy.account_id == account.id)
        ).all()

    positions = current_positions(account_mode=account_mode)
    if positions.empty:
        total_value = Decimal("0")
        actual_by_asset_class: dict[str, Decimal] = {}
    else:
        account_positions = positions[
            (positions["Broker"] == broker_name) & (positions["Account"] == account_name)
        ]
        actual_by_asset_class = {
            str(asset_class): sum(_to_decimal(value) for value in rows["Market Value"])
            for asset_class, rows in account_positions.groupby("Asset Class")
        }
        total_value = sum(actual_by_asset_class.values(), Decimal("0"))

    target_by_asset_class = {
        strategy.name: account_strategy.allocation_weight
        for account_strategy, strategy in target_rows
    }
    asset_classes = sorted(set(actual_by_asset_class) | set(target_by_asset_class))

    records = []
    for asset_class in asset_classes:
        current_value = actual_by_asset_class.get(asset_class, Decimal("0"))
        actual_weight = current_value / total_value if total_value else Decimal("0")
        target_weight = target_by_asset_class.get(asset_class, Decimal("0"))
        drift = actual_weight - target_weight
        target_value = total_value * target_weight
        trade_value = target_value - current_value
        if trade_value > 0:
            action = "BUY"
        elif trade_value < 0:
            action = "SELL"
        else:
            action = "HOLD"

        records.append(
            {
                "Asset Class": asset_class,
                "Current Value": str(current_value),
                "Actual %": str(actual_weight * Decimal("100")),
                "Target %": str(target_weight * Decimal("100")),
                "Drift %": str(drift * Decimal("100")),
                "Action": action,
                "Trade Value": str(abs(trade_value)),
            }
        )

    return _rebalance_dataframe(records)


def default_rebalance_account_choice() -> str | None:
    choices = account_choices(include_simulated=True)
    return choices[0] if choices else None


def _target_dataframe(records: list[dict[str, str]]) -> pd.DataFrame:
    return pd.DataFrame(records, columns=["Asset Class", "Target %"])


def _rebalance_dataframe(records: list[dict[str, str]]) -> pd.DataFrame:
    return pd.DataFrame(
        records,
        columns=[
            "Asset Class",
            "Current Value",
            "Actual %",
            "Target %",
            "Drift %",
            "Action",
            "Trade Value",
        ],
    )


def _to_decimal(value: object) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")
