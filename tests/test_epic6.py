from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pandas as pd
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from portfolio_management.db.base import Base
from portfolio_management.db.models import (
    Account,
    AccountStrategy,
    AssetClass,
    Benchmark,
    Broker,
    FxRateHistory,
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
    delete_target_allocation,
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
                    quantity=10,
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
    assert Decimal(str(targets.loc[0, "Target %"])) == Decimal("60")
    assert Decimal(str(report.loc[0, "Actual %"])) == Decimal("100")
    assert Decimal(str(report.loc[0, "Target %"])) == Decimal("60")
    assert report.loc[0, "Action"] == "SELL"
    assert Decimal(str(report.loc[0, "Trade Value"])) == Decimal("400")


def test_target_allocation_timestamps_insert_and_update(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        broker = Broker(name="Broker")
        account = Account(broker=broker, name="ISA", currency_code="USD")
        session.add(account)
        session.commit()
        account_choice = f"{account.id} | Broker / ISA"

    _patch_session(monkeypatch, engine)

    create_target_allocation(account_choice, "EQUITY", "60")

    with Session(engine) as session:
        account_strategy = session.scalar(select(AccountStrategy))
        assert account_strategy is not None
        assert account_strategy.created_at is not None
        assert account_strategy.updated_at is not None
        original_created_at = account_strategy.created_at
        old_updated_at = datetime(2026, 1, 1, tzinfo=UTC)
        account_strategy.updated_at = old_updated_at
        session.commit()

    create_target_allocation(account_choice, "EQUITY", "70")

    with Session(engine) as session:
        account_strategy = session.scalar(select(AccountStrategy))
        assert account_strategy is not None
        assert account_strategy.allocation_weight == Decimal("0.7000000000")
        assert account_strategy.created_at == original_created_at
        assert account_strategy.updated_at != old_updated_at


def test_delete_target_allocation_removes_existing_target(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        broker = Broker(name="Broker")
        account = Account(broker=broker, name="ISA", currency_code="USD")
        session.add(account)
        session.commit()
        account_choice = f"{account.id} | Broker / ISA"

    _patch_session(monkeypatch, engine)

    create_target_allocation(account_choice, "EQUITY", "60")
    delete_target_allocation(account_choice, "EQUITY")

    with Session(engine) as session:
        assert session.scalar(select(AccountStrategy)) is None

    targets = target_allocations(account_choice)
    assert targets.empty


def test_rebalance_uses_selected_account_currency_and_account_type(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        broker = Broker(name="Broker")
        account = Account(
            broker=broker,
            name="Paper GBP",
            currency_code="GBP",
            is_simulated=True,
        )
        portfolio = Portfolio(account=account, name="Core")
        security = Security(
            ticker="USD-ASSET",
            name="USD Asset",
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
                    quantity=1,
                    price=Decimal("100"),
                    fees=Decimal("0"),
                    total_value=Decimal("100"),
                    currency_exchange_rate=Decimal("1"),
                ),
                Transaction(
                    portfolio=portfolio,
                    date=datetime(2026, 1, 1),
                    type=TransactionType.DEPOSIT,
                    quantity=20,
                    price=Decimal("1"),
                    fees=Decimal("0"),
                    total_value=Decimal("20"),
                    currency_exchange_rate=Decimal("1"),
                ),
                PriceHistory(
                    security=security,
                    date=date(2026, 1, 1),
                    close=Decimal("100"),
                ),
                FxRateHistory(
                    base_currency_code="GBP",
                    quote_currency_code="USD",
                    symbol="GBPUSD=X",
                    date=date(2026, 1, 1),
                    close=Decimal("1.25"),
                ),
            ]
        )
        session.commit()
        account_choice = f"{account.id} | Broker / Paper GBP [TEST]"

    _patch_session(monkeypatch, engine)
    create_target_allocation(account_choice, "EQUITY", "50")
    create_target_allocation(account_choice, "CASH", "50")

    # The report must infer this is a paper account even if the caller still
    # passes the default Live Mode.
    report = rebalance_report(account_choice)
    by_class = report.set_index("Asset Class")

    assert Decimal(by_class.loc["EQUITY", "Current Value"]) == Decimal("80")
    assert Decimal(by_class.loc["CASH", "Current Value"]) == Decimal("20")
    assert Decimal(by_class.loc["EQUITY", "Actual %"]) == Decimal("80")
    assert Decimal(by_class.loc["CASH", "Actual %"]) == Decimal("20")
    assert by_class.loc["EQUITY", "Action"] == "SELL"
    assert Decimal(by_class.loc["EQUITY", "Trade Value"]) == Decimal("30")
    assert by_class.loc["CASH", "Action"] == "BUY"
    assert Decimal(by_class.loc["CASH", "Trade Value"]) == Decimal("30")


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
                quantity=1,
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
    assert Decimal(str(report.loc[0, "Amount"])) == Decimal("5")


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
                    quantity=1000,
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
                    quantity=10,
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
