from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from tempfile import NamedTemporaryFile

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from portfolio_management.db.models import (
    Account,
    Broker,
    FxRateHistory,
    Portfolio,
    PriceHistory,
    Security,
    Transaction,
    TransactionType,
)
from portfolio_management.db.session import get_session_factory

LIVE_MODE = "Live Mode"
SANDBOX_MODE = "Sandbox Mode"


@dataclass
class Lot:
    quantity: Decimal
    unit_cost: Decimal
    acquired_date: date


def current_positions(
    include_simulated: bool = False,
    account_mode: str = LIVE_MODE,
    reporting_currency: str | None = None,
    as_of_date: date | None = None,
) -> pd.DataFrame:
    reporting_currency = reporting_currency.upper() if reporting_currency else None
    as_of_date = as_of_date or date.today()
    session_factory = get_session_factory()
    with session_factory() as session:
        rows = _load_transaction_rows(
            session,
            include_simulated=include_simulated,
            account_mode=account_mode,
        )
        records = _calculate_position_records(
            session,
            rows,
            reporting_currency=reporting_currency,
            as_of_date=as_of_date,
        )
    return pd.DataFrame(
        records,
        columns=[
            "Broker",
            "Account",
            "Portfolio",
            "Portfolio URL",
            "Ticker",
            "Name",
            "Asset Class",
            "Currency",
            "Reporting Currency",
            "Quantity",
            "Average Cost",
            "Latest Price",
            "Market Value",
            "Unrealized P&L",
        ],
    )


def realized_pnl_report(
    tax_year: int | None = None,
    include_simulated: bool = False,
    account_mode: str = LIVE_MODE,
) -> pd.DataFrame:
    session_factory = get_session_factory()
    with session_factory() as session:
        rows = _load_transaction_rows(
            session,
            include_simulated=include_simulated,
            account_mode=account_mode,
        )
    records = _calculate_realized_pnl_records(rows, tax_year=tax_year)
    return pd.DataFrame(
        records,
        columns=[
            "Date",
            "Broker",
            "Account",
            "Portfolio",
            "Ticker",
            "Quantity Sold",
            "Proceeds",
            "Cost Basis",
            "Realized P&L",
        ],
    )


def tax_prep_report(
    tax_year: int | None = None,
    account_mode: str = LIVE_MODE,
) -> pd.DataFrame:
    realized = realized_pnl_report(tax_year=tax_year, account_mode=account_mode)
    records = [
        {
            "Type": "REALIZED_GAIN",
            "Date": row["Date"],
            "Broker": row["Broker"],
            "Account": row["Account"],
            "Portfolio": row["Portfolio"],
            "Ticker": row["Ticker"],
            "Amount": row["Proceeds"],
            "Cost Basis": row["Cost Basis"],
            "Realized P&L": row["Realized P&L"],
        }
        for _, row in realized.iterrows()
    ]

    session_factory = get_session_factory()
    with session_factory() as session:
        rows = _load_transaction_rows(
            session,
            include_simulated=False,
            account_mode=account_mode,
        )

    for transaction, portfolio, account, broker, security in rows:
        if transaction.type != TransactionType.DIVIDEND:
            continue
        if tax_year is not None and transaction.date.year != tax_year:
            continue
        records.append(
            {
                "Type": "DIVIDEND",
                "Date": transaction.date.date().isoformat(),
                "Broker": broker.name,
                "Account": account.name,
                "Portfolio": portfolio.name,
                "Ticker": security.ticker if security else "",
                "Amount": str(transaction.total_value),
                "Cost Basis": "",
                "Realized P&L": "",
            }
        )

    return pd.DataFrame(
        records,
        columns=[
            "Type",
            "Date",
            "Broker",
            "Account",
            "Portfolio",
            "Ticker",
            "Amount",
            "Cost Basis",
            "Realized P&L",
        ],
    )


def export_tax_prep_report_csv(
    tax_year: int | None = None,
    account_mode: str = LIVE_MODE,
) -> str:
    report = tax_prep_report(tax_year=tax_year, account_mode=account_mode)
    with NamedTemporaryFile(
        mode="w",
        suffix=".csv",
        prefix="portfolio_tax_report_",
        delete=False,
        newline="",
    ) as file:
        report.to_csv(file.name, index=False)
        return str(Path(file.name))


def twr_curve(
    include_simulated: bool = False,
    account_mode: str = LIVE_MODE,
) -> pd.DataFrame:
    session_factory = get_session_factory()
    with session_factory() as session:
        rows = _load_transaction_rows(
            session,
            include_simulated=include_simulated,
            account_mode=account_mode,
        )
        if not rows:
            return pd.DataFrame(columns=["Date", "TWR"])
        start_date = min(transaction.date.date() for transaction, *_ in rows)
        end_date = date.today()
        values = _portfolio_values_by_day(session, rows, start_date, end_date)
        cash_flows = _external_cash_flows_by_day(rows)

    linked_return = Decimal("1")
    previous_value: Decimal | None = None
    records: list[dict[str, str]] = []

    current_date = start_date
    while current_date <= end_date:
        end_value = values.get(current_date, Decimal("0"))
        flow = cash_flows.get(current_date, Decimal("0"))

        if previous_value is not None and previous_value != 0:
            period_return = (end_value - flow - previous_value) / previous_value
            linked_return *= Decimal("1") + period_return

        records.append(
            {
                "Date": current_date.isoformat(),
                "TWR": str(linked_return - Decimal("1")),
            }
        )
        previous_value = end_value
        current_date += timedelta(days=1)

    return pd.DataFrame(records, columns=["Date", "TWR"])


def dashboard_summary(
    include_simulated: bool = False,
    account_mode: str = LIVE_MODE,
    reporting_currency: str | None = None,
    as_of_date: date | None = None,
) -> pd.DataFrame:
    positions = current_positions(
        include_simulated=include_simulated,
        account_mode=account_mode,
        reporting_currency=reporting_currency,
        as_of_date=as_of_date,
    )
    if positions.empty:
        total_market_value = Decimal("0")
        total_unrealized = Decimal("0")
    else:
        total_market_value = sum(_decimal_or_zero(value) for value in positions["Market Value"])
        total_unrealized = sum(_decimal_or_zero(value) for value in positions["Unrealized P&L"])

    return pd.DataFrame(
        [
            {
                "Metric": (
                    f"Global Market Value ({reporting_currency})"
                    if reporting_currency
                    else "Market Value"
                ),
                "Value": str(total_market_value),
            },
            {
                "Metric": (
                    f"Unrealized P&L ({reporting_currency})"
                    if reporting_currency
                    else "Unrealized P&L"
                ),
                "Value": str(total_unrealized),
            },
        ],
        columns=["Metric", "Value"],
    )


def allocation_by_asset_class(
    account_mode: str = LIVE_MODE,
    reporting_currency: str | None = None,
    as_of_date: date | None = None,
) -> pd.DataFrame:
    positions = current_positions(
        account_mode=account_mode,
        reporting_currency=reporting_currency,
        as_of_date=as_of_date,
    )
    if positions.empty:
        return pd.DataFrame(columns=["Asset Class", "Market Value"])
    rows = []
    for _, row in positions.iterrows():
        rows.append(
            {
                "Asset Class": row["Asset Class"],
                "Market Value": float(_decimal_or_zero(row["Market Value"])),
            }
        )
    return (
        pd.DataFrame(rows)
        .groupby("Asset Class", as_index=False)["Market Value"]
        .sum()
        .sort_values("Asset Class")
    )


def allocation_by_currency(
    account_mode: str = LIVE_MODE,
    reporting_currency: str | None = None,
    as_of_date: date | None = None,
) -> pd.DataFrame:
    positions = current_positions(
        account_mode=account_mode,
        reporting_currency=reporting_currency,
        as_of_date=as_of_date,
    )
    if positions.empty:
        return pd.DataFrame(columns=["Currency", "Market Value"])
    rows = [
        {
            "Currency": row["Currency"],
            "Market Value": float(_decimal_or_zero(row["Market Value"])),
        }
        for _, row in positions.iterrows()
    ]
    return (
        pd.DataFrame(rows)
        .groupby("Currency", as_index=False)["Market Value"]
        .sum()
        .sort_values("Currency")
    )


def _load_transaction_rows(
    session: Session,
    include_simulated: bool,
    account_mode: str = LIVE_MODE,
) -> list[tuple[Transaction, Portfolio, Account, Broker, Security | None]]:
    statement = (
        select(Transaction, Portfolio, Account, Broker, Security)
        .join(Transaction.portfolio)
        .join(Portfolio.account)
        .join(Account.broker)
        .join(Transaction.security, isouter=True)
        .where(Broker.is_active.is_(True))
        .where(Account.is_active.is_(True))
        .where(Portfolio.is_active.is_(True))
        .order_by(Transaction.date, Transaction.id)
    )
    if account_mode == SANDBOX_MODE:
        statement = statement.where(Account.is_simulated.is_(True))
    elif not include_simulated:
        statement = statement.where(Account.is_simulated.is_(False))
    return list(session.execute(statement).all())


def _calculate_position_records(
    session: Session,
    rows: list[tuple[Transaction, Portfolio, Account, Broker, Security | None]],
    reporting_currency: str | None = None,
    as_of_date: date | None = None,
) -> list[dict[str, str]]:
    as_of_date = as_of_date or date.today()
    security_state: dict[tuple[int, int], dict[str, object]] = {}
    cash_state: defaultdict[tuple[int, str], Decimal] = defaultdict(Decimal)

    for transaction, portfolio, account, broker, security in rows:
        if transaction.date.date() > as_of_date:
            continue
        if security is None:
            _apply_cash_transaction(cash_state, transaction, portfolio, account)
            continue

        key = (portfolio.id, security.id)
        state = security_state.setdefault(
            key,
            {
                "broker": broker,
                "account": account,
                "portfolio": portfolio,
                "security": security,
                "quantity": Decimal("0"),
                "cost_basis": Decimal("0"),
            },
        )
        _apply_security_transaction(state, transaction)
        _apply_cash_transaction(cash_state, transaction, portfolio, account)

    records: list[dict[str, str]] = []
    for state in security_state.values():
        quantity = state["quantity"]
        cost_basis = state["cost_basis"]
        if not isinstance(quantity, Decimal) or quantity == 0:
            continue
        if not isinstance(cost_basis, Decimal):
            continue

        broker = state["broker"]
        account = state["account"]
        portfolio = state["portfolio"]
        security = state["security"]
        if not isinstance(broker, Broker) or not isinstance(account, Account):
            continue
        if not isinstance(portfolio, Portfolio) or not isinstance(security, Security):
            continue

        latest_price = _latest_price(session, security, as_of_date=as_of_date)
        average_cost = cost_basis / quantity if quantity else Decimal("0")
        market_value = quantity * latest_price if latest_price is not None else None
        unrealized = market_value - cost_basis if market_value is not None else None
        if reporting_currency:
            average_cost = _convert_currency(
                session,
                average_cost,
                security.currency_code,
                reporting_currency,
                as_of_date,
            )
            if latest_price is not None:
                latest_price = _convert_currency(
                    session,
                    latest_price,
                    security.currency_code,
                    reporting_currency,
                    as_of_date,
                )
            if market_value is not None:
                market_value = _convert_currency(
                    session,
                    market_value,
                    security.currency_code,
                    reporting_currency,
                    as_of_date,
                )
            if unrealized is not None:
                unrealized = _convert_currency(
                    session,
                    unrealized,
                    security.currency_code,
                    reporting_currency,
                    as_of_date,
                )

        records.append(
            {
                "Broker": broker.name,
                "Account": account.name,
                "Portfolio": portfolio.name,
                "Portfolio URL": portfolio.portfolio_url or "",
                "Ticker": security.ticker,
                "Name": security.name,
                "Asset Class": security.asset_class.value,
                "Currency": security.currency_code,
                "Reporting Currency": reporting_currency or security.currency_code,
                "Quantity": str(quantity),
                "Average Cost": str(average_cost),
                "Latest Price": str(latest_price) if latest_price is not None else "",
                "Market Value": str(market_value) if market_value is not None else "",
                "Unrealized P&L": str(unrealized) if unrealized is not None else "",
            }
        )

    for (portfolio_id, currency_code), balance in cash_state.items():
        if balance == 0:
            continue
        portfolio_row = next((row for row in rows if row[1].id == portfolio_id), None)
        if portfolio_row is None:
            continue
        _, portfolio, account, broker, _ = portfolio_row
        converted_balance = (
            _convert_currency(
                session,
                balance,
                currency_code,
                reporting_currency,
                as_of_date,
            )
            if reporting_currency
            else balance
        )
        unit_value = (
            _convert_currency(
                session,
                Decimal("1"),
                currency_code,
                reporting_currency,
                as_of_date,
            )
            if reporting_currency
            else Decimal("1")
        )
        records.append(
            {
                "Broker": broker.name,
                "Account": account.name,
                "Portfolio": portfolio.name,
                "Portfolio URL": portfolio.portfolio_url or "",
                "Ticker": "CASH",
                "Name": f"{currency_code} Cash",
                "Asset Class": "CASH",
                "Currency": currency_code,
                "Reporting Currency": reporting_currency or currency_code,
                "Quantity": str(balance),
                "Average Cost": str(unit_value),
                "Latest Price": str(unit_value),
                "Market Value": str(converted_balance),
                "Unrealized P&L": "0",
            }
        )

    return records


def _calculate_realized_pnl_records(
    rows: list[tuple[Transaction, Portfolio, Account, Broker, Security | None]],
    tax_year: int | None,
) -> list[dict[str, str]]:
    lots_by_security: defaultdict[tuple[int, int], deque[Lot]] = defaultdict(deque)
    records: list[dict[str, str]] = []

    for transaction, portfolio, account, broker, security in rows:
        if security is None:
            continue

        key = (portfolio.id, security.id)
        lots = lots_by_security[key]

        if transaction.type == TransactionType.BUY:
            lots.append(
                Lot(
                    quantity=transaction.quantity,
                    unit_cost=transaction.total_value / transaction.quantity,
                    acquired_date=transaction.date.date(),
                )
            )
        elif transaction.type == TransactionType.SPLIT:
            _apply_split_to_lots(lots, transaction.quantity)
        elif transaction.type == TransactionType.SELL:
            if tax_year is not None and transaction.date.year != tax_year:
                _consume_lots(lots, transaction.quantity)
                continue

            quantity_to_sell = transaction.quantity
            cost_basis = Decimal("0")
            while quantity_to_sell > 0 and lots:
                lot = lots[0]
                matched_quantity = min(quantity_to_sell, lot.quantity)
                cost_basis += matched_quantity * lot.unit_cost
                lot.quantity -= matched_quantity
                quantity_to_sell -= matched_quantity
                if lot.quantity == 0:
                    lots.popleft()

            proceeds = transaction.total_value
            records.append(
                {
                    "Date": transaction.date.date().isoformat(),
                    "Broker": broker.name,
                    "Account": account.name,
                    "Portfolio": portfolio.name,
                    "Ticker": security.ticker,
                    "Quantity Sold": str(transaction.quantity),
                    "Proceeds": str(proceeds),
                    "Cost Basis": str(cost_basis),
                    "Realized P&L": str(proceeds - cost_basis),
                }
            )

    return records


def _portfolio_values_by_day(
    session: Session,
    rows: list[tuple[Transaction, Portfolio, Account, Broker, Security | None]],
    start_date: date,
    end_date: date,
) -> dict[date, Decimal]:
    values: dict[date, Decimal] = {}
    current_date = start_date
    while current_date <= end_date:
        values[current_date] = _portfolio_value_on_date(session, rows, current_date)
        current_date += timedelta(days=1)
    return values


def _portfolio_value_on_date(
    session: Session,
    rows: list[tuple[Transaction, Portfolio, Account, Broker, Security | None]],
    as_of_date: date,
) -> Decimal:
    quantities: defaultdict[int, Decimal] = defaultdict(Decimal)
    cash_by_currency: defaultdict[str, Decimal] = defaultdict(Decimal)

    for transaction, _, account, _, security in rows:
        if transaction.date.date() > as_of_date:
            continue

        if security is None:
            _apply_cash_to_currency(cash_by_currency, transaction, account.currency_code)
            continue

        if transaction.type == TransactionType.BUY:
            quantities[security.id] += transaction.quantity
            cash_by_currency[account.currency_code] -= _convert_to_account_currency(
                session, transaction.total_value, security.currency_code, account.currency_code, as_of_date
            )
        elif transaction.type == TransactionType.SELL:
            quantities[security.id] -= transaction.quantity
            cash_by_currency[account.currency_code] += _convert_to_account_currency(
                session, transaction.total_value, security.currency_code, account.currency_code, as_of_date
            )
        elif transaction.type == TransactionType.DIVIDEND:
            cash_by_currency[account.currency_code] += _convert_to_account_currency(
                session, transaction.total_value, security.currency_code, account.currency_code, as_of_date
            )
        elif transaction.type == TransactionType.SPLIT:
            quantities[security.id] *= transaction.quantity

    value = sum(cash_by_currency.values(), Decimal("0"))
    for security_id, quantity in quantities.items():
        if quantity == 0:
            continue
        security = session.get(Security, security_id)
        if security is None:
            continue
        latest_price = _latest_price(session, security, as_of_date=as_of_date)
        if latest_price is None:
            continue
        value += quantity * latest_price
    return value


def _external_cash_flows_by_day(
    rows: list[tuple[Transaction, Portfolio, Account, Broker, Security | None]],
) -> defaultdict[date, Decimal]:
    cash_flows: defaultdict[date, Decimal] = defaultdict(Decimal)
    for transaction, _, _, _, security in rows:
        if security is not None:
            continue
        if transaction.type == TransactionType.DEPOSIT:
            cash_flows[transaction.date.date()] += transaction.total_value
        elif transaction.type == TransactionType.WITHDRAWAL:
            cash_flows[transaction.date.date()] -= abs(transaction.total_value)
    return cash_flows


def _apply_security_transaction(state: dict[str, object], transaction: Transaction) -> None:
    quantity = state["quantity"]
    cost_basis = state["cost_basis"]
    if not isinstance(quantity, Decimal) or not isinstance(cost_basis, Decimal):
        return

    if transaction.type == TransactionType.BUY:
        quantity += transaction.quantity
        cost_basis += transaction.total_value
    elif transaction.type == TransactionType.SELL:
        average_cost = cost_basis / quantity if quantity else Decimal("0")
        cost_basis -= average_cost * transaction.quantity
        quantity -= transaction.quantity
    elif transaction.type == TransactionType.SPLIT:
        quantity *= transaction.quantity

    state["quantity"] = quantity
    state["cost_basis"] = cost_basis


def _apply_cash_transaction(
    cash_state: defaultdict[tuple[int, str], Decimal],
    transaction: Transaction,
    portfolio: Portfolio,
    account: Account,
) -> None:
    key = (portfolio.id, account.currency_code)
    if transaction.security_id is None:
        _apply_cash_to_portfolio(cash_state, key, transaction)


def _apply_cash_to_portfolio(
    cash_state: defaultdict[tuple[int, str], Decimal],
    key: tuple[int, str],
    transaction: Transaction,
) -> None:
    if transaction.type == TransactionType.DEPOSIT:
        cash_state[key] += transaction.total_value
    elif transaction.type == TransactionType.WITHDRAWAL:
        cash_state[key] -= abs(transaction.total_value)


def _apply_cash_to_currency(
    cash_by_currency: defaultdict[str, Decimal],
    transaction: Transaction,
    currency_code: str,
) -> None:
    if transaction.type == TransactionType.DEPOSIT:
        cash_by_currency[currency_code] += transaction.total_value
    elif transaction.type == TransactionType.WITHDRAWAL:
        cash_by_currency[currency_code] -= abs(transaction.total_value)


def _apply_split_to_lots(lots: deque[Lot], split_ratio: Decimal) -> None:
    for lot in lots:
        lot.quantity *= split_ratio
        lot.unit_cost /= split_ratio


def _consume_lots(lots: deque[Lot], quantity: Decimal) -> None:
    quantity_to_consume = quantity
    while quantity_to_consume > 0 and lots:
        lot = lots[0]
        matched_quantity = min(quantity_to_consume, lot.quantity)
        lot.quantity -= matched_quantity
        quantity_to_consume -= matched_quantity
        if lot.quantity == 0:
            lots.popleft()


def _latest_price(
    session: Session,
    security: Security,
    as_of_date: date | None = None,
) -> Decimal | None:
    direct_price = _latest_price_for_security_id(
        session,
        security.id,
        as_of_date=as_of_date,
    )
    if direct_price is not None:
        return direct_price

    # A transaction may use a base exchange ticker (for example VWRP) while
    # market data uses the Yahoo/exchange-qualified symbol (VWRP.L). Use that
    # alias only when it resolves to one priced security in the same currency.
    ticker_base = security.ticker.upper().split(".", 1)[0]
    alias_prices: list[Decimal] = []
    securities = session.scalars(
        select(Security).where(Security.currency_code == security.currency_code)
    ).all()
    for candidate in securities:
        if candidate.id == security.id:
            continue
        if candidate.ticker.upper().split(".", 1)[0] != ticker_base:
            continue
        candidate_price = _latest_price_for_security_id(
            session,
            candidate.id,
            as_of_date=as_of_date,
        )
        if candidate_price is not None:
            alias_prices.append(candidate_price)

    return alias_prices[0] if len(alias_prices) == 1 else None


def _latest_price_for_security_id(
    session: Session,
    security_id: int,
    as_of_date: date | None = None,
) -> Decimal | None:
    statement = select(PriceHistory).where(PriceHistory.security_id == security_id)
    if as_of_date is not None:
        statement = statement.where(PriceHistory.date <= as_of_date)
    price = session.scalar(statement.order_by(PriceHistory.date.desc()).limit(1))
    return price.close_price if price else None


def _convert_to_account_currency(
    session: Session,
    value: Decimal,
    security_currency: str,
    account_currency: str,
    as_of_date: date,
) -> Decimal:
    return _convert_currency(
        session,
        value,
        security_currency,
        account_currency,
        as_of_date,
    )


def _convert_currency(
    session: Session,
    value: Decimal,
    source_currency: str,
    target_currency: str,
    as_of_date: date,
) -> Decimal:
    source = source_currency.upper()
    target = target_currency.upper()
    if source == target:
        return value

    source_to_usd = _rate_to_usd(session, source, as_of_date)
    target_to_usd = _rate_to_usd(session, target, as_of_date)
    if source_to_usd is None:
        raise ValueError(
            f"No FX rate is available to normalize {source} to USD on or before "
            f"{as_of_date.isoformat()}."
        )
    if target_to_usd is None or target_to_usd == 0:
        raise ValueError(
            f"No FX rate is available to convert USD to {target} on or before "
            f"{as_of_date.isoformat()}."
        )
    return value * source_to_usd / target_to_usd


def _rate_to_usd(
    session: Session,
    currency: str,
    as_of_date: date,
) -> Decimal | None:
    if currency == "USD":
        return Decimal("1")

    direct_rate = _latest_fx_rate(session, currency, "USD", as_of_date)
    if direct_rate is not None:
        return direct_rate

    inverse_rate = _latest_fx_rate(session, "USD", currency, as_of_date)
    if inverse_rate is not None and inverse_rate != 0:
        return Decimal("1") / inverse_rate
    return None


def _latest_fx_rate(
    session: Session,
    base_currency: str,
    quote_currency: str,
    as_of_date: date,
) -> Decimal | None:
    rate = session.scalar(
        select(FxRateHistory)
        .where(
            FxRateHistory.base_currency_code == base_currency,
            FxRateHistory.quote_currency_code == quote_currency,
            FxRateHistory.date <= as_of_date,
        )
        .order_by(FxRateHistory.date.desc())
        .limit(1)
    )
    return rate.close if rate else None


def _decimal_or_zero(value: object) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")
