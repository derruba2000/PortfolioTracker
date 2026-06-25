from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from portfolio_management.db.models import (
    Account,
    Broker,
    Portfolio,
    PriceHistory,
    Security,
    Transaction,
    TransactionType,
)
from portfolio_management.db.session import get_session_factory
from portfolio_management.services.analytics import (
    ALL_ACCOUNTS_MODE,
    LIVE_MODE,
    SANDBOX_MODE,
    _convert_currency,
    _latest_price,
)


def portfolio_value_history(
    account_mode: str = LIVE_MODE,
    reporting_currency: str = "GBP",
    start_date: date | None = None,
    end_date: date | None = None,
    portfolio_id: int | None = None,
) -> pd.DataFrame:
    """Return one row per calendar day with portfolio value in one currency."""
    reporting_currency = reporting_currency.upper()
    end_date = end_date or date.today()
    session_factory = get_session_factory()
    with session_factory() as session:
        rows = _transaction_rows(session, account_mode, portfolio_id)
        if not rows:
            return pd.DataFrame(columns=["Date", "Portfolio Value"])
        first_transaction = min(transaction.date.date() for transaction, *_ in rows)
        start_date = max(start_date or first_transaction, first_transaction)
        records = []
        current = start_date
        while current <= end_date:
            records.append(
                {
                    "Date": current.isoformat(),
                    "Portfolio Value": float(
                        _portfolio_value(
                            session,
                            rows,
                            current,
                            reporting_currency,
                        )
                    ),
                }
            )
            current += timedelta(days=1)
    return pd.DataFrame(records, columns=["Date", "Portfolio Value"])


def asset_price_history(
    account_mode: str = LIVE_MODE,
    start_date: date | None = None,
    end_date: date | None = None,
    portfolio_id: int | None = None,
) -> pd.DataFrame:
    """Return stored daily closes for securities held in the selected mode."""
    end_date = end_date or date.today()
    session_factory = get_session_factory()
    with session_factory() as session:
        security_ids = _held_security_ids(session, account_mode, end_date, portfolio_id)
        if not security_ids:
            return pd.DataFrame(columns=["Date", "Ticker", "Close"])
        security_ids = _priced_security_ids(session, security_ids, end_date)
        statement = (
            select(PriceHistory.date, Security.ticker, PriceHistory.close)
            .join(Security, Security.id == PriceHistory.security_id)
            .where(PriceHistory.security_id.in_(security_ids))
            .where(PriceHistory.date <= end_date)
            .order_by(PriceHistory.date, Security.ticker)
        )
        if start_date:
            statement = statement.where(PriceHistory.date >= start_date)
        rows = session.execute(statement).all()
    return pd.DataFrame(
        [
            {"Date": row.date.isoformat(), "Ticker": row.ticker, "Close": float(row.close)}
            for row in rows
        ],
        columns=["Date", "Ticker", "Close"],
    )


def cash_flow_history(
    account_mode: str = LIVE_MODE,
    reporting_currency: str = "GBP",
    start_date: date | None = None,
    end_date: date | None = None,
    portfolio_id: int | None = None,
) -> pd.DataFrame:
    """Return external deposits (+) and withdrawals (-) in reporting currency."""
    reporting_currency = reporting_currency.upper()
    end_date = end_date or date.today()
    session_factory = get_session_factory()
    with session_factory() as session:
        rows = _transaction_rows(session, account_mode, portfolio_id)
        settlement_transaction_ids = _trade_settlement_transaction_ids(rows)
        flows: defaultdict[date, Decimal] = defaultdict(Decimal)
        for transaction, _, account, _, security in rows:
            flow_date = transaction.date.date()
            if (
                security is not None
                or transaction.id in settlement_transaction_ids
                or flow_date > end_date
            ):
                continue
            if start_date and flow_date < start_date:
                continue
            if transaction.type == TransactionType.DEPOSIT:
                amount = transaction.total_value
            elif transaction.type == TransactionType.WITHDRAWAL:
                amount = -abs(transaction.total_value)
            else:
                continue
            flows[flow_date] += _convert_currency(
                session,
                amount,
                account.currency_code,
                reporting_currency,
                flow_date,
            )
    return pd.DataFrame(
        [
            {"Date": flow_date.isoformat(), "Cash Flow": float(amount)}
            for flow_date, amount in sorted(flows.items())
        ],
        columns=["Date", "Cash Flow"],
    )


def benchmark_price_history(
    ticker: str,
    start_date: date | None = None,
    end_date: date | None = None,
) -> pd.DataFrame:
    """Return locally stored closes for a benchmark ticker when available."""
    end_date = end_date or date.today()
    session_factory = get_session_factory()
    with session_factory() as session:
        statement = (
            select(PriceHistory.date, PriceHistory.close)
            .join(Security, Security.id == PriceHistory.security_id)
            .where(Security.ticker == ticker)
            .where(PriceHistory.date <= end_date)
            .order_by(PriceHistory.date)
        )
        if start_date:
            statement = statement.where(PriceHistory.date >= start_date)
        rows = session.execute(statement).all()
    return pd.DataFrame(
        [{"Date": row.date.isoformat(), "Close": float(row.close)} for row in rows],
        columns=["Date", "Close"],
    )


def _transaction_rows(
    session: Session,
    account_mode: str,
    portfolio_id: int | None = None,
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
    elif account_mode != ALL_ACCOUNTS_MODE:
        statement = statement.where(Account.is_simulated.is_(False))
    if portfolio_id is not None:
        statement = statement.where(Portfolio.id == portfolio_id)
    return list(session.execute(statement).all())


def _held_security_ids(
    session: Session,
    account_mode: str,
    as_of_date: date,
    portfolio_id: int | None = None,
) -> set[int]:
    quantities: defaultdict[int, Decimal] = defaultdict(Decimal)
    for transaction, _, _, _, security in _transaction_rows(
        session,
        account_mode,
        portfolio_id,
    ):
        if security is None or transaction.date.date() > as_of_date:
            continue
        if transaction.type == TransactionType.BUY:
            quantities[security.id] += transaction.quantity
        elif transaction.type == TransactionType.SELL:
            quantities[security.id] -= transaction.quantity
        elif transaction.type == TransactionType.SPLIT:
            quantities[security.id] *= transaction.quantity
    return {security_id for security_id, quantity in quantities.items() if quantity != 0}


def _priced_security_ids(
    session: Session,
    held_security_ids: set[int],
    as_of_date: date,
) -> set[int]:
    resolved: set[int] = set()
    securities = session.scalars(select(Security)).all()
    by_id = {security.id: security for security in securities}
    for security_id in held_security_ids:
        direct_exists = session.scalar(
            select(PriceHistory.security_id)
            .where(
                PriceHistory.security_id == security_id,
                PriceHistory.date <= as_of_date,
            )
            .limit(1)
        )
        if direct_exists is not None:
            resolved.add(security_id)
            continue
        held = by_id.get(security_id)
        if held is None:
            continue
        ticker_base = held.ticker.upper().split(".", 1)[0]
        aliases = []
        for candidate in securities:
            if candidate.currency_code != held.currency_code:
                continue
            if candidate.ticker.upper().split(".", 1)[0] != ticker_base:
                continue
            has_price = session.scalar(
                select(PriceHistory.security_id)
                .where(
                    PriceHistory.security_id == candidate.id,
                    PriceHistory.date <= as_of_date,
                )
                .limit(1)
            )
            if has_price is not None:
                aliases.append(candidate.id)
        if len(aliases) == 1:
            resolved.add(aliases[0])
    return resolved


def _portfolio_value(
    session: Session,
    rows: list[tuple[Transaction, Portfolio, Account, Broker, Security | None]],
    as_of_date: date,
    reporting_currency: str,
) -> Decimal:
    quantities: defaultdict[int, Decimal] = defaultdict(Decimal)
    cash: defaultdict[tuple[int, str], Decimal] = defaultdict(Decimal)
    settlement_transaction_ids = _trade_settlement_transaction_ids(rows)
    explicitly_funded_portfolios = {
        portfolio.id
        for transaction, portfolio, _, _, security in rows
        if (
            security is None
            and transaction.date.date() <= as_of_date
            and transaction.type
            in {TransactionType.DEPOSIT, TransactionType.WITHDRAWAL}
        )
    }

    for transaction, portfolio, account, _, security in rows:
        if transaction.date.date() > as_of_date:
            continue
        cash_key = (portfolio.id, account.currency_code)
        if security is None:
            if transaction.type == TransactionType.DEPOSIT:
                cash[cash_key] += transaction.total_value
            elif transaction.type == TransactionType.WITHDRAWAL:
                cash[cash_key] -= abs(transaction.total_value)
            continue

        trade_value = _convert_currency(
            session,
            transaction.total_value,
            security.currency_code,
            account.currency_code,
            transaction.date.date(),
        )
        if transaction.type == TransactionType.BUY:
            quantities[security.id] += transaction.quantity
            if (
                portfolio.id in explicitly_funded_portfolios
                and transaction.id not in settlement_transaction_ids
            ):
                cash[cash_key] -= trade_value
        elif transaction.type == TransactionType.SELL:
            quantities[security.id] -= transaction.quantity
            if (
                portfolio.id in explicitly_funded_portfolios
                and transaction.id not in settlement_transaction_ids
            ):
                cash[cash_key] += trade_value
        elif transaction.type == TransactionType.DIVIDEND:
            cash[cash_key] += trade_value
        elif transaction.type == TransactionType.SPLIT:
            quantities[security.id] *= transaction.quantity

    total = Decimal("0")
    for (_, currency), amount in cash.items():
        total += _convert_currency(
            session,
            amount,
            currency,
            reporting_currency,
            as_of_date,
        )
    for security_id, quantity in quantities.items():
        if quantity == 0:
            continue
        security = session.get(Security, security_id)
        if security is None:
            continue
        price = _latest_price(session, security, as_of_date)
        if price is None:
            continue
        total += _convert_currency(
            session,
            quantity * price,
            security.currency_code,
            reporting_currency,
            as_of_date,
        )
    return total


def _trade_settlement_transaction_ids(
    rows: list[tuple[Transaction, Portfolio, Account, Broker, Security | None]],
) -> set[int]:
    """Identify explicit cash rows that already settle a recorded BUY or SELL."""
    trades_by_key: defaultdict[
        tuple[int, date, str, TransactionType],
        list[Transaction],
    ] = defaultdict(list)
    cash_by_key: defaultdict[
        tuple[int, date, str, TransactionType],
        list[Transaction],
    ] = defaultdict(list)

    for transaction, portfolio, _, _, security in rows:
        description = (transaction.description or "").strip().casefold()
        if not description:
            continue
        transaction_date = transaction.date.date()
        if security is not None and transaction.type in {
            TransactionType.BUY,
            TransactionType.SELL,
        }:
            cash_type = (
                TransactionType.WITHDRAWAL
                if transaction.type == TransactionType.BUY
                else TransactionType.DEPOSIT
            )
            trades_by_key[
                (portfolio.id, transaction_date, description, cash_type)
            ].append(transaction)
        elif security is None and transaction.type in {
            TransactionType.DEPOSIT,
            TransactionType.WITHDRAWAL,
        }:
            cash_by_key[
                (portfolio.id, transaction_date, description, transaction.type)
            ].append(transaction)

    matched_ids: set[int] = set()
    for key, trades in trades_by_key.items():
        cash_transactions = cash_by_key.get(key, [])
        for trade, cash_transaction in zip(trades, cash_transactions, strict=False):
            matched_ids.add(trade.id)
            matched_ids.add(cash_transaction.id)
    return matched_ids
