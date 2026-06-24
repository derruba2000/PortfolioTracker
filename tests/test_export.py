from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from portfolio_management.db.base import Base
from portfolio_management.db.models import (
    Account,
    AssetClass,
    Benchmark,
    Broker,
    Portfolio,
    PriceHistory,
    Security,
    Transaction,
    TransactionType,
)
from portfolio_management.services.analytics import (
    ALL_ACCOUNTS_MODE,
    LIVE_MODE,
    SANDBOX_MODE,
)
from portfolio_management.services.csv_exports import (
    export_portfolio_correlations_csv,
    export_portfolio_kpis_csv,
    export_portfolio_time_series_csv,
    export_positions_csv,
    export_transactions_csv,
)
from portfolio_management.tabs import export


def test_import_market_data_logs_missing_paths(monkeypatch: object) -> None:
    logged: list[tuple[str, str]] = []

    def capture_error(*, pipeline_name: str, error_message: str) -> None:
        logged.append((pipeline_name, error_message))

    monkeypatch.setattr(export, "log_import_error", capture_error)

    prices_path, fx_path, status = export._import_market_data("", "")

    assert prices_path == ""
    assert fx_path == ""
    assert status == "Both the market prices and FX rates Delta table paths are required."
    assert logged == [("delta_market_data", status)]


def test_csv_exports_apply_account_scope_and_portfolio_filters(
    monkeypatch,
) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        broker = Broker(name="Broker")
        live_account = Account(broker=broker, name="Live", currency_code="USD")
        paper_account = Account(
            broker=broker,
            name="Paper",
            currency_code="USD",
            is_simulated=True,
        )
        live_portfolio = Portfolio(account=live_account, name="Live Portfolio")
        paper_portfolio = Portfolio(account=paper_account, name="Paper Portfolio")
        live_security = Security(
            ticker="LIVE",
            name="Live Security",
            asset_class=AssetClass.EQUITY,
            currency_code="USD",
        )
        paper_security = Security(
            ticker="PAPER",
            name="Paper Security",
            asset_class=AssetClass.EQUITY,
            currency_code="USD",
        )
        session.add_all(
            [
                Transaction(
                    portfolio=live_portfolio,
                    security=live_security,
                    date=datetime(2026, 1, 1),
                    type=TransactionType.BUY,
                    quantity=1,
                    price=Decimal("100"),
                    fees=Decimal("0"),
                    total_value=Decimal("100"),
                    currency_exchange_rate=Decimal("1"),
                ),
                Transaction(
                    portfolio=paper_portfolio,
                    security=paper_security,
                    date=datetime(2026, 1, 1),
                    type=TransactionType.BUY,
                    quantity=2,
                    price=Decimal("50"),
                    fees=Decimal("0"),
                    total_value=Decimal("100"),
                    currency_exchange_rate=Decimal("1"),
                ),
                PriceHistory(
                    security=live_security,
                    date=date(2026, 1, 2),
                    close=Decimal("110"),
                ),
                PriceHistory(
                    security=paper_security,
                    date=date(2026, 1, 2),
                    close=Decimal("55"),
                ),
            ]
        )
        session.flush()
        live_portfolio_id = live_portfolio.id
        session.commit()

    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    monkeypatch.setattr(
        "portfolio_management.services.analytics.get_session_factory",
        lambda: factory,
    )
    monkeypatch.setattr(
        "portfolio_management.services.csv_exports.get_session_factory",
        lambda: factory,
    )

    live_positions_path = export_positions_csv(
        LIVE_MODE,
        "USD",
        live_portfolio_id,
    )
    paper_transactions_path = export_transactions_csv(SANDBOX_MODE)
    all_transactions_path = export_transactions_csv(ALL_ACCOUNTS_MODE)

    live_positions = pd.read_csv(live_positions_path)
    paper_transactions = pd.read_csv(paper_transactions_path)
    all_transactions = pd.read_csv(all_transactions_path)

    assert list(live_positions["Ticker"]) == ["LIVE"]
    assert list(live_positions["Market Value"]) == [110]
    assert list(paper_transactions["Ticker"]) == ["PAPER"]
    assert list(paper_transactions["Account Type"]) == ["Paper/Sandbox/Test"]
    assert set(all_transactions["Ticker"]) == {"LIVE", "PAPER"}


def test_portfolio_kpi_export_has_one_row_per_portfolio_and_benchmark_columns(
    monkeypatch,
) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        broker = Broker(name="Broker")
        account = Account(broker=broker, name="Live", currency_code="USD")
        first = Portfolio(account=account, name="First")
        second = Portfolio(account=account, name="Second")
        session.add_all(
            [
                first,
                second,
                Benchmark(ticker="SPY", name="S&P 500"),
            ]
        )
        session.commit()

    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    monkeypatch.setattr(
        "portfolio_management.services.csv_exports.get_session_factory",
        lambda: factory,
    )

    values = pd.DataFrame(
        {
            "Date": ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"],
            "Portfolio Value": [100.0, 101.0, 100.0, 103.0],
        }
    )
    flows = pd.DataFrame(
        {"Date": ["2026-01-01"], "Cash Flow": [100.0]}
    )
    monkeypatch.setattr(
        "portfolio_management.services.csv_exports.performance_dataset",
        lambda *args, **kwargs: (values, flows, pd.DataFrame()),
    )
    monkeypatch.setattr(
        "portfolio_management.services.csv_exports.benchmark_overlay",
        lambda *args, **kwargs: pd.DataFrame(
            {
                "Date": [
                    "2026-01-01",
                    "2026-01-02",
                    "2026-01-03",
                    "2026-01-04",
                ],
                "Series": ["Benchmark"] * 4,
                "Index": [100.0, 100.5, 100.0, 101.0],
            }
        ),
    )

    export_path = export_portfolio_kpis_csv(
        LIVE_MODE,
        reporting_currency="USD",
        risk_free_rate=0.0,
    )
    kpis = pd.read_csv(export_path)

    assert list(kpis["Portfolio"]) == ["First", "Second"]
    assert list(kpis["Latest Portfolio Value"]) == [103.0, 103.0]
    assert "Volatility (%)" in kpis
    assert "Sharpe Ratio" in kpis
    assert "Sortino Ratio" in kpis
    assert "SPY Return (%)" in kpis
    assert "SPY Alpha (%)" in kpis
    assert "SPY Beta" in kpis
    assert "SPY Tracking Error (%)" in kpis
    assert "SPY R-Squared" in kpis


def test_correlation_and_time_series_exports_are_tabular_per_portfolio(
    monkeypatch,
) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        broker = Broker(name="Broker")
        account = Account(broker=broker, name="Live", currency_code="USD")
        portfolio = Portfolio(account=account, name="Core")
        session.add_all(
            [
                portfolio,
                Benchmark(ticker="SPY", name="S&P 500"),
            ]
        )
        session.flush()
        portfolio_id = portfolio.id
        session.commit()

    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    monkeypatch.setattr(
        "portfolio_management.services.csv_exports.get_session_factory",
        lambda: factory,
    )

    values = pd.DataFrame(
        {
            "Date": ["2026-01-01", "2026-01-02", "2026-01-03"],
            "Portfolio Value": [100.0, 102.0, 101.0],
        }
    )
    flows = pd.DataFrame(
        {"Date": ["2026-01-01"], "Cash Flow": [100.0]}
    )
    prices = pd.DataFrame(
        {
            "Date": [
                "2026-01-01",
                "2026-01-02",
                "2026-01-03",
                "2026-01-01",
                "2026-01-02",
                "2026-01-03",
            ],
            "Ticker": ["AAA", "AAA", "AAA", "BBB", "BBB", "BBB"],
            "Close": [100.0, 101.0, 103.0, 200.0, 202.0, 206.0],
        }
    )
    monkeypatch.setattr(
        "portfolio_management.services.csv_exports.performance_dataset",
        lambda *args, **kwargs: (values, flows, prices),
    )
    monkeypatch.setattr(
        "portfolio_management.services.csv_exports.benchmark_overlay",
        lambda *args, **kwargs: pd.DataFrame(
            {
                "Date": ["2026-01-01", "2026-01-02", "2026-01-03"],
                "Series": ["Benchmark"] * 3,
                "Index": [100.0, 101.0, 102.0],
            }
        ),
    )

    correlation_path = export_portfolio_correlations_csv(
        LIVE_MODE,
        portfolio_id=portfolio_id,
    )
    time_series_path = export_portfolio_time_series_csv(
        LIVE_MODE,
        "USD",
        portfolio_id=portfolio_id,
    )
    correlations = pd.read_csv(correlation_path)
    time_series = pd.read_csv(time_series_path)

    assert list(correlations["Symbol"]) == ["AAA", "BBB"]
    assert {"AAA", "BBB"} <= set(correlations.columns)
    assert set(correlations["Portfolio"]) == {"Core"}
    assert list(time_series["Portfolio Value"]) == [100.0, 102.0, 101.0]
    assert "Daily Return" in time_series
    assert "TWR" in time_series
    assert "MWR" in time_series
    assert "Drawdown" in time_series
    assert "SPY Growth Index" in time_series
    assert "SPY Daily Return" in time_series
    assert "SPY Relative Performance" in time_series
