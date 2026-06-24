from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf
from deltalake import DeltaTable
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
from portfolio_management.services.import_errors import add_import_error, log_import_error


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


@dataclass(frozen=True)
class DeltaImportResult:
    prices_upserted: int = 0
    fx_rates_upserted: int = 0
    skipped: tuple[str, ...] = ()

    @property
    def message(self) -> str:
        skipped = f" Skipped: {', '.join(self.skipped)}." if self.skipped else ""
        return (
            f"Imported {self.prices_upserted} price row(s) and "
            f"{self.fx_rates_upserted} FX row(s).{skipped}"
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
    for row in _iter_ohlcv_rows(history):
        existing = session.get(
            PriceHistory,
            {"security_id": security.id, "date": row["date"]},
        )
        if existing is None:
            session.add(
                PriceHistory(
                    security_id=security.id,
                    symbol=security.ticker,
                    **row,
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

    symbol = yahoo_fx_symbol(base_currency, quote_currency)
    for row in _iter_ohlcv_rows(history):
        existing = session.get(
            FxRateHistory,
            {
                "base_currency_code": base_currency,
                "quote_currency_code": quote_currency,
                "date": row["date"],
            },
        )
        if existing is None:
            session.add(
                FxRateHistory(
                    base_currency_code=base_currency,
                    quote_currency_code=quote_currency,
                    symbol=symbol,
                    **row,
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


def import_market_data_from_delta(
    market_prices_path: str | Path | None,
    fx_rates_path: str | Path | None,
) -> DeltaImportResult:
    session_factory = get_session_factory()
    try:
        with session_factory() as session:
            result = import_market_data_from_delta_for_session(
                session,
                market_prices_path=market_prices_path,
                fx_rates_path=fx_rates_path,
            )
            session.commit()
        return result
    except Exception as exc:
        log_import_error(
            pipeline_name="delta_market_data",
            error_message=str(exc),
        )
        raise


def import_market_data_from_delta_for_session(
    session: Session,
    market_prices_path: str | Path | None,
    fx_rates_path: str | Path | None,
) -> DeltaImportResult:
    prices_upserted = 0
    fx_rates_upserted = 0
    skipped: list[str] = []

    if market_prices_path:
        prices = _read_delta_ohlcv(market_prices_path)
        securities = {
            security.ticker.upper(): security for security in session.scalars(select(Security)).all()
        }
        for row in prices:
            symbol = row.pop("symbol")
            security = securities.get(symbol.upper())
            if security is None:
                message = f"unknown price symbol {symbol}"
                skipped.append(message)
                add_import_error(
                    session,
                    pipeline_name="delta_market_prices",
                    error_message=message,
                )
                continue
            existing = session.get(
                PriceHistory,
                {"security_id": security.id, "date": row["date"]},
            )
            if existing is None:
                session.add(
                    PriceHistory(
                        security_id=security.id,
                        symbol=security.ticker,
                        **row,
                    )
                )
            else:
                _apply_ohlcv(existing, security.ticker, row)
            prices_upserted += 1

    if fx_rates_path:
        fx_rates = _read_delta_ohlcv(fx_rates_path)
        for row in fx_rates:
            symbol = row.pop("symbol")
            try:
                base_currency, quote_currency = parse_fx_symbol(symbol)
            except ValueError as exc:
                message = str(exc)
                skipped.append(message)
                add_import_error(
                    session,
                    pipeline_name="delta_fx_rates",
                    error_message=message,
                )
                continue
            existing = session.get(
                FxRateHistory,
                {
                    "base_currency_code": base_currency,
                    "quote_currency_code": quote_currency,
                    "date": row["date"],
                },
            )
            if existing is None:
                session.add(
                    FxRateHistory(
                        base_currency_code=base_currency,
                        quote_currency_code=quote_currency,
                        symbol=symbol,
                        **row,
                    )
                )
            else:
                _apply_ohlcv(existing, symbol, row)
            fx_rates_upserted += 1

    if not market_prices_path:
        message = "market prices Delta path is not set"
        skipped.append(message)
        add_import_error(
            session,
            pipeline_name="delta_market_prices",
            error_message=message,
        )
    if not fx_rates_path:
        message = "FX rates Delta path is not set"
        skipped.append(message)
        add_import_error(
            session,
            pipeline_name="delta_fx_rates",
            error_message=message,
        )

    session.flush()
    return DeltaImportResult(
        prices_upserted=prices_upserted,
        fx_rates_upserted=fx_rates_upserted,
        skipped=tuple(skipped),
    )


def parse_fx_symbol(symbol: str) -> tuple[str, str]:
    normalized = symbol.strip().upper()
    if normalized.endswith("=X"):
        normalized = normalized[:-2]
    normalized = normalized.replace("/", "").replace("-", "").replace("_", "")
    if len(normalized) != 6 or not normalized.isalpha():
        raise ValueError(f"invalid FX symbol {symbol!r}")
    return normalized[:3], normalized[3:]


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
    return [(row["date"], row["close"]) for row in _iter_ohlcv_rows(history)]


def _iter_ohlcv_rows(history: pd.DataFrame) -> list[dict[str, Any]]:
    if history.empty:
        return []

    close_values = _history_series(history, "Close")
    rows: list[dict[str, Any]] = []
    for index, close_value in close_values.dropna().items():
        price_date = pd.Timestamp(index).date()
        rows.append(
            {
                "date": price_date,
                "open": _decimal_at(history, "Open", index),
                "high": _decimal_at(history, "High", index),
                "low": _decimal_at(history, "Low", index),
                "close": Decimal(str(close_value)),
                "volume": _decimal_at(history, "Volume", index),
            }
        )
    return rows


def _close_series(history: pd.DataFrame) -> pd.Series:
    return _history_series(history, "Close")


def _history_series(history: pd.DataFrame, column_name: str) -> pd.Series:
    if column_name not in history.columns and not isinstance(history.columns, pd.MultiIndex):
        return pd.Series(index=history.index, dtype="object")
    try:
        values: Any = history[column_name]
    except KeyError:
        return pd.Series(index=history.index, dtype="object")
    if isinstance(values, pd.DataFrame):
        return values.iloc[:, 0]
    return values


def _decimal_at(history: pd.DataFrame, column_name: str, index: Any) -> Decimal | None:
    series = _history_series(history, column_name)
    if series.empty:
        return None
    value = series.loc[index]
    if isinstance(value, pd.Series):
        value = value.iloc[0]
    if pd.isna(value):
        return None
    return Decimal(str(value))


def _read_delta_ohlcv(path: str | Path) -> list[dict[str, Any]]:
    frame = DeltaTable(str(path)).to_pandas()
    frame.columns = [str(column).strip().lower() for column in frame.columns]
    required = {"symbol", "date", "open", "high", "low", "close", "volume"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(
            f"Delta table {path} is missing required column(s): {', '.join(missing)}"
        )

    rows: list[dict[str, Any]] = []
    for record in frame[list(required)].to_dict(orient="records"):
        if pd.isna(record["symbol"]) or pd.isna(record["date"]) or pd.isna(record["close"]):
            raise ValueError(f"Delta table {path} contains a row without symbol, date, or close")
        rows.append(
            {
                "symbol": str(record["symbol"]).strip(),
                "date": pd.Timestamp(record["date"]).date(),
                "open": _optional_decimal(record["open"]),
                "high": _optional_decimal(record["high"]),
                "low": _optional_decimal(record["low"]),
                "close": Decimal(str(record["close"])),
                "volume": _optional_decimal(record["volume"]),
            }
        )
    return rows


def _optional_decimal(value: Any) -> Decimal | None:
    if pd.isna(value):
        return None
    return Decimal(str(value))


def _apply_ohlcv(target: PriceHistory | FxRateHistory, symbol: str, row: dict[str, Any]) -> None:
    target.symbol = symbol
    target.open = row["open"]
    target.high = row["high"]
    target.low = row["low"]
    target.close = row["close"]
    target.volume = row["volume"]
