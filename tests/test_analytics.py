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
    Portfolio,
    PriceHistory,
    Security,
    Transaction,
    TransactionType,
)
from portfolio_management.services.analytics import (
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
                    quantity=Decimal("10"),
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
                    quantity=Decimal("4"),
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
                    quantity=Decimal("100"),
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
    assert positions.loc[0, "Average Cost"] == "100"
    assert positions.loc[0, "Market Value"] == "960"
    assert positions.loc[0, "Unrealized P&L"] == "360"
    assert len(positions) == 1
    assert pnl.loc[0, "Realized P&L"] == "200"
    assert summary.loc[0, "Value"] == "960"

    sandbox_positions = current_positions(account_mode=SANDBOX_MODE)
    sandbox_summary = dashboard_summary(account_mode=SANDBOX_MODE)
    asset_allocation = allocation_by_asset_class(account_mode=SANDBOX_MODE)
    currency_allocation = allocation_by_currency(account_mode=SANDBOX_MODE)

    assert sandbox_positions.loc[0, "Account"] == "Test"
    assert sandbox_positions.loc[0, "Quantity"] == "100"
    assert sandbox_summary.loc[0, "Value"] == "16000"
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
