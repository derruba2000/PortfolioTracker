from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from portfolio_management.db.base import Base
from portfolio_management.db.models import (
    Account,
    AssetClass,
    Broker,
    Order,
    OrderStatus,
    OrderType,
    Portfolio,
    PriceHistory,
    Security,
    Transaction,
    TransactionType,
)
from portfolio_management.services.analytics import LIVE_MODE, SANDBOX_MODE
from portfolio_management.services.orders import (
    cancel_order,
    create_order,
    list_orders,
    mark_order_completed,
)
from portfolio_management.tabs.orders import orders_table


def test_orders_table_has_required_columns_and_rich_cells(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)

    monkeypatch.setattr(
        "portfolio_management.services.orders.get_session_factory",
        lambda: sessionmaker(bind=engine, expire_on_commit=False, future=True),
    )

    with Session(engine) as session:
        broker = Broker(name="Broker")
        account = Account(broker=broker, name="Live", currency_code="USD", is_simulated=False)
        portfolio = Portfolio(account=account, name="Core")
        security = Security(
            ticker="AAPL",
            name="Apple",
            asset_class=AssetClass.EQUITY,
            currency_code="USD",
        )
        session.add_all([broker, account, portfolio, security])
        session.flush()

        session.add(
            Order(
                portfolio=portfolio,
                security=security,
                order_type=OrderType.BUY,
                status=OrderStatus.PENDING,
                target_quantity=Decimal("2"),
                target_price=Decimal("100"),
                created_at=datetime(2026, 7, 1, 10, 0, 0),
            )
        )
        session.add(
            PriceHistory(
                security=security,
                date=date(2026, 7, 1),
                symbol="AAPL",
                close=Decimal("98.5"),
            )
        )
        session.commit()

    table = orders_table(LIVE_MODE)
    assert isinstance(table, pd.DataFrame)

    expected_columns = [
        "ID",
        "Date",
        "Portfolio",
        "Type",
        "Asset/Ticker",
        "Quantity",
        "Price",
        "Status",
        "Market vs Target",
    ]
    assert list(table.columns) == expected_columns

    first_row = table.iloc[0]
    assert "finance.yahoo.com/quote/AAPL" in str(first_row["Asset/Ticker"])
    assert "Mkt 98.5000 vs Target 100.0000" in str(first_row["Market vs Target"])
    assert "background:#16a34a" in str(first_row["Market vs Target"])


def test_orders_table_mode_filter_respects_live_vs_sandbox(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)

    monkeypatch.setattr(
        "portfolio_management.services.orders.get_session_factory",
        lambda: sessionmaker(bind=engine, expire_on_commit=False, future=True),
    )

    with Session(engine) as session:
        broker = Broker(name="Broker")
        live_account = Account(broker=broker, name="Live", currency_code="USD", is_simulated=False)
        test_account = Account(broker=broker, name="Paper", currency_code="USD", is_simulated=True)
        live_portfolio = Portfolio(account=live_account, name="Live Core")
        test_portfolio = Portfolio(account=test_account, name="Paper Core")
        session.add_all([broker, live_account, test_account, live_portfolio, test_portfolio])
        session.flush()

        session.add_all(
            [
                Order(
                    portfolio=live_portfolio,
                    order_type=OrderType.DEPOSIT,
                    status=OrderStatus.PENDING,
                    target_cash_amount=Decimal("1000"),
                    created_at=datetime(2026, 7, 1, 9, 0, 0),
                ),
                Order(
                    portfolio=test_portfolio,
                    order_type=OrderType.WITHDRAW,
                    status=OrderStatus.PENDING,
                    target_cash_amount=Decimal("500"),
                    created_at=datetime(2026, 7, 1, 8, 0, 0),
                ),
            ]
        )
        session.commit()

    live_table = orders_table(LIVE_MODE)
    sandbox_table = orders_table(SANDBOX_MODE)

    assert len(live_table.index) == 1
    assert len(sandbox_table.index) == 1
    assert str(live_table.iloc[0]["Portfolio"]).find("Live Core") >= 0
    assert str(sandbox_table.iloc[0]["Portfolio"]).find("Paper Core") >= 0


def test_create_buy_order_defaults_to_pending(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)

    monkeypatch.setattr(
        "portfolio_management.services.orders.get_session_factory",
        lambda: sessionmaker(bind=engine, expire_on_commit=False, future=True),
    )

    with Session(engine) as session:
        broker = Broker(name="Broker")
        account = Account(broker=broker, name="Live", currency_code="USD", is_simulated=False)
        portfolio = Portfolio(account=account, name="Core")
        security = Security(
            ticker="MSFT",
            name="Microsoft",
            asset_class=AssetClass.EQUITY,
            currency_code="USD",
        )
        session.add_all([broker, account, portfolio, security])
        session.commit()
        portfolio_choice = f"{portfolio.id} | {portfolio.name}"

    status = create_order(
        portfolio_choice=portfolio_choice,
        order_type="BUY",
        security_ticker="MSFT",
        target_quantity="1.5",
        target_price="400",
        target_cash_amount="",
    )

    with Session(engine) as session:
        orders = session.query(Order).all()

    assert len(orders) == 1
    order = orders[0]
    assert order.status == OrderStatus.PENDING
    assert order.order_type == OrderType.BUY
    assert order.security_id is not None
    assert order.target_quantity == Decimal("1.5")
    assert order.target_price == Decimal("400")
    assert order.target_cash_amount is None
    assert "PENDING" in status


def test_create_withdraw_order_uses_cash_amount_and_no_security(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)

    monkeypatch.setattr(
        "portfolio_management.services.orders.get_session_factory",
        lambda: sessionmaker(bind=engine, expire_on_commit=False, future=True),
    )

    with Session(engine) as session:
        broker = Broker(name="Broker")
        account = Account(broker=broker, name="Live", currency_code="USD", is_simulated=False)
        portfolio = Portfolio(account=account, name="Core")
        session.add_all([broker, account, portfolio])
        session.commit()
        portfolio_choice = f"{portfolio.id} | {portfolio.name}"

    status = create_order(
        portfolio_choice=portfolio_choice,
        order_type="WITHDRAW",
        security_ticker="",
        target_quantity="",
        target_price="",
        target_cash_amount="250",
    )

    with Session(engine) as session:
        orders = session.query(Order).all()

    assert len(orders) == 1
    order = orders[0]
    assert order.status == OrderStatus.PENDING
    assert order.order_type == OrderType.WITHDRAW
    assert order.security_id is None
    assert order.target_quantity is None
    assert order.target_price is None
    assert order.target_cash_amount == Decimal("250")
    assert "PENDING" in status


def test_list_orders_filters_by_status_portfolio_and_date_range(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)

    monkeypatch.setattr(
        "portfolio_management.services.orders.get_session_factory",
        lambda: sessionmaker(bind=engine, expire_on_commit=False, future=True),
    )

    with Session(engine) as session:
        broker = Broker(name="Broker")
        account = Account(broker=broker, name="Live", currency_code="USD", is_simulated=False)
        p1 = Portfolio(account=account, name="Core")
        p2 = Portfolio(account=account, name="Income")
        session.add_all([broker, account, p1, p2])
        session.flush()

        session.add_all(
            [
                Order(
                    portfolio=p1,
                    order_type=OrderType.BUY,
                    status=OrderStatus.PENDING,
                    target_quantity=Decimal("1"),
                    target_price=Decimal("100"),
                    created_at=datetime(2026, 7, 1, 10, 0, 0),
                ),
                Order(
                    portfolio=p1,
                    order_type=OrderType.SELL,
                    status=OrderStatus.EXECUTED,
                    target_quantity=Decimal("1"),
                    target_price=Decimal("110"),
                    created_at=datetime(2026, 6, 20, 10, 0, 0),
                ),
                Order(
                    portfolio=p2,
                    order_type=OrderType.DEPOSIT,
                    status=OrderStatus.CANCELLED,
                    target_cash_amount=Decimal("500"),
                    created_at=datetime(2026, 7, 2, 10, 0, 0),
                ),
            ]
        )
        session.commit()
        p1_choice = f"{p1.id} | {p1.name}"

    pending = list_orders(account_filter="Real", status_filter="PENDING")
    assert len(pending.index) == 1
    assert set(pending["Status"]) == {"PENDING"}

    p1_only = list_orders(account_filter="Real", portfolio_filter=p1_choice)
    assert len(p1_only.index) == 2
    assert set(p1_only["Portfolio"]) == {"Core"}

    july_window = list_orders(
        account_filter="Real",
        start_date="2026-07-01",
        end_date="2026-07-01",
    )
    assert len(july_window.index) == 1
    assert set(july_window["Date"]) == {"2026-07-01"}


def test_cancel_pending_order_sets_cancelled_and_generates_no_transactions(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)

    monkeypatch.setattr(
        "portfolio_management.services.orders.get_session_factory",
        lambda: sessionmaker(bind=engine, expire_on_commit=False, future=True),
    )

    with Session(engine) as session:
        broker = Broker(name="Broker")
        account = Account(broker=broker, name="Live", currency_code="USD", is_simulated=False)
        portfolio = Portfolio(account=account, name="Core")
        security = Security(
            ticker="AAPL",
            name="Apple",
            asset_class=AssetClass.EQUITY,
            currency_code="USD",
        )
        session.add_all([broker, account, portfolio, security])
        session.flush()

        order = Order(
            portfolio=portfolio,
            security=security,
            order_type=OrderType.BUY,
            status=OrderStatus.PENDING,
            target_quantity=Decimal("1"),
            target_price=Decimal("100"),
            created_at=datetime(2026, 7, 1, 11, 0, 0),
        )
        session.add(order)
        session.commit()
        order_id = order.id
        order_choice = f"{order.id} | BUY AAPL"

    with Session(engine) as session:
        before_tx_count = session.query(Transaction).count()

    status = cancel_order(order_choice)

    with Session(engine) as session:
        cancelled = session.get(Order, order_id)
        after_tx_count = session.query(Transaction).count()

    assert cancelled is not None
    assert cancelled.status == OrderStatus.CANCELLED
    assert before_tx_count == after_tx_count == 0
    assert "Cancelled order" in status


def test_cannot_cancel_non_pending_order(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)

    monkeypatch.setattr(
        "portfolio_management.services.orders.get_session_factory",
        lambda: sessionmaker(bind=engine, expire_on_commit=False, future=True),
    )

    with Session(engine) as session:
        broker = Broker(name="Broker")
        account = Account(broker=broker, name="Live", currency_code="USD", is_simulated=False)
        portfolio = Portfolio(account=account, name="Core")
        session.add_all([broker, account, portfolio])
        session.flush()

        executed_order = Order(
            portfolio=portfolio,
            order_type=OrderType.DEPOSIT,
            status=OrderStatus.EXECUTED,
            target_cash_amount=Decimal("100"),
            created_at=datetime(2026, 7, 1, 12, 0, 0),
        )
        session.add(executed_order)
        session.commit()
        executed_order_id = executed_order.id

    with Session(engine) as session:
        with pytest.raises(ValueError, match="Only PENDING orders can be cancelled"):
            _ = cancel_order(f"{executed_order_id} | DEPOSIT CASH")


def test_mark_order_completed_sets_executed_and_timestamp(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)

    monkeypatch.setattr(
        "portfolio_management.services.orders.get_session_factory",
        lambda: sessionmaker(bind=engine, expire_on_commit=False, future=True),
    )

    with Session(engine) as session:
        broker = Broker(name="Broker")
        account = Account(broker=broker, name="Live", currency_code="USD", is_simulated=False)
        portfolio = Portfolio(account=account, name="Core")
        security = Security(
            ticker="NVDA",
            name="NVIDIA",
            asset_class=AssetClass.EQUITY,
            currency_code="USD",
        )
        session.add_all([broker, account, portfolio, security])
        session.flush()

        session.add(
            Transaction(
                portfolio=portfolio,
                security=None,
                date=datetime(2026, 6, 30, 11, 30, 0),
                type=TransactionType.DEPOSIT,
                description="Seed cash",
                quantity=Decimal("1"),
                price=Decimal("1000"),
                fees=Decimal("0"),
                total_value=Decimal("1000"),
                currency_exchange_rate=Decimal("1"),
            )
        )

        pending_order = Order(
            portfolio=portfolio,
            security=security,
            order_type=OrderType.BUY,
            status=OrderStatus.PENDING,
            target_quantity=Decimal("1"),
            target_price=Decimal("120"),
            created_at=datetime(2026, 7, 1, 12, 0, 0),
        )
        session.add(pending_order)
        session.commit()
        order_id = pending_order.id

    status = mark_order_completed(
        order_choice=f"{order_id} | BUY NVDA",
        actual_quantity="1",
        actual_price="121.5",
        actual_fees="0.25",
    )

    with Session(engine) as session:
        order = session.get(Order, order_id)

    assert order is not None
    assert order.status == OrderStatus.EXECUTED
    assert order.executed_at is not None
    assert "EXECUTED" in status


def test_mark_completed_buy_generates_two_linked_transactions_with_legacy_math(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)

    monkeypatch.setattr(
        "portfolio_management.services.orders.get_session_factory",
        lambda: sessionmaker(bind=engine, expire_on_commit=False, future=True),
    )

    with Session(engine) as session:
        broker = Broker(name="Broker")
        account = Account(broker=broker, name="Live", currency_code="USD", is_simulated=False)
        portfolio = Portfolio(account=account, name="Core")
        security = Security(
            ticker="SPY",
            name="SPDR S&P 500 ETF",
            asset_class=AssetClass.EQUITY,
            currency_code="USD",
        )
        session.add_all([broker, account, portfolio, security])
        session.flush()

        session.add(
            Transaction(
                portfolio=portfolio,
                security=None,
                date=datetime(2026, 6, 30, 9, 0, 0),
                type=TransactionType.DEPOSIT,
                description="Seed cash",
                quantity=Decimal("1"),
                price=Decimal("10000"),
                fees=Decimal("0"),
                total_value=Decimal("10000"),
                currency_exchange_rate=Decimal("1"),
            )
        )

        order = Order(
            portfolio=portfolio,
            security=security,
            order_type=OrderType.BUY,
            status=OrderStatus.PENDING,
            target_quantity=Decimal("2"),
            target_price=Decimal("100"),
            created_at=datetime(2026, 7, 1, 10, 0, 0),
        )
        session.add(order)
        session.commit()
        order_id = order.id

    _ = mark_order_completed(
        order_choice=f"{order_id} | BUY SPY",
        actual_quantity="2",
        actual_price="100",
        actual_fees="1.5",
    )

    with Session(engine) as session:
        transactions = session.query(Transaction).filter(Transaction.order_id == order_id).order_by(Transaction.id).all()

    assert len(transactions) == 2
    asset_leg = [txn for txn in transactions if txn.security_id is not None][0]
    cash_leg = [txn for txn in transactions if txn.security_id is None][0]

    assert asset_leg.type == TransactionType.BUY
    assert asset_leg.total_value == Decimal("201.5")
    assert cash_leg.type == TransactionType.WITHDRAWAL
    assert cash_leg.total_value == Decimal("-201.5")


def test_mark_completed_withdraw_generates_single_cash_transaction(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)

    monkeypatch.setattr(
        "portfolio_management.services.orders.get_session_factory",
        lambda: sessionmaker(bind=engine, expire_on_commit=False, future=True),
    )

    with Session(engine) as session:
        broker = Broker(name="Broker")
        account = Account(broker=broker, name="Live", currency_code="USD", is_simulated=False)
        portfolio = Portfolio(account=account, name="Core")
        order = Order(
            portfolio=portfolio,
            order_type=OrderType.WITHDRAW,
            status=OrderStatus.PENDING,
            target_cash_amount=Decimal("300"),
            created_at=datetime(2026, 7, 1, 10, 0, 0),
        )
        session.add_all([broker, account, portfolio, order])
        session.commit()
        order_id = order.id

    _ = mark_order_completed(
        order_choice=f"{order_id} | WITHDRAW CASH",
        actual_quantity="1",
        actual_price="300",
        actual_fees="0",
    )

    with Session(engine) as session:
        transactions = session.query(Transaction).filter(Transaction.order_id == order_id).all()

    assert len(transactions) == 1
    leg = transactions[0]
    assert leg.security_id is None
    assert leg.type == TransactionType.WITHDRAWAL
    assert leg.total_value == Decimal("-300")


def test_mark_order_completed_rejects_non_pending(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)

    monkeypatch.setattr(
        "portfolio_management.services.orders.get_session_factory",
        lambda: sessionmaker(bind=engine, expire_on_commit=False, future=True),
    )

    with Session(engine) as session:
        broker = Broker(name="Broker")
        account = Account(broker=broker, name="Live", currency_code="USD", is_simulated=False)
        portfolio = Portfolio(account=account, name="Core")
        executed_order = Order(
            portfolio=portfolio,
            order_type=OrderType.DEPOSIT,
            status=OrderStatus.EXECUTED,
            target_cash_amount=Decimal("100"),
            created_at=datetime(2026, 7, 1, 12, 0, 0),
            executed_at=datetime(2026, 7, 1, 12, 30, 0),
        )
        session.add_all([broker, account, portfolio, executed_order])
        session.commit()
        order_id = executed_order.id

    with pytest.raises(ValueError, match="Only PENDING orders can be marked as completed"):
        _ = mark_order_completed(
            order_choice=f"{order_id} | DEPOSIT CASH",
            actual_quantity="1",
            actual_price="100",
            actual_fees="0",
        )