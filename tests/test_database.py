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


def test_schema_migration_replaces_alert_account_ids_with_names() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO brokers (
                    id,
                    name,
                    is_active,
                    trade_fee_fixed,
                    trade_fee_percent,
                    fx_fee_percent,
                    spread_fee_percent,
                    custody_fee_percent_annual,
                    platform_fee_fixed_monthly,
                    account_fee_fixed_monthly,
                    inactivity_fee_fixed_monthly,
                    withdrawal_fee_fixed,
                    deposit_fee_fixed,
                    stamp_duty_percent,
                    regulatory_fee_percent,
                    margin_interest_percent_annual,
                    short_borrow_fee_percent_annual
                ) VALUES (
                    1,
                    'Broker',
                    1,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO accounts (
                    id, broker_id, name, currency_code, is_simulated, is_active
                ) VALUES (
                    7, 1, 'Retirement ISA', 'GBP', 0, 1
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO portfolios (id, account_id, name, is_active)
                VALUES (1, 7, 'Default Portfolio', 1)
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO portfolio_alerts (
                    alert_hash, alert_type, message
                ) VALUES (
                    'legacy-drift',
                    'DRIFT',
                    'DRIFT ALERT: EQUITY is 6.0% above target for account 7, exceeding tolerance.'
                )
                """
            )
        )

    migrate_sqlite_schema(engine)

    with engine.begin() as connection:
        message = connection.execute(
            text(
                "SELECT message FROM portfolio_alerts WHERE alert_hash = 'legacy-drift'"
            )
        ).scalar_one()

    assert "for Retirement ISA" in message
    assert "account 7" not in message


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


def test_security_migration_adds_asset_subclass_and_removes_etf_master_data() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)

    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE brokers (id INTEGER PRIMARY KEY, name TEXT)"))
        connection.execute(text("CREATE TABLE accounts (id INTEGER PRIMARY KEY, name TEXT)"))
        connection.execute(
            text(
                """
                CREATE TABLE portfolios (
                    id INTEGER PRIMARY KEY,
                    account_id INTEGER NOT NULL,
                    name TEXT NOT NULL
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
                    quantity INTEGER NOT NULL,
                    price DECIMAL NOT NULL,
                    fees DECIMAL NOT NULL,
                    total_value DECIMAL NOT NULL,
                    currency_exchange_rate DECIMAL NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE securities (
                    id INTEGER PRIMARY KEY,
                    ticker VARCHAR(32) NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    asset_class VARCHAR(32) NOT NULL,
                    currency_code VARCHAR(3) NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE asset_classes (
                    code VARCHAR(32) PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    display_order INTEGER NOT NULL
                )
                """
            )
        )
        connection.execute(text("INSERT INTO asset_classes VALUES ('ETF', 'ETF', 2)"))
        connection.execute(
            text(
                """
                INSERT INTO securities (id, ticker, name, asset_class, currency_code)
                VALUES (1, 'VWRP', 'Vanguard ETF', 'ETF', 'GBP')
                """
            )
        )

    migrate_sqlite_schema(engine)

    with engine.begin() as connection:
        columns = {
            row[1]
            for row in connection.execute(text("PRAGMA table_info(securities)")).fetchall()
        }
        security = connection.execute(
            text("SELECT asset_class, asset_subclass FROM securities WHERE id = 1")
        ).one()
        etf_master_count = connection.execute(
            text("SELECT COUNT(*) FROM asset_classes WHERE code = 'ETF'")
        ).scalar_one()

    assert "asset_subclass" in columns
    assert security == ("EQUITY", "ETF 100% EQUITY")
    assert etf_master_count == 0
