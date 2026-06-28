from __future__ import annotations

import json
from datetime import UTC, datetime

import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from portfolio_management.db.models import Account, Broker, Portfolio, Transaction
from portfolio_management.db.session import get_session_factory


DEFAULT_PORTFOLIO_NAME = "Default Portfolio"
PORTFOLIO_GOAL_CHOICES = [
    "Capital Growth",
    "Income",
    "Capital Preservation",
    "Retirement",
    "Education",
    "House Purchase",
    "Emergency Reserve",
    "Inflation Protection",
    "Tax Efficiency",
    "Speculative Growth",
]
PORTFOLIO_GOAL_TYPE_CHOICES = [
    "Core",
    "Satellite",
    "Income",
    "Growth",
    "Balanced",
    "Defensive",
    "Speculative",
    "Tax Efficient",
]
PORTFOLIO_TIMELINE_CHOICES = [
    "0-1 years",
    "1-3 years",
    "3-5 years",
    "5-10 years",
    "10+ years",
]


def portfolio_goal_choices() -> list[str]:
    return PORTFOLIO_GOAL_CHOICES.copy()


def portfolio_goal_type_choices() -> list[str]:
    return PORTFOLIO_GOAL_TYPE_CHOICES.copy()


def portfolio_timeline_choices() -> list[str]:
    return PORTFOLIO_TIMELINE_CHOICES.copy()


def _serialize_goal_list(goals: list[str] | str | None) -> str | None:
    if goals is None:
        return None
    if isinstance(goals, str):
        values = [goals] if goals.strip() else []
    else:
        values = [str(goal).strip() for goal in goals if str(goal).strip()]
    cleaned = [goal for goal in values if goal in PORTFOLIO_GOAL_CHOICES]
    return json.dumps(cleaned) if cleaned else None


def _deserialize_goal_list(raw_goals: str | None) -> list[str]:
    if not raw_goals:
        return []
    try:
        values = json.loads(raw_goals)
    except json.JSONDecodeError:
        return [goal.strip() for goal in raw_goals.split(",") if goal.strip()]
    if not isinstance(values, list):
        return []
    return [str(goal) for goal in values if str(goal) in PORTFOLIO_GOAL_CHOICES]


def _clean_option(value: str | None, choices: list[str]) -> str | None:
    clean_value = (value or "").strip()
    if not clean_value:
        return None
    if clean_value not in choices:
        raise ValueError(f"Unsupported option '{clean_value}'.")
    return clean_value


def create_account(
    broker_name: str,
    account_name: str,
    currency_code: str,
    description: str = "",
    tax_wrapper_type: str = "",
    is_simulated: bool = False,
) -> str:
    if not broker_name.strip():
        raise ValueError("Broker is required.")
    if not account_name.strip():
        raise ValueError("Account is required.")

    session_factory = get_session_factory()
    with session_factory() as session:
        broker = get_or_create_broker(session, broker_name.strip())
        account = get_or_create_account(
            session=session,
            broker=broker,
            name=account_name.strip(),
            currency_code=currency_code.strip().upper() or "USD",
            description=description.strip() or None,
            tax_wrapper_type=tax_wrapper_type.strip() or None,
            is_simulated=bool(is_simulated),
        )
        session.commit()

    account_type = "TEST" if account.is_simulated else "REAL"
    return f"Created {account_type} account '{account.name}'."


def create_broker(
    broker_name: str,
    description: str = "",
) -> str:
    clean_name = (broker_name or "").strip()
    if not clean_name:
        raise ValueError("Broker is required.")

    session_factory = get_session_factory()
    with session_factory() as session:
        broker = get_or_create_broker(
            session,
            clean_name,
            description=(description or "").strip() or None,
        )
        broker.is_active = True
        session.commit()

    return f"Saved broker '{broker.name}'."


def update_broker(
    broker_choice: str | int | None,
    broker_name: str,
    description: str,
    is_active: bool,
) -> str:
    broker_id = parse_choice_id(broker_choice)
    if broker_id is None:
        raise ValueError("Broker is required.")

    clean_name = (broker_name or "").strip()
    if not clean_name:
        raise ValueError("Broker name is required.")

    session_factory = get_session_factory()
    with session_factory() as session:
        broker = session.get(Broker, broker_id)
        if broker is None:
            raise ValueError(f"Broker id {broker_id} does not exist.")

        duplicate = session.scalar(
            select(Broker).where(Broker.name == clean_name, Broker.id != broker_id)
        )
        if duplicate is not None:
            raise ValueError(f"Broker '{clean_name}' already exists.")

        broker.name = clean_name
        broker.description = (description or "").strip() or None
        broker.is_active = bool(is_active)
        session.commit()

    status = "enabled" if broker.is_active else "disabled"
    return f"Updated broker '{broker.name}' ({status})."


def delete_broker(broker_choice: str | int | None) -> str:
    broker_id = parse_choice_id(broker_choice)
    if broker_id is None:
        raise ValueError("Broker is required.")

    session_factory = get_session_factory()
    with session_factory() as session:
        broker = session.get(Broker, broker_id)
        if broker is None:
            raise ValueError(f"Broker id {broker_id} does not exist.")
        if broker.accounts:
            raise ValueError("Broker has accounts and cannot be removed.")
        broker_name = broker.name
        session.delete(broker)
        session.commit()

    return f"Deleted broker '{broker_name}'."


def create_portfolio(
    account_choice: str | int | None,
    portfolio_name: str,
    description: str = "",
    portfolio_url: str = "",
    portfolio_goals: list[str] | str | None = None,
    goal_type: str = "",
    goal_timeline: str = "",
) -> str:
    account_id = parse_choice_id(account_choice)
    if account_id is None:
        raise ValueError("Account is required.")
    if not portfolio_name.strip():
        raise ValueError("Portfolio is required.")

    session_factory = get_session_factory()
    with session_factory() as session:
        account = session.get(Account, account_id)
        if account is None:
            raise ValueError(f"Account id {account_id} does not exist.")
        portfolio = get_or_create_portfolio(
            session,
            account,
            portfolio_name.strip(),
            description=description.strip() or None,
            portfolio_url=portfolio_url.strip() or None,
            portfolio_goals=_serialize_goal_list(portfolio_goals),
            goal_type=_clean_option(goal_type, PORTFOLIO_GOAL_TYPE_CHOICES),
            goal_timeline=_clean_option(goal_timeline, PORTFOLIO_TIMELINE_CHOICES),
        )
        session.commit()

    return f"Created portfolio '{portfolio.name}' for account '{account.name}'."


def broker_choices(include_inactive: bool = False) -> list[str]:
    session_factory = get_session_factory()
    with session_factory() as session:
        statement = select(Broker).order_by(Broker.name)
        if not include_inactive:
            statement = statement.where(Broker.is_active.is_(True))
        rows = session.scalars(statement).all()
    return [_broker_label(broker, include_status=include_inactive) for broker in rows]


def broker_details(broker_choice: str | int | None) -> tuple[str, str, bool]:
    broker_id = parse_choice_id(broker_choice)
    if broker_id is None:
        return "", "", True

    session_factory = get_session_factory()
    with session_factory() as session:
        broker = session.get(Broker, broker_id)
        if broker is None:
            return "", "", True
        return broker.name, broker.description or "", bool(broker.is_active)


def create_account_with_portfolio(
    broker_name: str,
    account_name: str,
    currency_code: str,
    description: str = "",
    tax_wrapper_type: str = "",
    is_simulated: bool = False,
    portfolio_name: str = DEFAULT_PORTFOLIO_NAME,
    portfolio_description: str = "",
    portfolio_url: str = "",
) -> str:
    create_account(
        broker_name=broker_name,
        account_name=account_name,
        currency_code=currency_code,
        description=description,
        tax_wrapper_type=tax_wrapper_type,
        is_simulated=is_simulated,
    )
    return create_portfolio(
        account_choice=_find_account_choice(broker_name, account_name),
        portfolio_name=portfolio_name,
        description=portfolio_description,
        portfolio_url=portfolio_url,
    )


def account_description(account_choice: str | int | None) -> str:
    account_id = parse_choice_id(account_choice)
    if account_id is None:
        return ""

    session_factory = get_session_factory()
    with session_factory() as session:
        account = session.get(Account, account_id)
        if account is None:
            return ""
        return account.description or ""


def account_details(account_choice: str | int | None) -> tuple[str, str, str, str, str, bool, bool]:
    account_id = parse_choice_id(account_choice)
    if account_id is None:
        return "", "", "GBP", "", "", False, True

    session_factory = get_session_factory()
    with session_factory() as session:
        account = session.get(Account, account_id)
        if account is None:
            return "", "", "GBP", "", "", False, True
        return (
            account.broker.name,
            account.name,
            account.currency_code,
            account.description or "",
            account.tax_wrapper_type or "",
            bool(account.is_simulated),
            bool(account.is_active),
        )


def update_account_description(
    account_choice: str | int | None,
    description: str,
) -> str:
    account_id = parse_choice_id(account_choice)
    if account_id is None:
        raise ValueError("Account is required.")

    session_factory = get_session_factory()
    with session_factory() as session:
        account = session.get(Account, account_id)
        if account is None:
            raise ValueError(f"Account id {account_id} does not exist.")
        account.description = description.strip() or None
        session.commit()

    return f"Updated account description for '{account.name}'."


def update_account(
    account_choice: str | int | None,
    broker_name: str,
    account_name: str,
    currency_code: str,
    description: str,
    tax_wrapper_type: str,
    is_simulated: bool,
    is_active: bool,
) -> str:
    account_id = parse_choice_id(account_choice)
    if account_id is None:
        raise ValueError("Account is required.")

    clean_broker_name = (broker_name or "").strip()
    clean_account_name = (account_name or "").strip()
    clean_currency = (currency_code or "").strip().upper()
    if not clean_broker_name:
        raise ValueError("Broker is required.")
    if not clean_account_name:
        raise ValueError("Account name is required.")
    if not clean_currency:
        raise ValueError("Currency is required.")

    session_factory = get_session_factory()
    with session_factory() as session:
        account = session.get(Account, account_id)
        if account is None:
            raise ValueError(f"Account id {account_id} does not exist.")

        broker = get_or_create_broker(session, clean_broker_name)
        duplicate = session.scalar(
            select(Account).where(
                Account.id != account_id,
                Account.broker_id == broker.id,
                Account.name == clean_account_name,
            )
        )
        if duplicate is not None:
            raise ValueError(f"Account '{clean_account_name}' already exists for this broker.")

        account.broker = broker
        account.name = clean_account_name
        account.currency_code = clean_currency
        account.description = (description or "").strip() or None
        account.tax_wrapper_type = (tax_wrapper_type or "").strip() or None
        account.is_simulated = bool(is_simulated)
        account.is_active = bool(is_active)
        session.commit()

    status = "enabled" if account.is_active else "disabled"
    return f"Updated account '{account.name}' ({status})."


def portfolio_details(
    portfolio_choice: str | int | None,
) -> tuple[str, str, str, list[str], str, str, str, str, str, str, datetime | None, bool]:
    portfolio_id = parse_choice_id(portfolio_choice)
    if portfolio_id is None:
        return "", "", "", [], "", "", "", "", "", "", None, True

    session_factory = get_session_factory()
    with session_factory() as session:
        portfolio = session.get(Portfolio, portfolio_id)
        if portfolio is None:
            return "", "", "", [], "", "", "", "", "", "", None, True
        return (
            portfolio.name,
            portfolio.description or "",
            portfolio.portfolio_url or "",
            _deserialize_goal_list(portfolio.portfolio_goals),
            portfolio.goal_type or "",
            portfolio.goal_timeline or "",
            portfolio.rewritten_goals or "",
            portfolio.strategy_recommendation or "",
            portfolio.portfolio_profile or "",
            portfolio.ai_notes or "",
            portfolio.llm_updated_at,
            bool(portfolio.is_active),
        )


def update_portfolio(
    portfolio_choice: str | int | None,
    portfolio_name: str,
    description: str,
    portfolio_url: str,
    portfolio_goals: list[str] | str | None,
    goal_type: str,
    goal_timeline: str,
    is_active: bool,
) -> str:
    portfolio_id = parse_choice_id(portfolio_choice)
    if portfolio_id is None:
        raise ValueError("Portfolio is required.")

    clean_name = (portfolio_name or "").strip()
    if not clean_name:
        raise ValueError("Portfolio name is required.")

    session_factory = get_session_factory()
    with session_factory() as session:
        portfolio = session.get(Portfolio, portfolio_id)
        if portfolio is None:
            raise ValueError(f"Portfolio id {portfolio_id} does not exist.")

        duplicate = session.scalar(
            select(Portfolio).where(
                Portfolio.id != portfolio_id,
                Portfolio.account_id == portfolio.account_id,
                Portfolio.name == clean_name,
            )
        )
        if duplicate is not None:
            raise ValueError(
                f"Portfolio '{clean_name}' already exists for account '{portfolio.account.name}'."
            )

        portfolio.name = clean_name
        portfolio.description = (description or "").strip() or None
        portfolio.portfolio_url = (portfolio_url or "").strip() or None
        portfolio.portfolio_goals = _serialize_goal_list(portfolio_goals)
        portfolio.goal_type = _clean_option(goal_type, PORTFOLIO_GOAL_TYPE_CHOICES)
        portfolio.goal_timeline = _clean_option(goal_timeline, PORTFOLIO_TIMELINE_CHOICES)
        portfolio.is_active = bool(is_active)
        session.commit()

    status = "enabled" if portfolio.is_active else "disabled"
    return f"Updated portfolio '{portfolio.name}' ({status})."


def get_or_create_broker(
    session: Session,
    name: str,
    description: str | None = None,
) -> Broker:
    broker = session.scalar(select(Broker).where(Broker.name == name))
    if broker is None:
        broker = Broker(name=name, description=description, is_active=True)
        session.add(broker)
        session.flush()
    elif description and not broker.description:
        broker.description = description
    return broker


def get_or_create_account(
    session: Session,
    broker: Broker,
    name: str,
    currency_code: str,
    description: str | None = None,
    tax_wrapper_type: str | None = None,
    is_simulated: bool = False,
    is_active: bool = True,
) -> Account:
    account = session.scalar(
        select(Account).where(Account.broker_id == broker.id, Account.name == name)
    )
    if account is None:
        account = Account(
            broker=broker,
            name=name,
            description=description,
            currency_code=currency_code,
            tax_wrapper_type=tax_wrapper_type,
            is_simulated=is_simulated,
            is_active=is_active,
        )
        session.add(account)
        session.flush()
    return account


def get_or_create_portfolio(
    session: Session,
    account: Account,
    name: str = DEFAULT_PORTFOLIO_NAME,
    description: str | None = None,
    portfolio_url: str | None = None,
    portfolio_goals: str | None = None,
    goal_type: str | None = None,
    goal_timeline: str | None = None,
    is_active: bool = True,
) -> Portfolio:
    portfolio = session.scalar(
        select(Portfolio).where(Portfolio.account_id == account.id, Portfolio.name == name)
    )
    if portfolio is None:
        portfolio = Portfolio(
            account=account,
            name=name,
            description=description,
            portfolio_url=portfolio_url,
            portfolio_goals=portfolio_goals,
            goal_type=goal_type,
            goal_timeline=goal_timeline,
            is_active=is_active,
        )
        session.add(portfolio)
        session.flush()
    else:
        if description and not portfolio.description:
            portfolio.description = description
        if portfolio_url and not portfolio.portfolio_url:
            portfolio.portfolio_url = portfolio_url
        if portfolio_goals and not portfolio.portfolio_goals:
            portfolio.portfolio_goals = portfolio_goals
        if goal_type and not portfolio.goal_type:
            portfolio.goal_type = goal_type
        if goal_timeline and not portfolio.goal_timeline:
            portfolio.goal_timeline = goal_timeline
    return portfolio


def account_choices(
    include_simulated: bool = True,
    include_inactive: bool = False,
    account_mode: str | None = None,
) -> list[str]:
    from portfolio_management.services.analytics import LIVE_MODE, SANDBOX_MODE

    session_factory = get_session_factory()
    with session_factory() as session:
        statement = (
            select(Account, Broker)
            .join(Account.broker)
            .order_by(Broker.name, Account.name)
        )
        if account_mode == SANDBOX_MODE:
            statement = statement.where(Account.is_simulated.is_(True))
        elif account_mode == LIVE_MODE or not include_simulated:
            statement = statement.where(Account.is_simulated.is_(False))
        if not include_inactive:
            statement = statement.where(Account.is_active.is_(True), Broker.is_active.is_(True))
        rows = session.execute(statement).all()
    return [_account_label(account, broker, include_status=include_inactive) for account, broker in rows]


def list_brokers() -> pd.DataFrame:
    session_factory = get_session_factory()
    with session_factory() as session:
        rows = session.scalars(select(Broker).order_by(Broker.name)).all()

    return pd.DataFrame(
        [{"ID": broker.id, "Broker": broker.name} for broker in rows],
        columns=["ID", "Broker"],
    )


def list_brokers_detailed() -> pd.DataFrame:
    session_factory = get_session_factory()
    with session_factory() as session:
        rows = session.scalars(select(Broker).order_by(Broker.name)).all()

    return pd.DataFrame(
        [
            {
                "ID": broker.id,
                "Broker": broker.name,
                "Description": broker.description or "",
                "Active": "Yes" if broker.is_active else "No",
            }
            for broker in rows
        ],
        columns=["ID", "Broker", "Description", "Active"],
    )


def list_accounts(account_filter: str = "All") -> pd.DataFrame:
    session_factory = get_session_factory()
    with session_factory() as session:
        stmt = (
            select(Account, Broker)
            .join(Account.broker)
            .order_by(Broker.name, Account.name)
        )
        if account_filter == "Real":
            stmt = stmt.where(Account.is_simulated.is_(False))
        elif account_filter == "Test":
            stmt = stmt.where(Account.is_simulated.is_(True))
        rows = session.execute(stmt).all()

    return pd.DataFrame(
        [
            {
                "ID": account.id,
                "Broker": broker.name,
                "Account": account.name,
                "Description": account.description or "",
                "Currency": account.currency_code,
                "Tax Wrapper": account.tax_wrapper_type or "",
                "Simulated": "Yes" if account.is_simulated else "No",
                "Active": "Yes" if account.is_active else "No",
            }
            for account, broker in rows
        ],
        columns=[
            "ID",
            "Broker",
            "Account",
            "Description",
            "Currency",
            "Tax Wrapper",
            "Simulated",
            "Active",
        ],
    )


def list_portfolios(account_filter: str = "All", active_only: bool = True) -> pd.DataFrame:
    session_factory = get_session_factory()
    with session_factory() as session:
        stmt = (
            select(Portfolio, Account, Broker)
            .join(Portfolio.account)
            .join(Account.broker)
            .order_by(Broker.name, Account.name, Portfolio.name)
        )
        if account_filter == "Real":
            stmt = stmt.where(Account.is_simulated.is_(False))
        elif account_filter == "Test":
            stmt = stmt.where(Account.is_simulated.is_(True))
        if active_only:
            stmt = stmt.where(Portfolio.is_active.is_(True))
        rows = session.execute(stmt).all()

    return pd.DataFrame(
        [
            {
                "ID": portfolio.id,
                "Broker": broker.name,
                "Account": account.name,
                "Portfolio": portfolio.name,
                "Portfolio URL": portfolio.portfolio_url or "",
                "Description": portfolio.description or "",
                "Goals": ", ".join(_deserialize_goal_list(portfolio.portfolio_goals)),
                "Goal Type": portfolio.goal_type or "",
                "Timeline": portfolio.goal_timeline or "",
                "Rewritten Goals": portfolio.rewritten_goals or "",
                "Strategy Recommendation": portfolio.strategy_recommendation or "",
                "Currency": account.currency_code,
                "Simulated Account": "Yes" if account.is_simulated else "No",
                "Active": "Yes" if portfolio.is_active else "No",
            }
            for portfolio, account, broker in rows
        ],
        columns=[
            "ID",
            "Broker",
            "Account",
            "Portfolio",
            "Portfolio URL",
            "Description",
            "Goals",
            "Goal Type",
            "Timeline",
            "Rewritten Goals",
            "Strategy Recommendation",
            "Currency",
            "Simulated Account",
            "Active",
        ],
    )


def store_portfolio_recommendation(
    portfolio_choice: str | int | None,
    rewritten_goals: str,
    strategy_recommendation: str,
    portfolio_profile: str = "",
    ai_notes: str = "",
) -> str:
    portfolio_id = parse_choice_id(portfolio_choice)
    if portfolio_id is None:
        raise ValueError("Portfolio is required.")

    session_factory = get_session_factory()
    with session_factory() as session:
        portfolio = session.get(Portfolio, portfolio_id)
        if portfolio is None:
            raise ValueError(f"Portfolio id {portfolio_id} does not exist.")
        portfolio.rewritten_goals = (rewritten_goals or "").strip() or None
        portfolio.strategy_recommendation = (strategy_recommendation or "").strip() or None
        portfolio.portfolio_profile = (portfolio_profile or "").strip() or None
        portfolio.ai_notes = (ai_notes or "").strip() or None
        portfolio.llm_updated_at = datetime.now(UTC)
        session.commit()

    return f"Stored AI insights for portfolio '{portfolio.name}'."


def portfolio_choices_for_account(
    account_choice: str | int | None,
    include_inactive: bool = False,
) -> list[str]:
    account_id = parse_choice_id(account_choice)
    if account_id is None:
        return []

    session_factory = get_session_factory()
    with session_factory() as session:
        statement = select(Portfolio).where(Portfolio.account_id == account_id)
        if not include_inactive:
            statement = statement.where(Portfolio.is_active.is_(True))
        rows = session.scalars(statement.order_by(Portfolio.name)).all()
    return [_portfolio_label(portfolio, include_status=include_inactive) for portfolio in rows]


def default_account_choice() -> str | None:
    choices = account_choices(include_simulated=True, include_inactive=False)
    return choices[0] if choices else None


def default_portfolio_choice(account_choice: str | int | None) -> str | None:
    choices = portfolio_choices_for_account(account_choice)
    return choices[0] if choices else None


def parse_choice_id(choice: str | int | None) -> int | None:
    if choice is None or choice == "":
        return None
    if isinstance(choice, int):
        return choice
    raw_id = str(choice).split("|", maxsplit=1)[0].strip()
    return int(raw_id) if raw_id else None


def _account_label(
    account: Account,
    broker: Broker,
    include_status: bool = False,
) -> str:
    badge = " [TEST]" if account.is_simulated else ""
    active = " [DISABLED]" if include_status and not account.is_active else ""
    wrapper = f" ({account.tax_wrapper_type})" if account.tax_wrapper_type else ""
    return f"{account.id} | {broker.name} / {account.name}{wrapper}{badge}{active}"


def _portfolio_label(portfolio: Portfolio, include_status: bool = False) -> str:
    active = " [DISABLED]" if include_status and not portfolio.is_active else ""
    return f"{portfolio.id} | {portfolio.name}{active}"


def _broker_label(broker: Broker, include_status: bool = False) -> str:
    active = " [DISABLED]" if include_status and not broker.is_active else ""
    return f"{broker.id} | {broker.name}{active}"


def _find_account_choice(broker_name: str, account_name: str) -> str:
    for choice in account_choices(include_simulated=True):
        if f"{broker_name.strip()} / {account_name.strip()}" in choice:
            return choice
    raise ValueError(f"Account '{account_name}' does not exist.")


def list_portfolios_with_transactions() -> pd.DataFrame:
    """Return all portfolios that have NO transactions, for preview before deletion."""
    session_factory = get_session_factory()
    with session_factory() as session:
        rows = session.execute(
            select(Portfolio, Account, Broker)
            .join(Portfolio.account)
            .join(Account.broker)
            .where(
                Portfolio.id.not_in(
                    select(Transaction.portfolio_id).distinct()
                )
            )
            .order_by(Broker.name, Account.name, Portfolio.name)
        ).all()
    return pd.DataFrame(
        [
            {
                "ID": portfolio.id,
                "Broker": broker.name,
                "Account": account.name,
                "Portfolio": portfolio.name,
                "Active": "Yes" if portfolio.is_active else "No",
            }
            for portfolio, account, broker in rows
        ],
        columns=["ID", "Broker", "Account", "Portfolio", "Active"],
    )


def delete_portfolios_with_transactions() -> tuple[int, int]:
    """Delete all portfolios that have NO transactions.

    Returns (portfolios_deleted, transactions_deleted) — transactions_deleted will always be 0.
    """
    session_factory = get_session_factory()
    with session_factory() as session:
        portfolio_ids = list(
            session.scalars(
                select(Portfolio.id).where(
                    Portfolio.id.not_in(
                        select(Transaction.portfolio_id).distinct()
                    )
                )
            ).all()
        )
        if not portfolio_ids:
            return 0, 0
        port_result = session.execute(
            delete(Portfolio).where(Portfolio.id.in_(portfolio_ids))
        )
        session.commit()
    return int(port_result.rowcount or 0), 0

