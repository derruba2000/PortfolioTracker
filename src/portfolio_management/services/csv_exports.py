from __future__ import annotations

from datetime import date
from pathlib import Path
from tempfile import NamedTemporaryFile

import numpy as np
import pandas as pd
from sqlalchemy import select

from portfolio_management.db.models import (
    Account,
    Benchmark,
    Broker,
    Portfolio,
    Security,
    Transaction,
)
from portfolio_management.services.benchmarks import benchmark_overlay
from portfolio_management.services.performance import (
    benchmark_metrics,
    calculate_mwr,
    calculate_twr,
    correlation_matrix,
    drawdown_curve,
    performance_dataset,
    risk_metrics,
)
from portfolio_management.db.session import get_session_factory
from portfolio_management.services.analytics import (
    ALL_ACCOUNTS_MODE,
    LIVE_MODE,
    SANDBOX_MODE,
    current_positions,
)


def export_positions_csv(
    account_mode: str = LIVE_MODE,
    reporting_currency: str = "GBP",
    portfolio_id: int | None = None,
) -> str:
    positions = current_positions(
        account_mode=account_mode,
        reporting_currency=reporting_currency,
        portfolio_id=portfolio_id,
    )
    filename = _export_filename("positions", account_mode, portfolio_id)
    return _write_dataframe_csv(positions, filename)


def export_transactions_csv(
    account_mode: str = LIVE_MODE,
    portfolio_id: int | None = None,
) -> str:
    session_factory = get_session_factory()
    with session_factory() as session:
        statement = (
            select(Transaction, Portfolio, Account, Broker, Security)
            .join(Transaction.portfolio)
            .join(Portfolio.account)
            .join(Account.broker)
            .join(Transaction.security, isouter=True)
            .where(Broker.is_active.is_(True))
            .where(Account.is_active.is_(True))
            .where(Portfolio.is_active.is_(True))
            .order_by(Transaction.date.desc(), Transaction.id.desc())
        )
        if account_mode == SANDBOX_MODE:
            statement = statement.where(Account.is_simulated.is_(True))
        elif account_mode != ALL_ACCOUNTS_MODE:
            statement = statement.where(Account.is_simulated.is_(False))
        if portfolio_id is not None:
            statement = statement.where(Portfolio.id == portfolio_id)
        rows = session.execute(statement).all()

    transactions = pd.DataFrame(
        [
            {
                "ID": transaction.id,
                "Date": transaction.date.date().isoformat(),
                "Broker": broker.name,
                "Account": account.name,
                "Account Type": "Paper/Sandbox/Test" if account.is_simulated else "Live",
                "Portfolio": portfolio.name,
                "Portfolio URL": portfolio.portfolio_url or "",
                "Ticker": security.ticker if security else "",
                "Security Name": security.name if security else "",
                "Type": transaction.type.value,
                "Description": transaction.description or "",
                "Quantity": str(transaction.quantity),
                "Price": str(transaction.price),
                "Fees": str(transaction.fees),
                "Total Value": str(transaction.total_value),
                "FX Rate": str(transaction.currency_exchange_rate),
            }
            for transaction, portfolio, account, broker, security in rows
        ],
        columns=[
            "ID",
            "Date",
            "Broker",
            "Account",
            "Account Type",
            "Portfolio",
            "Portfolio URL",
            "Ticker",
            "Security Name",
            "Type",
            "Description",
            "Quantity",
            "Price",
            "Fees",
            "Total Value",
            "FX Rate",
        ],
    )
    filename = _export_filename("transactions", account_mode, portfolio_id)
    return _write_dataframe_csv(transactions, filename)


def export_portfolio_kpis_csv(
    account_mode: str = LIVE_MODE,
    reporting_currency: str = "GBP",
    portfolio_id: int | None = None,
    risk_free_rate: float = 0.04,
) -> str:
    portfolios, benchmarks = _portfolio_and_benchmark_rows(account_mode, portfolio_id)
    records: list[dict[str, object]] = []

    for portfolio, account, broker in portfolios:
        values, flows, _ = performance_dataset(
            account_mode,
            reporting_currency,
            portfolio_id=portfolio.id,
        )
        twr = calculate_twr(values, flows)
        mwr = calculate_mwr(values, flows)
        drawdowns = drawdown_curve(values)
        portfolio_returns = _daily_returns(values, "Portfolio Value")
        standalone = risk_metrics(
            portfolio_returns,
            risk_free_rate=risk_free_rate,
        )

        record: dict[str, object] = {
            "Portfolio ID": portfolio.id,
            "Broker": broker.name,
            "Account": account.name,
            "Account Type": "Paper/Sandbox/Test" if account.is_simulated else "Live",
            "Portfolio": portfolio.name,
            "Reporting Currency": reporting_currency.upper(),
            "Latest Portfolio Value": _last_value(values, "Portfolio Value"),
            "TWR (%)": _last_value(twr, "TWR", scale=100),
            "MWR Annualized (%)": _last_value(mwr, "MWR", scale=100),
            "Maximum Drawdown (%)": _minimum_value(drawdowns, "Drawdown", scale=100),
            "Volatility (%)": _scaled_metric(standalone["Volatility"], 100),
            "Sharpe Ratio": standalone["Sharpe Ratio"],
            "Sortino Ratio": standalone["Sortino Ratio"],
        }

        for benchmark in benchmarks:
            prefix = benchmark.ticker
            try:
                overlay = benchmark_overlay(
                    benchmark.id,
                    account_mode=account_mode,
                    portfolio_id=portfolio.id,
                )
                benchmark_index = overlay[overlay["Series"] == "Benchmark"].copy()
                benchmark_returns = _daily_returns(benchmark_index, "Index")
                comparison_risk = risk_metrics(
                    portfolio_returns,
                    benchmark_returns,
                    risk_free_rate,
                )
                comparison = benchmark_metrics(portfolio_returns, benchmark_returns)
                record[f"{prefix} Return (%)"] = _period_return(
                    benchmark_index,
                    "Index",
                )
                record[f"{prefix} Alpha (%)"] = _scaled_metric(
                    comparison_risk["Alpha"],
                    100,
                )
                record[f"{prefix} Beta"] = comparison_risk["Beta"]
                record[f"{prefix} Tracking Error (%)"] = _scaled_metric(
                    comparison["Tracking Error"],
                    100,
                )
                record[f"{prefix} R-Squared"] = comparison["R-Squared"]
            except Exception:
                record[f"{prefix} Return (%)"] = np.nan
                record[f"{prefix} Alpha (%)"] = np.nan
                record[f"{prefix} Beta"] = np.nan
                record[f"{prefix} Tracking Error (%)"] = np.nan
                record[f"{prefix} R-Squared"] = np.nan
        records.append(record)

    kpis = pd.DataFrame(records)
    filename = _export_filename("portfolio_kpis", account_mode, portfolio_id)
    return _write_dataframe_csv(kpis, filename)


def export_portfolio_correlations_csv(
    account_mode: str = LIVE_MODE,
    portfolio_id: int | None = None,
) -> str:
    portfolios, _ = _portfolio_and_benchmark_rows(account_mode, portfolio_id)
    matrices: list[pd.DataFrame] = []
    for portfolio, account, broker in portfolios:
        _, _, prices = performance_dataset(
            account_mode,
            account.currency_code,
            portfolio_id=portfolio.id,
        )
        matrix = correlation_matrix(prices)
        if matrix.empty:
            continue
        tabular = matrix.reset_index().rename(columns={"Ticker": "Symbol"})
        if "Symbol" not in tabular.columns:
            tabular = tabular.rename(columns={tabular.columns[0]: "Symbol"})
        tabular.insert(0, "Portfolio", portfolio.name)
        tabular.insert(0, "Account", account.name)
        tabular.insert(0, "Broker", broker.name)
        tabular.insert(0, "Portfolio ID", portfolio.id)
        matrices.append(tabular)

    correlations = pd.concat(matrices, ignore_index=True, sort=False) if matrices else pd.DataFrame(
        columns=["Portfolio ID", "Broker", "Account", "Portfolio", "Symbol"]
    )
    filename = _export_filename("portfolio_correlations", account_mode, portfolio_id)
    return _write_dataframe_csv(correlations, filename)


def export_portfolio_time_series_csv(
    account_mode: str = LIVE_MODE,
    reporting_currency: str = "GBP",
    portfolio_id: int | None = None,
) -> str:
    portfolios, benchmarks = _portfolio_and_benchmark_rows(account_mode, portfolio_id)
    series_rows: list[pd.DataFrame] = []
    for portfolio, account, broker in portfolios:
        values, flows, _ = performance_dataset(
            account_mode,
            reporting_currency,
            portfolio_id=portfolio.id,
        )
        if values.empty:
            continue
        frame = values.copy()
        frame["Date"] = pd.to_datetime(frame["Date"])
        twr = calculate_twr(values, flows)
        mwr = calculate_mwr(values, flows)
        drawdowns = drawdown_curve(values)
        for metric_frame, metric_column in (
            (twr, "TWR"),
            (mwr, "MWR"),
            (drawdowns, "Drawdown"),
        ):
            metric = metric_frame.copy()
            metric["Date"] = pd.to_datetime(metric["Date"])
            frame = frame.merge(metric[["Date", metric_column]], on="Date", how="left")
        frame["Daily Return"] = frame["Portfolio Value"].pct_change(fill_method=None)
        frame["Portfolio Growth Index"] = _growth_index(frame["Portfolio Value"])

        for benchmark in benchmarks:
            try:
                overlay = benchmark_overlay(
                    benchmark.id,
                    account_mode=account_mode,
                    portfolio_id=portfolio.id,
                )
                benchmark_rows = overlay[overlay["Series"] == "Benchmark"][
                    ["Date", "Index"]
                ].copy()
                benchmark_rows["Date"] = pd.to_datetime(benchmark_rows["Date"])
                benchmark_rows = benchmark_rows.drop_duplicates("Date", keep="last")
                benchmark_rows = benchmark_rows.rename(
                    columns={"Index": f"{benchmark.ticker} Growth Index"}
                )
                frame = frame.merge(benchmark_rows, on="Date", how="left")
                benchmark_column = f"{benchmark.ticker} Growth Index"
                frame[benchmark_column] = frame[benchmark_column].ffill()
                frame[f"{benchmark.ticker} Daily Return"] = frame[
                    benchmark_column
                ].pct_change(fill_method=None)
                frame[f"{benchmark.ticker} Relative Performance"] = (
                    frame["Portfolio Growth Index"] / frame[benchmark_column] - 1
                )
            except Exception:
                frame[f"{benchmark.ticker} Growth Index"] = np.nan
                frame[f"{benchmark.ticker} Daily Return"] = np.nan
                frame[f"{benchmark.ticker} Relative Performance"] = np.nan

        frame["Date"] = frame["Date"].dt.date.astype(str)
        frame.insert(0, "Reporting Currency", reporting_currency.upper())
        frame.insert(0, "Portfolio", portfolio.name)
        frame.insert(0, "Account", account.name)
        frame.insert(0, "Broker", broker.name)
        frame.insert(0, "Portfolio ID", portfolio.id)
        series_rows.append(frame)

    time_series = (
        pd.concat(series_rows, ignore_index=True, sort=False)
        if series_rows
        else pd.DataFrame(
            columns=[
                "Portfolio ID",
                "Broker",
                "Account",
                "Portfolio",
                "Reporting Currency",
                "Date",
                "Portfolio Value",
                "Daily Return",
                "TWR",
                "MWR",
                "Drawdown",
                "Portfolio Growth Index",
            ]
        )
    )
    filename = _export_filename("portfolio_time_series", account_mode, portfolio_id)
    return _write_dataframe_csv(time_series, filename)


def _portfolio_and_benchmark_rows(
    account_mode: str,
    portfolio_id: int | None,
) -> tuple[list[tuple[Portfolio, Account, Broker]], list[Benchmark]]:
    session_factory = get_session_factory()
    with session_factory() as session:
        statement = (
            select(Portfolio, Account, Broker)
            .join(Portfolio.account)
            .join(Account.broker)
            .where(Broker.is_active.is_(True))
            .where(Account.is_active.is_(True))
            .where(Portfolio.is_active.is_(True))
            .order_by(Broker.name, Account.name, Portfolio.name)
        )
        if account_mode == SANDBOX_MODE:
            statement = statement.where(Account.is_simulated.is_(True))
        elif account_mode != ALL_ACCOUNTS_MODE:
            statement = statement.where(Account.is_simulated.is_(False))
        if portfolio_id is not None:
            statement = statement.where(Portfolio.id == portfolio_id)
        portfolios = list(session.execute(statement).all())
        benchmarks = list(session.scalars(select(Benchmark).order_by(Benchmark.ticker)).all())
    return portfolios, benchmarks


def _daily_returns(dataframe: pd.DataFrame, value_column: str) -> pd.Series:
    if dataframe.empty or value_column not in dataframe.columns:
        return pd.Series(dtype=float)
    frame = dataframe[["Date", value_column]].copy()
    frame["Date"] = pd.to_datetime(frame["Date"])
    return (
        frame.dropna(subset=[value_column])
        .drop_duplicates("Date", keep="last")
        .set_index("Date")[value_column]
        .pct_change(fill_method=None)
        .dropna()
    )


def _last_value(
    dataframe: pd.DataFrame,
    column: str,
    scale: float = 1,
) -> float:
    if dataframe.empty or column not in dataframe.columns:
        return np.nan
    values = dataframe[column].dropna()
    return float(values.iloc[-1] * scale) if not values.empty else np.nan


def _minimum_value(
    dataframe: pd.DataFrame,
    column: str,
    scale: float = 1,
) -> float:
    if dataframe.empty or column not in dataframe.columns:
        return np.nan
    values = dataframe[column].dropna()
    return float(values.min() * scale) if not values.empty else np.nan


def _period_return(dataframe: pd.DataFrame, column: str) -> float:
    if dataframe.empty or column not in dataframe.columns:
        return np.nan
    values = dataframe[column].dropna()
    if len(values) < 2 or values.iloc[0] == 0:
        return np.nan
    return float((values.iloc[-1] / values.iloc[0] - 1) * 100)


def _scaled_metric(value: float, scale: float) -> float:
    return float(value * scale) if value is not None and np.isfinite(value) else np.nan


def _growth_index(values: pd.Series) -> pd.Series:
    clean = values.astype(float)
    first_valid = clean.dropna()
    if first_valid.empty or first_valid.iloc[0] == 0:
        return pd.Series(np.nan, index=values.index)
    return clean / first_valid.iloc[0] * 100


def _write_dataframe_csv(dataframe: pd.DataFrame, filename: str) -> str:
    with NamedTemporaryFile(
        mode="w",
        suffix=".csv",
        prefix=f"{Path(filename).stem}_",
        delete=False,
        newline="",
        encoding="utf-8",
    ) as csv_file:
        dataframe.to_csv(csv_file.name, index=False)
        return csv_file.name


def _export_filename(
    data_type: str,
    account_mode: str,
    portfolio_id: int | None,
) -> str:
    scope = {
        LIVE_MODE: "live",
        SANDBOX_MODE: "paper_sandbox_test",
        ALL_ACCOUNTS_MODE: "all_accounts",
    }.get(account_mode, "live")
    portfolio = f"portfolio_{portfolio_id}" if portfolio_id is not None else "all_portfolios"
    return f"{data_type}_{scope}_{portfolio}_{date.today().isoformat()}.csv"
