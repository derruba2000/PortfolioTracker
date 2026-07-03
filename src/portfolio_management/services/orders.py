from __future__ import annotations

from datetime import date
from datetime import datetime
from datetime import UTC
from decimal import Decimal
from decimal import InvalidOperation

import pandas as pd
from sqlalchemy import func
from sqlalchemy import select

from portfolio_management.db.models import (
    Account,
    Broker,
    FxRateHistory,
    Order,
    OrderStatus,
    OrderType,
    Portfolio,
    PriceHistory,
    Security,
    Transaction,
    TransactionType,
)
from portfolio_management.db.session import get_session_factory
from portfolio_management.services.accounts import parse_choice_id
from portfolio_management.services.reference_data import ensure_currency_code
from portfolio_management.services.transactions import TransactionInput, create_transaction


def create_order(
    portfolio_choice: str | int | None,
    order_type: str,
    security_ticker: str | None,
    target_quantity: str | Decimal | None,
    target_price: str | Decimal | None,
    target_cash_amount: str | Decimal | None,
    currency_code: str | None = None,
) -> str:
    portfolio_id = parse_choice_id(portfolio_choice)
    if portfolio_id is None:
        raise ValueError("Portfolio is required.")

    normalized_type = (order_type or "").strip().upper()
    if not normalized_type:
        raise ValueError("Action type is required.")

    try:
        parsed_order_type = OrderType(normalized_type)
    except ValueError as exc:
        raise ValueError(f"Unsupported action type '{order_type}'.") from exc

    session_factory = get_session_factory()
    with session_factory() as session:
        portfolio = session.get(Portfolio, portfolio_id)
        if portfolio is None:
            raise ValueError(f"Portfolio id {portfolio_id} does not exist.")
        selected_currency = ensure_currency_code(
            session,
            currency_code or portfolio.account.currency_code,
        )

        order_security: Security | None = None
        parsed_target_quantity: Decimal | None = None
        parsed_target_price: Decimal | None = None
        parsed_target_cash_amount: Decimal | None = None

        if parsed_order_type in {OrderType.BUY, OrderType.SELL}:
            clean_ticker = (security_ticker or "").strip().upper()
            if not clean_ticker:
                raise ValueError("Security ticker is required for BUY/SELL orders.")
            security = session.scalar(select(Security).where(Security.ticker == clean_ticker))
            if security is None:
                raise ValueError(f"Security '{clean_ticker}' does not exist.")

            order_security = security
            parsed_target_quantity = _parse_positive_decimal(target_quantity, field_name="Target quantity")
            parsed_target_price = _parse_positive_decimal(target_price, field_name="Target limit price")
        else:
            parsed_target_cash_amount = _parse_positive_decimal(
                target_cash_amount,
                field_name="Target cash amount",
            )

        order = Order(
            portfolio=portfolio,
            security=order_security,
            order_type=parsed_order_type,
            status=OrderStatus.PENDING,
            target_quantity=parsed_target_quantity,
            target_price=parsed_target_price,
            target_cash_amount=parsed_target_cash_amount,
            currency_code=selected_currency,
        )

        session.add(order)
        session.commit()

    return f"Created order #{order.id} ({parsed_order_type.value}) with PENDING status."


def list_order_portfolio_choices(account_filter: str = "Real") -> list[str]:
    session_factory = get_session_factory()
    with session_factory() as session:
        stmt = (
            select(Portfolio, Account, Broker)
            .join(Portfolio.account)
            .join(Account.broker)
            .where(Broker.is_active.is_(True))
            .where(Account.is_active.is_(True))
            .where(Portfolio.is_active.is_(True))
            .order_by(Broker.name, Account.name, Portfolio.name)
        )
        if account_filter == "Real":
            stmt = stmt.where(Account.is_simulated.is_(False))
        elif account_filter == "Test":
            stmt = stmt.where(Account.is_simulated.is_(True))

        rows = session.execute(stmt).all()

    choices: list[str] = []
    for portfolio, account, broker in rows:
        mode = "TEST" if account.is_simulated else "LIVE"
        choices.append(
            f"{portfolio.id} | {broker.name} / {account.name} / {portfolio.name} [{mode}]"
        )
    return choices


def list_pending_order_choices(account_filter: str = "Real") -> list[str]:
    session_factory = get_session_factory()
    with session_factory() as session:
        stmt = (
            select(Order, Portfolio, Account, Broker, Security)
            .join(Order.portfolio)
            .join(Portfolio.account)
            .join(Account.broker)
            .join(Order.security, isouter=True)
            .where(Broker.is_active.is_(True))
            .where(Account.is_active.is_(True))
            .where(Portfolio.is_active.is_(True))
            .where(Order.status == OrderStatus.PENDING)
            .order_by(Order.created_at.desc(), Order.id.desc())
        )
        if account_filter == "Real":
            stmt = stmt.where(Account.is_simulated.is_(False))
        elif account_filter == "Test":
            stmt = stmt.where(Account.is_simulated.is_(True))
        rows = session.execute(stmt).all()

    choices: list[str] = []
    for order, portfolio, account, broker, security in rows:
        symbol = security.ticker if security is not None else "CASH"
        mode = "TEST" if account.is_simulated else "LIVE"
        choices.append(
            f"{order.id} | {order.order_type.value} {symbol} | "
            f"{broker.name} / {account.name} / {portfolio.name} [{mode}]"
        )
    return choices


def cancel_order(order_choice: str | int | None) -> str:
    order_id = parse_choice_id(order_choice)
    if order_id is None:
        raise ValueError("Order is required.")

    session_factory = get_session_factory()
    with session_factory() as session:
        order = session.get(Order, order_id)
        if order is None:
            raise ValueError(f"Order id {order_id} does not exist.")
        if order.status != OrderStatus.PENDING:
            raise ValueError("Only PENDING orders can be cancelled.")

        linked_transactions = session.scalar(
            select(func.count(Transaction.id)).where(Transaction.order_id == order.id)
        )
        if int(linked_transactions or 0) > 0:
            raise ValueError("Order already has linked transactions and cannot be cancelled.")

        order.status = OrderStatus.CANCELLED
        session.commit()

    return f"Cancelled order #{order_id}."


def mark_order_completed(
    order_choice: str | int | None,
    actual_quantity: str | Decimal | None,
    actual_price: str | Decimal | None,
    actual_fees: str | Decimal | None,
) -> str:
    order_id = parse_choice_id(order_choice)
    if order_id is None:
        raise ValueError("Order is required.")

    quantity = _parse_positive_decimal(actual_quantity, field_name="Actual execution quantity")
    price = _parse_non_negative_decimal(actual_price, field_name="Actual execution price")
    fees = _parse_non_negative_decimal(actual_fees, field_name="Actual broker fees")

    session_factory = get_session_factory()
    with session_factory() as session:
        order = session.get(Order, order_id)
        if order is None:
            raise ValueError(f"Order id {order_id} does not exist.")
        if order.status != OrderStatus.PENDING:
            raise ValueError("Only PENDING orders can be marked as completed.")

        transaction_type = _transaction_type_from_order_type(order.order_type)
        ticker = order.security.ticker if order.security is not None else None
        description = f"Executed from order #{order.id}"
        execution_date = datetime.now()
        account_currency = order.portfolio.account.currency_code
        order_currency = (order.currency_code or account_currency).upper()
        fx_rate = _fx_rate_to_account_currency(
            session=session,
            source_currency=order_currency,
            account_currency=account_currency,
            as_of_date=execution_date.date(),
        )

        if order.order_type in {OrderType.BUY, OrderType.SELL}:
            create_transaction(
                session,
                TransactionInput(
                    portfolio_id=order.portfolio_id,
                    date=execution_date,
                    transaction_type=transaction_type,
                    ticker=ticker,
                    quantity=quantity,
                    price=price,
                    fees=fees,
                    currency_exchange_rate=fx_rate,
                    description=description,
                    order_id=order.id,
                ),
            )
        else:
            account_price = price * fx_rate
            account_fees = fees * fx_rate
            create_transaction(
                session,
                TransactionInput(
                    portfolio_id=order.portfolio_id,
                    date=execution_date,
                    transaction_type=transaction_type,
                    ticker=None,
                    quantity=quantity,
                    price=account_price,
                    fees=account_fees,
                    currency_exchange_rate=Decimal("1"),
                    description=description,
                    order_id=order.id,
                ),
            )

        order.status = OrderStatus.EXECUTED
        order.executed_at = datetime.now(UTC)
        session.commit()

    return (
        f"Marked order #{order_id} as EXECUTED "
        f"(qty={quantity}, price={price}, fees={fees})."
    )


def portfolio_account_currency(portfolio_choice: str | int | None) -> str:
    portfolio_id = parse_choice_id(portfolio_choice)
    if portfolio_id is None:
        return ""

    session_factory = get_session_factory()
    with session_factory() as session:
        portfolio = session.get(Portfolio, portfolio_id)
        if portfolio is None:
            return ""
        return portfolio.account.currency_code


def order_execution_defaults(order_choice: str | int | None) -> tuple[str, str, str]:
    order_id = parse_choice_id(order_choice)
    if order_id is None:
        return "1", "0", "0"

    session_factory = get_session_factory()
    with session_factory() as session:
        order = session.get(Order, order_id)
        if order is None:
            return "1", "0", "0"
        if order.order_type in {OrderType.DEPOSIT, OrderType.WITHDRAW}:
            return "1", _decimal_or_empty(order.target_cash_amount), "0"
        return (
            _decimal_or_empty(order.target_quantity) or "1",
            _decimal_or_empty(order.target_price) or "0",
            "0",
        )


def buy_order_price_defaults(security_ticker: str | None) -> tuple[str, str, str]:
    clean_ticker = (security_ticker or "").strip().upper()
    if not clean_ticker:
        return "", "", "none"

    session_factory = get_session_factory()
    with session_factory() as session:
        security = session.scalar(select(Security).where(Security.ticker == clean_ticker))
        if security is None:
            return "", "", "none"
        prices = session.scalars(
            select(PriceHistory)
            .where(PriceHistory.security_id == security.id)
            .order_by(PriceHistory.date.desc())
            .limit(2)
        ).all()

    if not prices:
        return "", "", "none"

    latest = Decimal(str(prices[0].close))
    target = latest * Decimal("1.05")
    if len(prices) < 2:
        trend = "flat"
    elif latest > Decimal(str(prices[1].close)):
        trend = "up"
    elif latest < Decimal(str(prices[1].close)):
        trend = "down"
    else:
        trend = "flat"
    return f"{latest:,.4f}", f"{target:.4f}", trend


def _fx_rate_to_account_currency(
    session: object,
    source_currency: str,
    account_currency: str,
    as_of_date: date,
) -> Decimal:
    source = source_currency.upper()
    target = account_currency.upper()
    if source == target:
        return Decimal("1")

    direct_rate = _latest_fx_rate(session, source, target, as_of_date)
    if direct_rate is not None:
        return direct_rate

    inverse_rate = _latest_fx_rate(session, target, source, as_of_date)
    if inverse_rate is not None and inverse_rate != 0:
        return Decimal("1") / inverse_rate

    raise ValueError(
        f"No FX rate is available to convert {source} to {target} on or before "
        f"{as_of_date.isoformat()}."
    )


def _latest_fx_rate(
    session: object,
    base_currency: str,
    quote_currency: str,
    as_of_date: date,
) -> Decimal | None:
    rate = session.scalar(
        select(FxRateHistory)
        .where(
            FxRateHistory.base_currency_code == base_currency.upper(),
            FxRateHistory.quote_currency_code == quote_currency.upper(),
            FxRateHistory.date <= as_of_date,
        )
        .order_by(FxRateHistory.date.desc())
        .limit(1)
    )
    return rate.close if rate else None

def list_orders(
    account_filter: str = "Real",
    status_filter: str = "All",
    portfolio_filter: str | int | None = None,
    start_date: str | date | None = None,
    end_date: str | date | None = None,
) -> pd.DataFrame:
    session_factory = get_session_factory()
    parsed_status = _parse_status_filter(status_filter)
    portfolio_id = parse_choice_id(portfolio_filter)
    parsed_start = _parse_date(start_date)
    parsed_end = _parse_date(end_date)

    with session_factory() as session:
        stmt = (
            select(Order, Portfolio, Account, Broker, Security)
            .join(Order.portfolio)
            .join(Portfolio.account)
            .join(Account.broker)
            .join(Order.security, isouter=True)
            .where(Broker.is_active.is_(True))
            .where(Account.is_active.is_(True))
            .where(Portfolio.is_active.is_(True))
            .order_by(Order.created_at.desc(), Order.id.desc())
        )
        if account_filter == "Real":
            stmt = stmt.where(Account.is_simulated.is_(False))
        elif account_filter == "Test":
            stmt = stmt.where(Account.is_simulated.is_(True))
        if parsed_status is not None:
            stmt = stmt.where(Order.status == parsed_status)
        if portfolio_id is not None:
            stmt = stmt.where(Order.portfolio_id == portfolio_id)
        if parsed_start is not None:
            stmt = stmt.where(func.date(Order.created_at) >= parsed_start.isoformat())
        if parsed_end is not None:
            stmt = stmt.where(func.date(Order.created_at) <= parsed_end.isoformat())

        rows = session.execute(stmt).all()

        price_map = _latest_market_prices(session)

    records: list[dict[str, str | int]] = []
    for order, portfolio, account, broker, security in rows:
        _ = account
        _ = broker
        market_price = price_map.get(security.id) if security is not None else None
        target_price = order.target_price
        records.append(
            {
                "ID": order.id,
                "Date": order.created_at.date().isoformat(),
                "Portfolio": portfolio.name,
                "Portfolio URL": portfolio.portfolio_url or "",
                "Type": order.order_type.value,
                "Asset/Ticker": security.ticker if security is not None else "CASH",
                "Quantity": _decimal_or_empty(order.target_quantity),
                "Price": _decimal_or_empty(order.target_price or order.target_cash_amount),
                "Currency": order.currency_code,
                "Status": order.status.value,
                "Market vs Target": _market_vs_target_tag(
                    order_type=order.order_type,
                    market_price=market_price,
                    target_price=target_price,
                ),
            }
        )

    return pd.DataFrame(
        records,
        columns=[
            "ID",
            "Date",
            "Portfolio",
            "Portfolio URL",
            "Type",
            "Asset/Ticker",
            "Quantity",
            "Price",
            "Currency",
            "Status",
            "Market vs Target",
        ],
    )


def _latest_market_prices(session: object) -> dict[int, Decimal]:
    subquery = (
        select(
            PriceHistory.security_id.label("security_id"),
            func.max(PriceHistory.date).label("max_date"),
        )
        .group_by(PriceHistory.security_id)
        .subquery()
    )
    rows = session.execute(
        select(PriceHistory.security_id, PriceHistory.close)
        .join(
            subquery,
            (PriceHistory.security_id == subquery.c.security_id)
            & (PriceHistory.date == subquery.c.max_date),
        )
    ).all()
    return {security_id: close for security_id, close in rows}


def _decimal_or_empty(value: Decimal | None) -> str:
    if value is None:
        return ""
    return str(value)


def _parse_positive_decimal(value: str | Decimal | None, field_name: str) -> Decimal:
    raw = str(value or "").strip().replace(",", "")
    if not raw:
        raise ValueError(f"{field_name} is required.")
    try:
        parsed = Decimal(raw)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field_name} must be a valid decimal number.") from exc
    if parsed <= 0:
        raise ValueError(f"{field_name} must be greater than zero.")
    return parsed


def _parse_non_negative_decimal(value: str | Decimal | None, field_name: str) -> Decimal:
    raw = str(value or "").strip().replace(",", "")
    if not raw:
        return Decimal("0")
    try:
        parsed = Decimal(raw)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field_name} must be a valid decimal number.") from exc
    if parsed < 0:
        raise ValueError(f"{field_name} cannot be negative.")
    return parsed


def _transaction_type_from_order_type(order_type: OrderType) -> TransactionType:
    if order_type == OrderType.BUY:
        return TransactionType.BUY
    if order_type == OrderType.SELL:
        return TransactionType.SELL
    if order_type == OrderType.DEPOSIT:
        return TransactionType.DEPOSIT
    return TransactionType.WITHDRAWAL


def _parse_status_filter(raw_status: str | None) -> OrderStatus | None:
    clean = (raw_status or "All").strip().upper()
    if clean in {"", "ALL"}:
        return None
    try:
        return OrderStatus(clean)
    except ValueError as exc:
        raise ValueError(f"Unsupported status filter '{raw_status}'.") from exc


def _parse_date(raw_date: str | date | None) -> date | None:
    if raw_date is None:
        return None
    if isinstance(raw_date, date):
        return raw_date

    clean = str(raw_date).strip()
    if not clean:
        return None
    try:
        return datetime.fromisoformat(clean).date()
    except ValueError:
        return date.fromisoformat(clean)


def _market_vs_target_tag(
    order_type: OrderType,
    market_price: Decimal | None,
    target_price: Decimal | None,
) -> str:
    if market_price is None or target_price is None:
        return ""

    if market_price > target_price:
        arrow = "▲"
    elif market_price < target_price:
        arrow = "▼"
    else:
        arrow = "="

    if order_type == OrderType.BUY:
        is_positive = market_price <= target_price
    elif order_type == OrderType.SELL:
        is_positive = market_price >= target_price
    else:
        return ""

    color = "#16a34a" if is_positive else "#dc2626"
    style = (
        f"background:{color};color:white;padding:3px 8px;"
        "border-radius:4px;font-weight:600;font-size:0.9em;"
    )
    return (
        f'<span style="{style}">{arrow} '
        f"Mkt {market_price:,.4f} vs Target {target_price:,.4f}</span>"
    )
