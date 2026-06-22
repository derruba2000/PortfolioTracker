from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pandas as pd
import yfinance as yf
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from portfolio_management.db.models import (
    Account,
    AssetClass,
    FxRateHistory,
    Portfolio,
    PriceHistory,
    Security,
    Transaction,
)
from portfolio_management.db.session import get_session_factory


DEFAULT_LOOKBACK_DAYS = 365

HistoryFetcher = Callable[[str, date, date], pd.DataFrame]


@dataclass(frozen=True)
class MarketDataResult:
    prices_inserted: int = 0
    fx_rates_inserted: int = 0
    skipped: tuple[str, ...] = ()

    @property
    def message(self) -> str:
        skipped = f" Skipped: {', '.join(self.skipped)}." if self.skipped else ""
        return (
            f"Stored {self.prices_inserted} price row(s) and "
            f"{self.fx_rates_inserted} FX row(s).{skipped}"
        )


def update_market_data(
    start_date: date | None = None,
    end_date: date | None = None,
    fetcher: HistoryFetcher | None = None,
) -> MarketDataResult:
    session_factory = get_session_factory()
    with session_factory() as session:
        result = update_market_data_for_session(
            session=session,
            start_date=start_date,
            end_date=end_date,
            fetcher=fetcher,
        )
        session.commit()
    return result


def update_market_data_for_session(
    session: Session,
    start_date: date | None = None,
    end_date: date | None = None,
    fetcher: HistoryFetcher | None = None,
) -> MarketDataResult:
    fetcher = fetcher or fetch_yfinance_history
    end_date = end_date or date.today()
    start_date = start_date or end_date - timedelta(days=DEFAULT_LOOKBACK_DAYS)

    prices_inserted = 0
    fx_rates_inserted = 0
    skipped: list[str] = []

    for security in list_tracked_securities(session):
        security_start = _next_security_price_date(session, security, start_date)
        if security_start > end_date:
            continue

        try:
            history = fetcher(security.ticker, security_start, end_date)
            prices_inserted += store_security_prices(session, security, history)
        except Exception as exc:
            skipped.append(f"{security.ticker} ({exc})")

    for base_currency, quote_currency in list_required_fx_pairs(session):
        fx_start = _next_fx_rate_date(session, base_currency, quote_currency, start_date)
        if fx_start > end_date:
            continue

        symbol = yahoo_fx_symbol(base_currency, quote_currency)
        try:
            history = fetcher(symbol, fx_start, end_date)
            fx_rates_inserted += store_fx_rates(
                session=session,
                base_currency=base_currency,
                quote_currency=quote_currency,
                history=history,
            )
        except Exception as exc:
            skipped.append(f"{symbol} ({exc})")

    session.flush()
    return MarketDataResult(
        prices_inserted=prices_inserted,
        fx_rates_inserted=fx_rates_inserted,
        skipped=tuple(skipped),
    )


def fetch_yfinance_history(symbol: str, start_date: date, end_date: date) -> pd.DataFrame:
    # yfinance treats the end date as exclusive, so include the requested day.
    return yf.download(
        symbol,
        start=start_date.isoformat(),
        end=(end_date + timedelta(days=1)).isoformat(),
        auto_adjust=False,
        progress=False,
        threads=False,
    )


def store_security_prices(
    session: Session,
    security: Security,
    history: pd.DataFrame,
) -> int:
    inserted = 0
    for price_date, close_price in _iter_close_prices(history):
        existing = session.get(
            PriceHistory,
            {"security_id": security.id, "date": price_date},
        )
        if existing is None:
            session.add(
                PriceHistory(
                    security_id=security.id,
                    date=price_date,
                    close_price=close_price,
                )
            )
            inserted += 1
    return inserted


def store_fx_rates(
    session: Session,
    base_currency: str,
    quote_currency: str,
    history: pd.DataFrame,
) -> int:
    inserted = 0
    base_currency = base_currency.upper()
    quote_currency = quote_currency.upper()

    for rate_date, rate in _iter_close_prices(history):
        existing = session.get(
            FxRateHistory,
            {
                "base_currency_code": base_currency,
                "quote_currency_code": quote_currency,
                "date": rate_date,
            },
        )
        if existing is None:
            session.add(
                FxRateHistory(
                    base_currency_code=base_currency,
                    quote_currency_code=quote_currency,
                    date=rate_date,
                    rate=rate,
                )
            )
            inserted += 1
    return inserted


def list_tracked_securities(session: Session) -> list[Security]:
    return session.scalars(
        select(Security)
        .join(Transaction, Transaction.security_id == Security.id)
        .where(Security.asset_class != AssetClass.CASH)
        .order_by(Security.ticker)
        .distinct()
    ).all()


def list_required_fx_pairs(session: Session) -> list[tuple[str, str]]:
    rows = session.execute(
        select(Security.currency_code, Account.currency_code)
        .join(Transaction, Transaction.security_id == Security.id)
        .join(Portfolio, Transaction.portfolio_id == Portfolio.id)
        .join(Account, Portfolio.account_id == Account.id)
        .where(Security.currency_code != Account.currency_code)
        .distinct()
    ).all()
    return sorted(
        {
            (security_currency.upper(), account_currency.upper())
            for security_currency, account_currency in rows
        }
    )


def yahoo_fx_symbol(base_currency: str, quote_currency: str) -> str:
    return f"{base_currency.upper()}{quote_currency.upper()}=X"


def market_data_summary() -> pd.DataFrame:
    session_factory = get_session_factory()
    with session_factory() as session:
        security_rows = session.execute(
            select(
                Security.ticker,
                Security.name,
                Security.currency_code,
                func.max(PriceHistory.date),
            )
            .join(PriceHistory, PriceHistory.security_id == Security.id, isouter=True)
            .group_by(Security.id)
            .order_by(Security.ticker)
        ).all()

        fx_rows = session.execute(
            select(
                FxRateHistory.base_currency_code,
                FxRateHistory.quote_currency_code,
                func.max(FxRateHistory.date),
            )
            .group_by(
                FxRateHistory.base_currency_code,
                FxRateHistory.quote_currency_code,
            )
            .order_by(
                FxRateHistory.base_currency_code,
                FxRateHistory.quote_currency_code,
            )
        ).all()

    rows = [
        {
            "Type": "Security",
            "Symbol": ticker,
            "Name": name,
            "Currency": currency_code,
            "Latest Date": latest_date.isoformat() if latest_date else "",
        }
        for ticker, name, currency_code, latest_date in security_rows
    ]
    rows.extend(
        {
            "Type": "FX",
            "Symbol": yahoo_fx_symbol(base_currency, quote_currency),
            "Name": f"{base_currency}/{quote_currency}",
            "Currency": quote_currency,
            "Latest Date": latest_date.isoformat() if latest_date else "",
        }
        for base_currency, quote_currency, latest_date in fx_rows
    )
    return pd.DataFrame(rows, columns=["Type", "Symbol", "Name", "Currency", "Latest Date"])


def _next_security_price_date(
    session: Session,
    security: Security,
    fallback_start_date: date,
) -> date:
    latest_date = session.scalar(
        select(func.max(PriceHistory.date)).where(PriceHistory.security_id == security.id)
    )
    if latest_date is None:
        return fallback_start_date
    return latest_date + timedelta(days=1)


def _next_fx_rate_date(
    session: Session,
    base_currency: str,
    quote_currency: str,
    fallback_start_date: date,
) -> date:
    latest_date = session.scalar(
        select(func.max(FxRateHistory.date)).where(
            FxRateHistory.base_currency_code == base_currency.upper(),
            FxRateHistory.quote_currency_code == quote_currency.upper(),
        )
    )
    if latest_date is None:
        return fallback_start_date
    return latest_date + timedelta(days=1)


def _iter_close_prices(history: pd.DataFrame) -> list[tuple[date, Decimal]]:
    if history.empty:
        return []

    close_values = _close_series(history).dropna()
    prices: list[tuple[date, Decimal]] = []
    for index, value in close_values.items():
        price_date = pd.Timestamp(index).date()
        prices.append((price_date, Decimal(str(value))))
    return prices


def _close_series(history: pd.DataFrame) -> pd.Series:
    close_column: Any = history["Close"]
    if isinstance(close_column, pd.DataFrame):
        return close_column.iloc[:, 0]
    return close_column
