from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pandas as pd
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from portfolio_management.db.base import Base
from portfolio_management.db.models import (
    Account,
    AssetClass,
    Broker,
    Portfolio,
    Security,
    Transaction,
    TransactionType,
)
from portfolio_management.services.query_filters import exclude_simulated_accounts
from portfolio_management.services.transactions import (
    TransactionInput,
    create_transaction,
    import_transactions_from_dataframe,
    transfer_cash,
    transaction_input_from_mapping,
)


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        yield session


def test_create_buy_transaction_creates_related_records(session: Session) -> None:
    broker = Broker(name="Interactive Brokers")
    account = Account(broker=broker, name="ISA", currency_code="GBP")
    portfolio = Portfolio(account=account, name="Core")
    session.add(portfolio)
    session.flush()

    transaction = create_transaction(
        session,
        TransactionInput(
            portfolio_id=portfolio.id,
            date=datetime(2026, 6, 21),
            transaction_type=TransactionType.BUY,
            description="Initial allocation",
            ticker="VWCE",
            security_name="Vanguard FTSE All-World UCITS ETF",
            asset_class=AssetClass.EQUITY,
            security_currency_code="EUR",
            quantity=2,
            price=Decimal("100.25"),
            fees=Decimal("1.50"),
        ),
    )
    session.commit()

    security = session.scalar(select(Security).where(Security.ticker == "VWCE"))

    assert broker is not None
    assert account is not None
    assert account.currency_code == "GBP"
    assert account.is_simulated is False
    assert transaction.portfolio.account_id == account.id
    assert transaction.portfolio.name == "Core"
    assert transaction.description == "Initial allocation"
    assert security is not None
    assert security.asset_class == AssetClass.EQUITY
    assert transaction.total_value == Decimal("202")


def test_import_transactions_from_dataframe(session: Session) -> None:
    broker = Broker(name="Broker")
    account = Account(broker=broker, name="Taxable", currency_code="USD")
    portfolio = Portfolio(account=account, name="Core")
    session.add(portfolio)
    session.flush()

    dataframe = pd.DataFrame(
        [
            {
                "Date": "2026-06-20",
                "Type": "BUY",
                "Description": "Core position",
                "Ticker": "AAPL",
                "Security Name": "Apple Inc.",
                "Asset Class": "EQUITY",
                "Quantity": "3",
                "Price": "200",
                "Fees": "1",
            },
            {
                "Date": "2026-06-21",
                "Type": "SELL",
                "Ticker": "AAPL",
                "Quantity": "1",
                "Price": "210",
                "Fees": "1",
            },
        ]
    )

    imported_count = import_transactions_from_dataframe(
        session,
        dataframe,
        portfolio_id=portfolio.id,
    )
    session.commit()

    transactions = session.scalars(select(Transaction).order_by(Transaction.id)).all()
    assert imported_count == 2
    assert len(transactions) == 2
    assert {transaction.portfolio_id for transaction in transactions} == {portfolio.id}
    assert transactions[0].total_value == Decimal("601")
    assert transactions[0].description == "Core position"
    assert transactions[1].total_value == Decimal("209")


def test_dividend_requires_positive_total_value(session: Session) -> None:
    with pytest.raises(ValueError, match="positive total value"):
        create_transaction(
            session,
            TransactionInput(
                date=datetime(2026, 6, 21),
                transaction_type=TransactionType.DIVIDEND,
                ticker="AAPL",
                quantity=0,
                price=Decimal("0"),
            ),
        )


def test_split_is_stored_as_ratio_with_zero_cash_flow(session: Session) -> None:
    broker = Broker(name="Broker")
    account = Account(broker=broker, name="Taxable", currency_code="USD")
    portfolio = Portfolio(account=account, name="Core")
    session.add(portfolio)
    session.flush()

    transaction = create_transaction(
        session,
        TransactionInput(
            portfolio_id=portfolio.id,
            date=datetime(2026, 6, 21),
            transaction_type=TransactionType.SPLIT,
            ticker="AAPL",
            quantity=4,
            price=Decimal("0"),
            fees=Decimal("0"),
        ),
    )

    assert transaction.type == TransactionType.SPLIT
    assert transaction.quantity == 4
    assert transaction.total_value == Decimal("0")


def test_transaction_input_from_mapping_normalizes_aliases() -> None:
    transaction_input = transaction_input_from_mapping(
        {
            "Symbol": " spy ",
            "Transaction Date": "2026-06-21",
            "Type": "BUY",
            "Shares": "2",
            "Price": "500.00",
            "Fee": "0.25",
            "Asset Class": "BOND",
        }
    )

    assert transaction_input.ticker == "SPY"
    assert transaction_input.transaction_type == TransactionType.BUY
    assert transaction_input.quantity == 2
    assert transaction_input.asset_class == AssetClass.BOND


def test_transaction_input_rejects_fractional_quantity() -> None:
    with pytest.raises(ValueError, match="Quantity must be an integer value"):
        transaction_input_from_mapping(
            {
                "Date": "2026-06-21",
                "Type": "BUY",
                "Ticker": "SPY",
                "Quantity": "1.25",
                "Price": "500.00",
            }
        )


def test_simulated_account_is_excluded_by_firewall_filter(session: Session) -> None:
    broker = Broker(name="Broker")
    real_account = Account(
        broker=broker,
        name="Real",
        currency_code="USD",
        is_simulated=False,
    )
    test_account = Account(
        broker=broker,
        name="Test Lab",
        currency_code="USD",
        is_simulated=True,
    )
    session.add_all([real_account, test_account])
    session.commit()

    statement = exclude_simulated_accounts(select(Account).order_by(Account.name))
    accounts = session.scalars(statement).all()

    assert [account.name for account in accounts] == ["Real"]


def test_transfer_cash_creates_withdrawal_and_deposit(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)

    monkeypatch.setattr(
        "portfolio_management.services.transactions.get_session_factory",
        lambda: sessionmaker(bind=engine, expire_on_commit=False, future=True),
    )

    with Session(engine) as session:
        broker = Broker(name="Broker")
        source_account = Account(broker=broker, name="Source", currency_code="USD")
        target_account = Account(broker=broker, name="Target", currency_code="USD")
        source_portfolio = Portfolio(account=source_account, name="Source Core")
        target_portfolio = Portfolio(account=target_account, name="Target Core")
        session.add_all([source_account, target_account, source_portfolio, target_portfolio])
        session.commit()

    status = transfer_cash(
        source_account_choice=1,
        target_account_choice=2,
        amount="150.25",
        transfer_date="2026-06-22",
        description="Top up",
    )

    with Session(engine) as session:
        transactions = session.scalars(select(Transaction).order_by(Transaction.id)).all()

    assert "Transferred 150.25 USD" in status
    assert len(transactions) == 2
    assert transactions[0].type == TransactionType.WITHDRAWAL
    assert transactions[1].type == TransactionType.DEPOSIT
    assert transactions[0].total_value == Decimal("-150.25")
    assert transactions[1].total_value == Decimal("150.25")
    assert "source account: Source" in (transactions[0].description or "")
    assert "target account: Target" in (transactions[0].description or "")
    assert "cash transferred: 150.25" in (transactions[0].description or "")


def test_transfer_cash_requires_matching_currency(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)

    monkeypatch.setattr(
        "portfolio_management.services.transactions.get_session_factory",
        lambda: sessionmaker(bind=engine, expire_on_commit=False, future=True),
    )

    with Session(engine) as session:
        broker = Broker(name="Broker")
        source_account = Account(broker=broker, name="Source", currency_code="USD")
        target_account = Account(broker=broker, name="Target", currency_code="EUR")
        session.add_all([source_account, target_account])
        session.commit()

    with pytest.raises(ValueError, match="same currency code"):
        transfer_cash(
            source_account_choice=1,
            target_account_choice=2,
            amount="10",
            transfer_date="2026-06-22",
        )
