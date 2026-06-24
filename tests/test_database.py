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
    ImportErrorLog,
    Strategy,
)
from portfolio_management.db.seed import seed_defaults
from portfolio_management.services.import_errors import add_import_error


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


def test_import_error_log_records_pipeline_message_and_timestamp() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        add_import_error(
            session,
            pipeline_name="test_pipeline",
            error_message="source row could not be parsed",
        )
        session.commit()

        error = session.scalar(select(ImportErrorLog))

    assert error is not None
    assert error.pipeline_name == "test_pipeline"
    assert error.error_message == "source row could not be parsed"
    assert error.timestamp is not None


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


def test_history_schema_migration_adds_ohlcv_and_preserves_close_values() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)

    with engine.begin() as connection:
        connection.execute(text("DROP TABLE price_history"))
        connection.execute(text("DROP TABLE fx_rate_history"))
        connection.execute(
            text(
                """
                CREATE TABLE price_history (
                    security_id INTEGER NOT NULL,
                    date DATE NOT NULL,
                    close_price VARCHAR NOT NULL,
                    PRIMARY KEY (security_id, date)
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE fx_rate_history (
                    base_currency_code VARCHAR(3) NOT NULL,
                    quote_currency_code VARCHAR(3) NOT NULL,
                    date DATE NOT NULL,
                    rate VARCHAR NOT NULL,
                    PRIMARY KEY (base_currency_code, quote_currency_code, date)
                )
                """
            )
        )
        connection.execute(
            text(
                "INSERT INTO price_history VALUES (1, '2026-06-20', '101.5')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO fx_rate_history VALUES ('EUR', 'GBP', '2026-06-20', '0.85')"
            )
        )

    migrate_sqlite_schema(engine)

    with engine.begin() as connection:
        price_columns = {
            row[1] for row in connection.execute(text("PRAGMA table_info(price_history)"))
        }
        fx_columns = {
            row[1] for row in connection.execute(text("PRAGMA table_info(fx_rate_history)"))
        }
        price = connection.execute(
            text("SELECT symbol, open, high, low, close, volume FROM price_history")
        ).one()
        fx_rate = connection.execute(
            text("SELECT symbol, open, high, low, close, volume FROM fx_rate_history")
        ).one()

    assert {"symbol", "date", "open", "high", "low", "close", "volume"} <= price_columns
    assert {"symbol", "date", "open", "high", "low", "close", "volume"} <= fx_columns
    assert Decimal(str(price.close)) == Decimal("101.5")
    assert Decimal(str(fx_rate.close)) == Decimal("0.85")
    assert fx_rate.symbol == "EURGBP=X"
