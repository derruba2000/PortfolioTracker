from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from portfolio_management.db.base import Base
from portfolio_management.db.models import (
    Account,
    AssetClass,
    Broker,
    FxRateHistory,
    Portfolio,
    PriceHistory,
    Security,
    Transaction,
    TransactionType,
)
from portfolio_management.services.analytics import (
    ALL_ACCOUNTS_MODE,
    SANDBOX_MODE,
    allocation_by_asset_class,
    allocation_by_currency,
    current_positions,
    dashboard_summary,
    realized_pnl_report,
    twr_curve,
)


def test_positions_and_pnl_exclude_simulated_accounts_by_default(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        broker = Broker(name="Broker")
        account = Account(broker=broker, name="Real", currency_code="USD")
        test_account = Account(
            broker=broker,
            name="Test",
            currency_code="USD",
            is_simulated=True,
        )
        portfolio = Portfolio(account=account, name="Core")
        test_portfolio = Portfolio(account=test_account, name="Sandbox")
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
                Transaction(
                    portfolio=portfolio,
                    security=security,
                    date=datetime(2026, 1, 2),
                    type=TransactionType.SELL,
                    quantity=4,
                    price=Decimal("150"),
                    fees=Decimal("0"),
                    total_value=Decimal("600"),
                    currency_exchange_rate=Decimal("1"),
                ),
                Transaction(
                    portfolio=test_portfolio,
                    security=security,
                    date=datetime(2026, 1, 3),
                    type=TransactionType.BUY,
                    quantity=100,
                    price=Decimal("1"),
                    fees=Decimal("0"),
                    total_value=Decimal("100"),
                    currency_exchange_rate=Decimal("1"),
                ),
                PriceHistory(
                    security=security,
                    date=date(2026, 1, 3),
                    close_price=Decimal("160"),
                ),
            ]
        )
        session.commit()

    monkeypatch.setattr(
        "portfolio_management.services.analytics.get_session_factory",
        lambda: sessionmaker(bind=engine, expire_on_commit=False, future=True),
    )

    positions = current_positions()
    pnl = realized_pnl_report()
    summary = dashboard_summary()

    assert positions.loc[0, "Ticker"] == "AAPL"
    assert positions.loc[0, "Quantity"] == "6"
    assert Decimal(str(positions.loc[0, "Average Cost"])) == Decimal("100")
    assert Decimal(str(positions.loc[0, "Market Value"])) == Decimal("960")
    assert Decimal(str(positions.loc[0, "Unrealized P&L"])) == Decimal("360")
    assert len(positions) == 1
    assert Decimal(str(pnl.loc[0, "Realized P&L"])) == Decimal("200")
    assert Decimal(str(summary.loc[0, "Value"])) == Decimal("960")

    sandbox_positions = current_positions(account_mode=SANDBOX_MODE)
    sandbox_summary = dashboard_summary(account_mode=SANDBOX_MODE)
    asset_allocation = allocation_by_asset_class(account_mode=SANDBOX_MODE)
    currency_allocation = allocation_by_currency(account_mode=SANDBOX_MODE)

    assert sandbox_positions.loc[0, "Account"] == "Test"
    assert sandbox_positions.loc[0, "Quantity"] == "100"
    assert Decimal(str(sandbox_summary.loc[0, "Value"])) == Decimal("16000")
    assert asset_allocation.loc[0, "Asset Class"] == "EQUITY"
    assert currency_allocation.loc[0, "Currency"] == "USD"


def test_twr_curve_links_daily_returns(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        broker = Broker(name="Broker")
        account = Account(broker=broker, name="Real", currency_code="USD")
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
                PriceHistory(
                    security=security,
                    date=date(2026, 1, 2),
                    close_price=Decimal("110"),
                ),
            ]
        )
        session.commit()

    monkeypatch.setattr(
        "portfolio_management.services.analytics.get_session_factory",
        lambda: sessionmaker(bind=engine, expire_on_commit=False, future=True),
    )

    curve = twr_curve()
    first_two_days = curve.head(2)

    assert first_two_days.iloc[0]["TWR"] == "0"
    assert first_two_days.iloc[1]["TWR"] == "0.1"


def test_dashboard_reporting_currency_converts_prices_costs_values_and_charts(
    monkeypatch,
) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        broker = Broker(name="Broker")
        account = Account(broker=broker, name="EUR Account", currency_code="EUR")
        portfolio = Portfolio(account=account, name="Core")
        security = Security(
            ticker="VWCE.AS",
            name="Global ETF",
            asset_class=AssetClass.ETF,
            currency_code="EUR",
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
                    date=date(2026, 1, 2),
                    close_price=Decimal("120"),
                ),
                FxRateHistory(
                    base_currency_code="EUR",
                    quote_currency_code="USD",
                    symbol="EURUSD=X",
                    date=date(2026, 1, 2),
                    close=Decimal("1.20"),
                ),
                FxRateHistory(
                    base_currency_code="GBP",
                    quote_currency_code="USD",
                    symbol="GBPUSD=X",
                    date=date(2026, 1, 2),
                    close=Decimal("1.50"),
                ),
                FxRateHistory(
                    base_currency_code="EUR",
                    quote_currency_code="USD",
                    symbol="EURUSD=X",
                    date=date(2026, 1, 4),
                    close=Decimal("1.35"),
                ),
            ]
        )
        session.commit()

    monkeypatch.setattr(
        "portfolio_management.services.analytics.get_session_factory",
        lambda: sessionmaker(bind=engine, expire_on_commit=False, future=True),
    )

    positions = current_positions(
        reporting_currency="GBP",
        as_of_date=date(2026, 1, 3),
    )
    summary = dashboard_summary(
        reporting_currency="GBP",
        as_of_date=date(2026, 1, 3),
    )
    asset_chart = allocation_by_asset_class(
        reporting_currency="GBP",
        as_of_date=date(2026, 1, 3),
    )
    currency_chart = allocation_by_currency(
        reporting_currency="GBP",
        as_of_date=date(2026, 1, 3),
    )

    assert positions.loc[0, "Currency"] == "EUR"
    assert positions.loc[0, "Reporting Currency"] == "GBP"
    assert Decimal(positions.loc[0, "Average Cost"]) == Decimal("80.00")
    assert Decimal(positions.loc[0, "Latest Price"]) == Decimal("96.00")
    assert Decimal(positions.loc[0, "Market Value"]) == Decimal("960.00")
    assert Decimal(positions.loc[0, "Unrealized P&L"]) == Decimal("160.00")
    assert summary.loc[0, "Metric"] == "Global Market Value (GBP)"
    assert Decimal(summary.loc[0, "Value"]) == Decimal("960.00")
    assert asset_chart.loc[0, "Market Value"] == 960.0
    assert currency_chart.loc[0, "Currency"] == "EUR"
    assert currency_chart.loc[0, "Market Value"] == 960.0


def test_dashboard_reporting_currency_uses_inverse_fx_pair(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        broker = Broker(name="Broker")
        account = Account(broker=broker, name="USD Account", currency_code="USD")
        portfolio = Portfolio(account=account, name="Core")
        security = Security(
            ticker="AAPL",
            name="Apple",
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
                PriceHistory(
                    security=security,
                    date=date(2026, 1, 2),
                    close_price=Decimal("125"),
                ),
                FxRateHistory(
                    base_currency_code="GBP",
                    quote_currency_code="USD",
                    symbol="GBPUSD=X",
                    date=date(2026, 1, 2),
                    close=Decimal("1.25"),
                ),
            ]
        )
        session.commit()

    monkeypatch.setattr(
        "portfolio_management.services.analytics.get_session_factory",
        lambda: sessionmaker(bind=engine, expire_on_commit=False, future=True),
    )

    positions = current_positions(
        reporting_currency="GBP",
        as_of_date=date(2026, 1, 3),
    )

    assert Decimal(positions.loc[0, "Latest Price"]) == Decimal("100")
    assert Decimal(positions.loc[0, "Market Value"]) == Decimal("100")


def test_dashboard_reporting_currency_rejects_missing_usd_leg(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        broker = Broker(name="Broker")
        account = Account(broker=broker, name="EUR Account", currency_code="EUR")
        portfolio = Portfolio(account=account, name="Core")
        security = Security(
            ticker="VWCE.AS",
            name="Global ETF",
            asset_class=AssetClass.ETF,
            currency_code="EUR",
        )
        session.add(
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
            )
        )
        session.commit()

    monkeypatch.setattr(
        "portfolio_management.services.analytics.get_session_factory",
        lambda: sessionmaker(bind=engine, expire_on_commit=False, future=True),
    )

    try:
        current_positions(
            reporting_currency="GBP",
            as_of_date=date(2026, 1, 3),
        )
    except ValueError as exc:
        assert "normalize EUR to USD" in str(exc)
    else:
        raise AssertionError("Expected a missing USD FX leg to fail visibly.")


def test_dashboard_uses_only_transactions_and_latest_price_on_or_before_as_of_date(
    monkeypatch,
) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        broker = Broker(name="Broker")
        account = Account(broker=broker, name="Real", currency_code="USD")
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
                    quantity=2,
                    price=Decimal("100"),
                    fees=Decimal("0"),
                    total_value=Decimal("200"),
                    currency_exchange_rate=Decimal("1"),
                ),
                Transaction(
                    portfolio=portfolio,
                    security=security,
                    date=datetime(2026, 1, 4),
                    type=TransactionType.BUY,
                    quantity=5,
                    price=Decimal("500"),
                    fees=Decimal("0"),
                    total_value=Decimal("2500"),
                    currency_exchange_rate=Decimal("1"),
                ),
                PriceHistory(
                    security=security,
                    date=date(2026, 1, 2),
                    close_price=Decimal("110"),
                ),
                PriceHistory(
                    security=security,
                    date=date(2026, 1, 4),
                    close_price=Decimal("999"),
                ),
            ]
        )
        session.commit()

    monkeypatch.setattr(
        "portfolio_management.services.analytics.get_session_factory",
        lambda: sessionmaker(bind=engine, expire_on_commit=False, future=True),
    )

    positions = current_positions(as_of_date=date(2026, 1, 3))
    summary = dashboard_summary(as_of_date=date(2026, 1, 3))

    assert positions.loc[0, "Quantity"] == "2"
    assert Decimal(positions.loc[0, "Latest Price"]) == Decimal("110")
    assert Decimal(positions.loc[0, "Market Value"]) == Decimal("220")
    assert Decimal(summary.loc[0, "Value"]) == Decimal("220")


def test_dashboard_resolves_unique_exchange_qualified_price_symbol(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        broker = Broker(name="Broker")
        account = Account(broker=broker, name="Real", currency_code="GBP")
        portfolio = Portfolio(account=account, name="Core")
        holding_security = Security(
            ticker="VWRP",
            name="Vanguard FTSE All-World UCITS ETF",
            asset_class=AssetClass.ETF,
            currency_code="GBP",
        )
        priced_security = Security(
            ticker="VWRP.L",
            name="Vanguard FTSE All-World UCITS ETF",
            asset_class=AssetClass.ETF,
            currency_code="GBP",
        )
        session.add_all(
            [
                Transaction(
                    portfolio=portfolio,
                    security=holding_security,
                    date=datetime(2026, 6, 23),
                    type=TransactionType.BUY,
                    quantity=6,
                    price=Decimal("141.22"),
                    fees=Decimal("0"),
                    total_value=Decimal("847.32"),
                    currency_exchange_rate=Decimal("1"),
                ),
                PriceHistory(
                    security=priced_security,
                    symbol="VWRP.L",
                    date=date(2026, 6, 24),
                    close_price=Decimal("141.36"),
                ),
            ]
        )
        session.commit()

    monkeypatch.setattr(
        "portfolio_management.services.analytics.get_session_factory",
        lambda: sessionmaker(bind=engine, expire_on_commit=False, future=True),
    )

    positions = current_positions(as_of_date=date(2026, 6, 24))

    assert positions.loc[0, "Ticker"] == "VWRP"
    assert Decimal(positions.loc[0, "Latest Price"]) == Decimal("141.36")
    assert Decimal(positions.loc[0, "Market Value"]) == Decimal("848.16")


def test_positions_can_filter_one_portfolio_and_include_all_account_scopes(
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
                    close_price=Decimal("110"),
                ),
                PriceHistory(
                    security=paper_security,
                    date=date(2026, 1, 2),
                    close_price=Decimal("55"),
                ),
            ]
        )
        session.flush()
        live_portfolio_id = live_portfolio.id
        session.commit()

    monkeypatch.setattr(
        "portfolio_management.services.analytics.get_session_factory",
        lambda: sessionmaker(bind=engine, expire_on_commit=False, future=True),
    )

    all_positions = current_positions(account_mode=ALL_ACCOUNTS_MODE)
    live_drilldown = current_positions(
        account_mode=ALL_ACCOUNTS_MODE,
        portfolio_id=live_portfolio_id,
    )

    assert set(all_positions["Ticker"]) == {"LIVE", "PAPER"}
    assert list(live_drilldown["Ticker"]) == ["LIVE"]
    assert list(live_drilldown["Portfolio"]) == ["Live Portfolio"]
