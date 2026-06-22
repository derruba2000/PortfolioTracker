from __future__ import annotations

from decimal import Decimal

from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from portfolio_management.db.base import Base
from portfolio_management.db.init_db import migrate_sqlite_schema
from portfolio_management.db.models import (
    Account,
    AccountStrategy,
    Benchmark,
    Broker,
    Strategy,
)
from portfolio_management.db.seed import seed_defaults


def test_seed_defaults_is_idempotent() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)

    seed_defaults(engine)
    seed_defaults(engine)

    with Session(engine) as session:
        benchmarks = session.scalars(select(Benchmark)).all()
        strategies = session.scalars(select(Strategy)).all()

    assert len(benchmarks) == 3
    assert len(strategies) == 2


def test_sqlite_decimal_round_trips_exactly() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    seed_defaults(engine)

    with Session(engine) as session:
        strategy = session.scalar(select(Strategy).where(Strategy.name == "Core Growth"))
        assert strategy is not None
        value = Decimal("0.3333333333")
        broker = Broker(name="Test Broker")
        account = Account(broker=broker, name="Taxable", currency_code="USD")
        session.add(
            AccountStrategy(
                account=account,
                strategy=strategy,
                allocation_weight=value,
            )
        )
        session.commit()

    with Session(engine) as session:
        account_strategy = session.scalar(select(AccountStrategy))
        assert account_strategy is not None
        assert account_strategy.allocation_weight == Decimal(
            "0.3333333333"
        )


def test_transaction_schema_migration_preserves_decimal_values() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)

    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE accounts (id INTEGER PRIMARY KEY, name TEXT)"))
        connection.execute(
            text(
                """
                CREATE TABLE portfolios (
                    id INTEGER PRIMARY KEY,
                    account_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE transactions (
                    id INTEGER PRIMARY KEY,
                    portfolio_id INTEGER NOT NULL,
                    security_id INTEGER,
                    date DATETIME NOT NULL,
                    type VARCHAR(10) NOT NULL,
                    description VARCHAR(1000),
                    quantity VARCHAR NOT NULL,
                    price VARCHAR NOT NULL,
                    fees VARCHAR NOT NULL,
                    total_value VARCHAR NOT NULL,
                    currency_exchange_rate VARCHAR NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO transactions (
                    id,
                    portfolio_id,
                    security_id,
                    date,
                    type,
                    description,
                    quantity,
                    price,
                    fees,
                    total_value,
                    currency_exchange_rate
                ) VALUES (
                    1,
                    10,
                    NULL,
                    '2026-06-22 00:00:00',
                    'BUY',
                    'migrate',
                    '2',
                    '100.25',
                    '1.50',
                    '202.00',
                    '1.2345'
                )
                """
            )
        )

    migrate_sqlite_schema(engine)

    with engine.begin() as connection:
        type_rows = connection.execute(text("PRAGMA table_info(transactions)")).fetchall()
        type_by_column = {row[1]: row[2].upper() for row in type_rows}
        migrated_row = connection.execute(
            text(
                "SELECT quantity, price, fees, total_value, currency_exchange_rate FROM transactions WHERE id = 1"
            )
        ).fetchone()

    assert "INT" in type_by_column["quantity"]
    assert "DECIMAL" in type_by_column["price"]
    assert "DECIMAL" in type_by_column["fees"]
    assert "DECIMAL" in type_by_column["total_value"]
    assert "DECIMAL" in type_by_column["currency_exchange_rate"]
    assert migrated_row is not None
    assert migrated_row[0] == 2
    assert Decimal(str(migrated_row[1])) == Decimal("100.25")
    assert Decimal(str(migrated_row[2])) == Decimal("1.50")
    assert Decimal(str(migrated_row[3])) == Decimal("202.00")
    assert Decimal(str(migrated_row[4])) == Decimal("1.2345")


def test_transaction_schema_migration_rejects_fractional_quantity() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)

    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE accounts (id INTEGER PRIMARY KEY, name TEXT)"))
        connection.execute(
            text(
                """
                CREATE TABLE portfolios (
                    id INTEGER PRIMARY KEY,
                    account_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE transactions (
                    id INTEGER PRIMARY KEY,
                    portfolio_id INTEGER NOT NULL,
                    security_id INTEGER,
                    date DATETIME NOT NULL,
                    type VARCHAR(10) NOT NULL,
                    description VARCHAR(1000),
                    quantity VARCHAR NOT NULL,
                    price VARCHAR NOT NULL,
                    fees VARCHAR NOT NULL,
                    total_value VARCHAR NOT NULL,
                    currency_exchange_rate VARCHAR NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO transactions (
                    id,
                    portfolio_id,
                    security_id,
                    date,
                    type,
                    description,
                    quantity,
                    price,
                    fees,
                    total_value,
                    currency_exchange_rate
                ) VALUES (
                    1,
                    10,
                    NULL,
                    '2026-06-22 00:00:00',
                    'BUY',
                    'fractional',
                    '2.5',
                    '100.25',
                    '1.50',
                    '252.125',
                    '1'
                )
                """
            )
        )

    try:
        migrate_sqlite_schema(engine)
    except ValueError as exc:
        assert "Cannot migrate quantity to INTEGER without data loss" in str(exc)
    else:
        raise AssertionError("Expected migration to fail for fractional quantity.")
