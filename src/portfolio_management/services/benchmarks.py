from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd
from sqlalchemy import select

from portfolio_management.db.models import Benchmark
from portfolio_management.db.session import get_session_factory
from portfolio_management.services.accounts import parse_choice_id
from portfolio_management.services.analytics import LIVE_MODE, twr_curve
from portfolio_management.services.db_performance import benchmark_price_history
from portfolio_management.services.market_data import HistoryFetcher, fetch_yfinance_history


def benchmark_choices() -> list[str]:
    session_factory = get_session_factory()
    with session_factory() as session:
        benchmarks = session.scalars(select(Benchmark).order_by(Benchmark.ticker)).all()
    return [f"{benchmark.id} | {benchmark.ticker} / {benchmark.name}" for benchmark in benchmarks]


def default_benchmark_choice() -> str | None:
    choices = benchmark_choices()
    return choices[0] if choices else None


def benchmark_overlay(
    benchmark_choice: str | int | None,
    account_mode: str = LIVE_MODE,
    fetcher: HistoryFetcher | None = None,
    portfolio_id: int | None = None,
) -> pd.DataFrame:
    portfolio_curve = twr_curve(
        account_mode=account_mode,
        portfolio_id=portfolio_id,
    )
    portfolio_records = [
        {
            "Date": row["Date"],
            "Series": "Portfolio",
            "Index": float((Decimal(str(row["TWR"])) + Decimal("1")) * Decimal("100")),
        }
        for _, row in portfolio_curve.iterrows()
    ]

    benchmark_id = parse_choice_id(benchmark_choice)
    if benchmark_id is None or portfolio_curve.empty:
        return _overlay_dataframe(portfolio_records)

    session_factory = get_session_factory()
    with session_factory() as session:
        benchmark = session.get(Benchmark, benchmark_id)
        if benchmark is None:
            return _overlay_dataframe(portfolio_records)
        ticker = benchmark.ticker

    start_date = date.fromisoformat(str(portfolio_curve.iloc[0]["Date"]))
    end_date = date.fromisoformat(str(portfolio_curve.iloc[-1]["Date"]))
    local_history = benchmark_price_history(ticker, start_date, end_date)
    if not local_history.empty:
        benchmark_records = _normalise_local_benchmark_history(local_history)
    else:
        history = (fetcher or fetch_yfinance_history)(ticker, start_date, end_date)
        benchmark_records = _normalise_benchmark_history(history)
    return _overlay_dataframe(portfolio_records + benchmark_records)


def _normalise_benchmark_history(history: pd.DataFrame) -> list[dict[str, object]]:
    if history.empty:
        return []
    close_values = history["Close"]
    if isinstance(close_values, pd.DataFrame):
        close_values = close_values.iloc[:, 0]
    close_values = close_values.dropna()
    if close_values.empty:
        return []

    first_close = Decimal(str(close_values.iloc[0]))
    if first_close == 0:
        return []

    return [
        {
            "Date": pd.Timestamp(index).date().isoformat(),
            "Series": "Benchmark",
            "Index": float((Decimal(str(value)) / first_close) * Decimal("100")),
        }
        for index, value in close_values.items()
    ]


def _normalise_local_benchmark_history(history: pd.DataFrame) -> list[dict[str, object]]:
    clean = history.dropna(subset=["Close"])
    if clean.empty or clean.iloc[0]["Close"] == 0:
        return []
    first_close = Decimal(str(clean.iloc[0]["Close"]))
    return [
        {
            "Date": str(row["Date"]),
            "Series": "Benchmark",
            "Index": float((Decimal(str(row["Close"])) / first_close) * Decimal("100")),
        }
        for _, row in clean.iterrows()
    ]


def _overlay_dataframe(records: list[dict[str, object]]) -> pd.DataFrame:
    return pd.DataFrame(records, columns=["Date", "Series", "Index"])
