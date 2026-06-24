from __future__ import annotations

from datetime import date
from math import sqrt

import numpy as np
import pandas as pd
from scipy.optimize import brentq

from portfolio_management.services.analytics import LIVE_MODE
from portfolio_management.services.db_performance import (
    asset_price_history,
    cash_flow_history,
    portfolio_value_history,
)

TRADING_DAYS = 252
STRESS_PERIODS = {
    "COVID Crash": (date(2020, 2, 19), date(2020, 3, 23)),
    "2022 Rate Shock": (date(2022, 1, 3), date(2022, 10, 12)),
    "2023 Banking Stress": (date(2023, 3, 8), date(2023, 3, 24)),
}


def calculate_twr(values: pd.DataFrame, cash_flows: pd.DataFrame) -> pd.DataFrame:
    if values.empty:
        return pd.DataFrame(columns=["Date", "TWR"])
    frame = _dated_values(values)
    flows = _dated_flows(cash_flows)
    frame["Cash Flow"] = frame["Date"].map(flows).fillna(0.0)
    previous = frame["Portfolio Value"].shift(1)
    daily_return = (frame["Portfolio Value"] - previous - frame["Cash Flow"]) / previous
    daily_return = daily_return.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    frame["TWR"] = (1.0 + daily_return).cumprod() - 1.0
    return frame[["Date", "TWR"]].assign(Date=lambda data: data["Date"].dt.date.astype(str))


def calculate_mwr(values: pd.DataFrame, cash_flows: pd.DataFrame) -> pd.DataFrame:
    if values.empty:
        return pd.DataFrame(columns=["Date", "MWR"])
    frame = _dated_values(values)
    flows = _dated_flows(cash_flows)
    records = []
    for _, row in frame.iterrows():
        end_date = row["Date"]
        dated_flows = [
            (flow_date, -amount)
            for flow_date, amount in flows.items()
            if flow_date <= end_date
        ]
        dated_flows.append((end_date, float(row["Portfolio Value"])))
        records.append({"Date": end_date.date().isoformat(), "MWR": xirr(dated_flows)})
    return pd.DataFrame(records, columns=["Date", "MWR"])


def xirr(cash_flows: list[tuple[pd.Timestamp, float]]) -> float:
    non_zero = [(pd.Timestamp(day), amount) for day, amount in cash_flows if amount != 0]
    if not non_zero or not any(amount < 0 for _, amount in non_zero):
        return float("nan")
    if not any(amount > 0 for _, amount in non_zero):
        return float("nan")
    origin = min(day for day, _ in non_zero)

    def npv(rate: float) -> float:
        return sum(
            amount / ((1.0 + rate) ** ((day - origin).days / 365.0))
            for day, amount in non_zero
        )

    try:
        return float(brentq(npv, -0.999999, 1_000.0, maxiter=500))
    except ValueError:
        return float("nan")


def drawdown_curve(values: pd.DataFrame) -> pd.DataFrame:
    if values.empty:
        return pd.DataFrame(columns=["Date", "Drawdown"])
    frame = _dated_values(values)
    peak = frame["Portfolio Value"].cummax()
    frame["Drawdown"] = (frame["Portfolio Value"] / peak) - 1.0
    frame.loc[peak == 0, "Drawdown"] = 0.0
    return frame[["Date", "Drawdown"]].assign(
        Date=lambda data: data["Date"].dt.date.astype(str)
    )


def risk_metrics(
    portfolio_returns: pd.Series,
    benchmark_returns: pd.Series | None = None,
    risk_free_rate: float = 0.04,
) -> dict[str, float]:
    portfolio = pd.Series(portfolio_returns, dtype=float).dropna()
    benchmark = (
        pd.Series(benchmark_returns, dtype=float).dropna()
        if benchmark_returns is not None
        else pd.Series(dtype=float)
    )
    volatility = float(portfolio.std(ddof=1) * sqrt(TRADING_DAYS)) if len(portfolio) > 1 else np.nan
    annual_return = float(portfolio.mean() * TRADING_DAYS) if not portfolio.empty else np.nan
    downside = portfolio[portfolio < 0]
    downside_deviation = (
        float(downside.std(ddof=1) * sqrt(TRADING_DAYS)) if len(downside) > 1 else np.nan
    )
    sharpe = (
        (annual_return - risk_free_rate) / volatility
        if volatility and not np.isnan(volatility)
        else np.nan
    )
    sortino = (
        (annual_return - risk_free_rate) / downside_deviation
        if downside_deviation and not np.isnan(downside_deviation)
        else np.nan
    )
    beta = alpha = np.nan
    if not benchmark.empty:
        aligned = pd.concat(
            [portfolio.rename("portfolio"), benchmark.rename("benchmark")],
            axis=1,
            join="inner",
        ).dropna()
        benchmark_variance = aligned["benchmark"].var(ddof=1)
        if len(aligned) > 1 and benchmark_variance != 0:
            beta = float(aligned.cov().loc["portfolio", "benchmark"] / benchmark_variance)
            alpha = float(
                (
                    aligned["portfolio"].mean()
                    - (
                        risk_free_rate / TRADING_DAYS
                        + beta
                        * (
                            aligned["benchmark"].mean()
                            - risk_free_rate / TRADING_DAYS
                        )
                    )
                )
                * TRADING_DAYS
            )
    return {
        "Volatility": volatility,
        "Sharpe Ratio": sharpe,
        "Sortino Ratio": sortino,
        "Alpha": alpha,
        "Beta": beta,
    }


def benchmark_metrics(
    portfolio_returns: pd.Series,
    benchmark_returns: pd.Series,
) -> dict[str, float]:
    aligned = pd.concat(
        [
            pd.Series(portfolio_returns, dtype=float).rename("portfolio"),
            pd.Series(benchmark_returns, dtype=float).rename("benchmark"),
        ],
        axis=1,
        join="inner",
    ).dropna()
    if len(aligned) < 2:
        return {"Tracking Error": np.nan, "R-Squared": np.nan}
    active = aligned["portfolio"] - aligned["benchmark"]
    correlation = aligned["portfolio"].corr(aligned["benchmark"])
    return {
        "Tracking Error": float(active.std(ddof=1) * sqrt(TRADING_DAYS)),
        "R-Squared": float(correlation**2) if not np.isnan(correlation) else np.nan,
    }


def correlation_matrix(prices: pd.DataFrame) -> pd.DataFrame:
    if prices.empty:
        return pd.DataFrame()
    frame = prices.copy()
    frame["Date"] = pd.to_datetime(frame["Date"])
    wide = frame.pivot_table(index="Date", columns="Ticker", values="Close", aggfunc="last")
    return wide.sort_index().ffill().pct_change(fill_method=None).corr()


def historical_stress_tests(
    values: pd.DataFrame,
    periods: dict[str, tuple[date, date]] | None = None,
) -> pd.DataFrame:
    periods = periods or STRESS_PERIODS
    if values.empty:
        return pd.DataFrame(columns=["Period", "Return"])
    frame = _dated_values(values).set_index("Date")["Portfolio Value"]
    records = []
    for name, (start, end) in periods.items():
        sample = frame.loc[pd.Timestamp(start) : pd.Timestamp(end)]
        result = (
            float(sample.iloc[-1] / sample.iloc[0] - 1.0)
            if len(sample) >= 2 and sample.iloc[0] != 0
            else np.nan
        )
        records.append({"Period": name, "Return": result})
    return pd.DataFrame(records, columns=["Period", "Return"])


def performance_dataset(
    account_mode: str = LIVE_MODE,
    reporting_currency: str = "GBP",
    portfolio_id: int | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    values = portfolio_value_history(
        account_mode,
        reporting_currency,
        portfolio_id=portfolio_id,
    )
    flows = cash_flow_history(
        account_mode,
        reporting_currency,
        portfolio_id=portfolio_id,
    )
    prices = asset_price_history(account_mode, portfolio_id=portfolio_id)
    return values, flows, prices


def _dated_values(values: pd.DataFrame) -> pd.DataFrame:
    frame = values[["Date", "Portfolio Value"]].copy()
    frame["Date"] = pd.to_datetime(frame["Date"])
    return frame.sort_values("Date").drop_duplicates("Date", keep="last")


def _dated_flows(cash_flows: pd.DataFrame) -> pd.Series:
    if cash_flows.empty:
        return pd.Series(dtype=float)
    frame = cash_flows[["Date", "Cash Flow"]].copy()
    frame["Date"] = pd.to_datetime(frame["Date"])
    return frame.groupby("Date")["Cash Flow"].sum()
