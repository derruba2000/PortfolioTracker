from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pandas as pd
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

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
    transaction_input_from_mapping,
)


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        yield session


def test_create_buy_transaction_creates_related_records(session: Session) -> None:
    transaction = create_transaction(
        session,
        TransactionInput(
            broker_name="Interactive Brokers",
            account_name="ISA",
            account_currency_code="GBP",
            date=datetime(2026, 6, 21),
            transaction_type=TransactionType.BUY,
            description="Initial allocation",
            ticker="VWCE",
            security_name="Vanguard FTSE All-World UCITS ETF",
            asset_class=AssetClass.ETF,
            security_currency_code="EUR",
            quantity=Decimal("2.5"),
            price=Decimal("100.25"),
            fees=Decimal("1.50"),
        ),
    )
    session.commit()

    broker = session.scalar(select(Broker).where(Broker.name == "Interactive Brokers"))
    account = session.scalar(select(Account).where(Account.name == "ISA"))
    security = session.scalar(select(Security).where(Security.ticker == "VWCE"))

    assert broker is not None
    assert account is not None
    assert account.currency_code == "GBP"
    assert account.is_simulated is False
    assert transaction.portfolio.account_id == account.id
    assert transaction.portfolio.name == "Default Portfolio"
    assert transaction.description == "Initial allocation"
    assert security is not None
    assert security.asset_class == AssetClass.ETF
    assert transaction.total_value == Decimal("252.125")


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
                quantity=Decimal("0"),
                price=Decimal("0"),
            ),
        )


def test_split_is_stored_as_ratio_with_zero_cash_flow(session: Session) -> None:
    transaction = create_transaction(
        session,
        TransactionInput(
            date=datetime(2026, 6, 21),
            transaction_type=TransactionType.SPLIT,
            ticker="AAPL",
            quantity=Decimal("4"),
            price=Decimal("0"),
            fees=Decimal("0"),
        ),
    )

    assert transaction.type == TransactionType.SPLIT
    assert transaction.quantity == Decimal("4")
    assert transaction.total_value == Decimal("0")


def test_transaction_input_from_mapping_normalizes_aliases() -> None:
    transaction_input = transaction_input_from_mapping(
        {
            "Symbol": " spy ",
            "Transaction Date": "2026-06-21",
            "Type": "BUY",
            "Shares": "1.25",
            "Price": "500.00",
            "Fee": "0.25",
            "Asset Class": "ETF",
        }
    )

    assert transaction_input.ticker == "SPY"
    assert transaction_input.transaction_type == TransactionType.BUY
    assert transaction_input.quantity == Decimal("1.25")
    assert transaction_input.asset_class == AssetClass.ETF


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
