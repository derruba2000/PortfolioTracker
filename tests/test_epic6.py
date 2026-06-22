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
from portfolio_management.services.analytics import tax_prep_report
from portfolio_management.services.benchmarks import benchmark_overlay
from portfolio_management.services.rebalancing import (
    create_target_allocation,
    rebalance_report,
    target_allocations,
)


def _patch_session(monkeypatch, engine) -> None:
    factory = lambda: sessionmaker(bind=engine, expire_on_commit=False, future=True)
    monkeypatch.setattr("portfolio_management.services.analytics.get_session_factory", factory)
    monkeypatch.setattr("portfolio_management.services.rebalancing.get_session_factory", factory)
    monkeypatch.setattr("portfolio_management.services.benchmarks.get_session_factory", factory)


def test_rebalance_report_compares_actual_to_targets(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        broker = Broker(name="Broker")
        account = Account(broker=broker, name="ISA", currency_code="USD")
        portfolio = Portfolio(account=account, name="Core")
        security = Security(
            ticker="AAPL",
            name="Apple Inc.",
            asset_class=AssetClass.EQUITY,
            currency_code="USD",
        )
        session.add_all(
            [
                Transaction(
                    portfolio=portfolio,
                    security=security,
                    date=datetime(2026, 1, 1),
                    type=TransactionType.BUY,
                    quantity=Decimal("10"),
                    price=Decimal("100"),
                    fees=Decimal("0"),
                    total_value=Decimal("1000"),
                    currency_exchange_rate=Decimal("1"),
                ),
                PriceHistory(
                    security=security,
                    date=date(2026, 1, 1),
                    close_price=Decimal("100"),
                ),
            ]
        )
        session.commit()
        account_choice = f"{account.id} | Broker / ISA"

    _patch_session(monkeypatch, engine)

    create_target_allocation(account_choice, "EQUITY", "60")
    targets = target_allocations(account_choice)
    report = rebalance_report(account_choice)

    assert targets.loc[0, "Asset Class"] == "EQUITY"
    assert targets.loc[0, "Target %"] == "60.0"
    assert report.loc[0, "Actual %"] == "100"
    assert report.loc[0, "Target %"] == "60.0"
    assert report.loc[0, "Action"] == "SELL"
    assert report.loc[0, "Trade Value"] == "400.0"


def test_tax_prep_report_includes_dividends(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        broker = Broker(name="Broker")
        account = Account(broker=broker, name="ISA", currency_code="USD")
        portfolio = Portfolio(account=account, name="Core")
        security = Security(
            ticker="AAPL",
            name="Apple Inc.",
            asset_class=AssetClass.EQUITY,
            currency_code="USD",
        )
        session.add(
            Transaction(
                portfolio=portfolio,
                security=security,
                date=datetime(2026, 1, 1),
                type=TransactionType.DIVIDEND,
                quantity=Decimal("1"),
                price=Decimal("5"),
                fees=Decimal("0"),
                total_value=Decimal("5"),
                currency_exchange_rate=Decimal("1"),
            )
        )
        session.commit()

    _patch_session(monkeypatch, engine)

    report = tax_prep_report(tax_year=2026)

    assert report.loc[0, "Type"] == "DIVIDEND"
    assert report.loc[0, "Amount"] == "5"


def test_benchmark_overlay_normalizes_benchmark(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        broker = Broker(name="Broker")
        account = Account(broker=broker, name="ISA", currency_code="USD")
        portfolio = Portfolio(account=account, name="Core")
        security = Security(
            ticker="AAPL",
            name="Apple Inc.",
            asset_class=AssetClass.EQUITY,
            currency_code="USD",
        )
        benchmark = Benchmark(ticker="SPY", name="S&P 500 ETF")
        session.add_all(
            [
                benchmark,
                Transaction(
                    portfolio=portfolio,
                    date=datetime(2026, 1, 1),
                    type=TransactionType.DEPOSIT,
                    quantity=Decimal("1000"),
                    price=Decimal("1"),
                    fees=Decimal("0"),
                    total_value=Decimal("1000"),
                    currency_exchange_rate=Decimal("1"),
                ),
                Transaction(
                    portfolio=portfolio,
                    security=security,
                    date=datetime(2026, 1, 1),
                    type=TransactionType.BUY,
                    quantity=Decimal("10"),
                    price=Decimal("100"),
                    fees=Decimal("0"),
                    total_value=Decimal("1000"),
                    currency_exchange_rate=Decimal("1"),
                ),
                PriceHistory(
                    security=security,
                    date=date(2026, 1, 1),
                    close_price=Decimal("100"),
                ),
            ]
        )
        session.commit()
        benchmark_choice = f"{benchmark.id} | SPY / S&P 500 ETF"

    _patch_session(monkeypatch, engine)

    def fetcher(symbol: str, start_date: date, end_date: date) -> pd.DataFrame:
        return pd.DataFrame(
            {"Close": [Decimal("100"), Decimal("110")]},
            index=pd.to_datetime(["2026-01-01", "2026-01-02"]),
        )

    overlay = benchmark_overlay(benchmark_choice, fetcher=fetcher)
    benchmark_rows = overlay[overlay["Series"] == "Benchmark"]

    assert list(benchmark_rows["Index"]) == [100.0, 110.0]
