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
    list_transactions,
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

    create_transaction(
        session,
        TransactionInput(
            portfolio_id=portfolio.id,
            date=datetime(2026, 6, 20),
            transaction_type=TransactionType.DEPOSIT,
            ticker=None,
            quantity=1,
            price=Decimal("500"),
        ),
    )

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

    settlements = session.scalars(
        select(Transaction)
        .where(
            Transaction.portfolio_id == portfolio.id,
            Transaction.security_id.is_(None),
            Transaction.type == TransactionType.WITHDRAWAL,
            Transaction.description.contains("Auto cash settlement for trade #"),
        )
    ).all()
    assert len(settlements) == 1
    assert "cash withdrawn from portfolio to settle BUY" in (settlements[0].description or "")


def test_buy_transaction_is_blocked_when_cash_is_insufficient(session: Session) -> None:
    broker = Broker(name="Interactive Brokers")
    account = Account(broker=broker, name="ISA", currency_code="GBP")
    portfolio = Portfolio(account=account, name="Core")
    session.add(portfolio)
    session.flush()

    with pytest.raises(ValueError, match="Not enough cash in portfolio"):
        create_transaction(
            session,
            TransactionInput(
                portfolio_id=portfolio.id,
                date=datetime(2026, 6, 21),
                transaction_type=TransactionType.BUY,
                ticker="VWCE",
                security_name="Vanguard FTSE All-World UCITS ETF",
                asset_class=AssetClass.EQUITY,
                security_currency_code="GBP",
                quantity=2,
                price=Decimal("100"),
                fees=Decimal("1"),
            ),
        )


def test_sell_transaction_creates_cash_deposit_settlement(session: Session) -> None:
    broker = Broker(name="Interactive Brokers")
    account = Account(broker=broker, name="ISA", currency_code="GBP")
    portfolio = Portfolio(account=account, name="Core")
    session.add(portfolio)
    session.flush()

    create_transaction(
        session,
        TransactionInput(
            portfolio_id=portfolio.id,
            date=datetime(2026, 6, 20),
            transaction_type=TransactionType.DEPOSIT,
            ticker=None,
            quantity=1,
            price=Decimal("1000"),
        ),
    )
    create_transaction(
        session,
        TransactionInput(
            portfolio_id=portfolio.id,
            date=datetime(2026, 6, 21),
            transaction_type=TransactionType.BUY,
            ticker="VWCE",
            security_name="Vanguard FTSE All-World UCITS ETF",
            asset_class=AssetClass.EQUITY,
            security_currency_code="GBP",
            quantity=2,
            price=Decimal("100"),
            fees=Decimal("2"),
        ),
    )

    sell = create_transaction(
        session,
        TransactionInput(
            portfolio_id=portfolio.id,
            date=datetime(2026, 6, 22),
            transaction_type=TransactionType.SELL,
            ticker="VWCE",
            security_name="Vanguard FTSE All-World UCITS ETF",
            asset_class=AssetClass.EQUITY,
            security_currency_code="GBP",
            quantity=1,
            price=Decimal("110"),
            fees=Decimal("1"),
        ),
    )
    session.commit()

    settlements = session.scalars(
        select(Transaction)
        .where(
            Transaction.portfolio_id == portfolio.id,
            Transaction.security_id.is_(None),
            Transaction.type == TransactionType.DEPOSIT,
            Transaction.description.contains(f"Auto cash settlement for trade #{sell.id}"),
        )
    ).all()
    assert len(settlements) == 1
    assert settlements[0].total_value == Decimal("109")
    assert "cash deposited into portfolio from SELL proceeds" in (settlements[0].description or "")


def test_import_transactions_from_dataframe(session: Session) -> None:
    broker = Broker(name="Broker")
    account = Account(broker=broker, name="Taxable", currency_code="USD")
    portfolio = Portfolio(account=account, name="Core")
    session.add(portfolio)
    session.flush()

    dataframe = pd.DataFrame(
        [
            {
                "Date": "2026-06-19",
                "Type": "DEPOSIT",
                "Quantity": "1",
                "Price": "1000",
                "Fees": "0",
            },
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
    assert imported_count == 3
    assert len(transactions) == 5
    assert {transaction.portfolio_id for transaction in transactions} == {portfolio.id}
    assert transactions[1].total_value == Decimal("601")
    assert transactions[1].description == "Core position"
    assert transactions[3].total_value == Decimal("209")


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


def test_transaction_input_accepts_fractional_quantity() -> None:
    transaction_input = transaction_input_from_mapping(
        {
            "Date": "2026-06-21",
            "Type": "BUY",
            "Ticker": "SPY",
            "Quantity": "1.25",
            "Price": "500.00",
        }
    )

    assert transaction_input.quantity == Decimal("1.25")


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


def test_list_transactions_supports_advanced_ledger_filters(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)

    monkeypatch.setattr(
        "portfolio_management.services.transactions.get_session_factory",
        lambda: sessionmaker(bind=engine, expire_on_commit=False, future=True),
    )

    with Session(engine) as session:
        broker = Broker(name="Broker")
        account = Account(broker=broker, name="Live", currency_code="USD", is_simulated=False)
        portfolio_core = Portfolio(account=account, name="Core")
        portfolio_income = Portfolio(account=account, name="Income")
        equity_security = Security(
            ticker="AAPL",
            name="Apple",
            asset_class=AssetClass.EQUITY,
            currency_code="USD",
        )
        session.add_all([broker, account, portfolio_core, portfolio_income, equity_security])
        session.flush()

        session.add_all(
            [
                Transaction(
                    portfolio=portfolio_core,
                    security=equity_security,
                    date=datetime(2026, 7, 1, 10, 0, 0),
                    type=TransactionType.BUY,
                    description="Core buy",
                    quantity=Decimal("1"),
                    price=Decimal("100"),
                    fees=Decimal("1"),
                    total_value=Decimal("101"),
                    currency_exchange_rate=Decimal("1"),
                ),
                Transaction(
                    portfolio=portfolio_core,
                    security=None,
                    date=datetime(2026, 7, 2, 10, 0, 0),
                    type=TransactionType.DEPOSIT,
                    description="Core cash deposit",
                    quantity=Decimal("1"),
                    price=Decimal("500"),
                    fees=Decimal("0"),
                    total_value=Decimal("500"),
                    currency_exchange_rate=Decimal("1"),
                ),
                Transaction(
                    portfolio=portfolio_income,
                    security=None,
                    date=datetime(2026, 6, 20, 10, 0, 0),
                    type=TransactionType.WITHDRAWAL,
                    description="Income withdrawal",
                    quantity=Decimal("1"),
                    price=Decimal("50"),
                    fees=Decimal("0"),
                    total_value=Decimal("-50"),
                    currency_exchange_rate=Decimal("1"),
                ),
            ]
        )
        session.commit()
        core_choice = f"{portfolio_core.id} | {portfolio_core.name}"

    core_only = list_transactions(account_filter="Real", portfolio_filter=core_choice)
    assert set(core_only["Portfolio"]) == {"Core"}

    july_window = list_transactions(
        account_filter="Real",
        start_date="2026-07-01",
        end_date="2026-07-01",
    )
    assert set(july_window["Date"]) == {"2026-07-01"}

    equity_only = list_transactions(account_filter="Real", asset_class_filter="EQUITY")
    assert len(equity_only.index) == 1
    assert set(equity_only["Ticker"]) == {"AAPL"}

    cash_only = list_transactions(account_filter="Real", asset_class_filter="CASH")
    assert set(cash_only["Ticker"]) == {""}

    deposits_only = list_transactions(account_filter="Real", transaction_type_filter="DEPOSIT")
    assert len(deposits_only.index) == 1
    assert set(deposits_only["Type"]) == {"DEPOSIT"}
