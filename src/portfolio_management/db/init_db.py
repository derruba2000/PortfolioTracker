from __future__ import annotations

from decimal import Decimal, InvalidOperation

from portfolio_management.config import load_settings
from portfolio_management.db.base import Base
from portfolio_management.db.models import (
    Account,
    AccountStrategy,
    Benchmark,
    AssetClassOption,
    Currency,
    FxRateHistory,
    Broker,
    PriceHistory,
    Portfolio,
    Security,
    Strategy,
    Transaction,
)
from portfolio_management.db.seed import seed_defaults
from portfolio_management.db.session import get_engine
from portfolio_management.services.reference_data import seed_reference_data
from sqlalchemy import text


def initialize_database(seed: bool = True) -> None:
    settings = load_settings()
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)

    engine = get_engine()
    Base.metadata.create_all(engine)
    migrate_sqlite_schema(engine)

    if seed:
        seed_defaults(engine)
        with engine.begin() as connection:
            from sqlalchemy.orm import Session

            with Session(bind=connection) as session:
                seed_reference_data(session)
                session.commit()


def migrate_sqlite_schema(engine: object) -> None:
    """Apply small SQLite schema upgrades until a migration tool is introduced."""

    with engine.begin() as connection:
        broker_columns = {
            row[1]
            for row in connection.execute(text("PRAGMA table_info(brokers)")).fetchall()
        }
        if broker_columns and "description" not in broker_columns:
            connection.execute(text("ALTER TABLE brokers ADD COLUMN description VARCHAR(1000)"))
        if broker_columns and "is_active" not in broker_columns:
            connection.execute(
                text("ALTER TABLE brokers ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1")
            )

        account_columns = {
            row[1]
            for row in connection.execute(text("PRAGMA table_info(accounts)")).fetchall()
        }
        if account_columns and "description" not in account_columns:
            connection.execute(text("ALTER TABLE accounts ADD COLUMN description VARCHAR(1000)"))
        if account_columns and "tax_wrapper_type" not in account_columns:
            connection.execute(text("ALTER TABLE accounts ADD COLUMN tax_wrapper_type VARCHAR(64)"))
        if account_columns and "is_simulated" not in account_columns:
            connection.execute(
                text("ALTER TABLE accounts ADD COLUMN is_simulated BOOLEAN NOT NULL DEFAULT 0")
            )
        if account_columns and "is_active" not in account_columns:
            connection.execute(
                text("ALTER TABLE accounts ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1")
            )

        portfolio_columns = {
            row[1]
            for row in connection.execute(text("PRAGMA table_info(portfolios)")).fetchall()
        }
        if portfolio_columns and "description" not in portfolio_columns:
            connection.execute(text("ALTER TABLE portfolios ADD COLUMN description VARCHAR(1000)"))
        if portfolio_columns and "portfolio_url" not in portfolio_columns:
            connection.execute(text("ALTER TABLE portfolios ADD COLUMN portfolio_url VARCHAR(2000)"))
        if portfolio_columns and "is_active" not in portfolio_columns:
            connection.execute(
                text("ALTER TABLE portfolios ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1")
            )

        security_columns = {
            row[1]
            for row in connection.execute(text("PRAGMA table_info(securities)"))
        }
        if security_columns and "description" not in security_columns:
            connection.execute(text("ALTER TABLE securities ADD COLUMN description VARCHAR(1000)"))

        reference_tables = {
            row[0]
            for row in connection.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            ).fetchall()
        }
        if "asset_classes" not in reference_tables:
            connection.execute(
                text(
                    """
                    CREATE TABLE asset_classes (
                        code VARCHAR(32) NOT NULL,
                        name VARCHAR(255) NOT NULL,
                        display_order INTEGER NOT NULL DEFAULT 0,
                        PRIMARY KEY (code)
                    )
                    """
                )
            )
        if "currencies" not in reference_tables:
            connection.execute(
                text(
                    """
                    CREATE TABLE currencies (
                        code VARCHAR(3) NOT NULL,
                        name VARCHAR(255) NOT NULL,
                        display_order INTEGER NOT NULL DEFAULT 0,
                        PRIMARY KEY (code)
                    )
                    """
                )
            )

        transaction_columns = {
            row[1]
            for row in connection.execute(text("PRAGMA table_info(transactions)")).fetchall()
        }
        if "portfolio_id" not in transaction_columns:
            connection.execute(text("ALTER TABLE transactions ADD COLUMN portfolio_id INTEGER"))
            transaction_columns.add("portfolio_id")
        if "description" not in transaction_columns:
            connection.execute(text("ALTER TABLE transactions ADD COLUMN description VARCHAR(1000)"))
            transaction_columns.add("description")

        account_rows = connection.execute(text("SELECT id FROM accounts")).fetchall()
        for (account_id,) in account_rows:
            portfolio_id = connection.execute(
                text(
                    "SELECT id FROM portfolios "
                    "WHERE account_id = :account_id AND name = 'Default Portfolio'"
                ),
                {"account_id": account_id},
            ).scalar_one_or_none()
            if portfolio_id is None:
                connection.execute(
                    text(
                        "INSERT INTO portfolios (account_id, name) "
                        "VALUES (:account_id, 'Default Portfolio')"
                    ),
                    {"account_id": account_id},
                )
                portfolio_id = connection.execute(text("SELECT last_insert_rowid()")).scalar_one()

            if "account_id" in transaction_columns:
                connection.execute(
                    text(
                        "UPDATE transactions SET portfolio_id = :portfolio_id "
                        "WHERE portfolio_id IS NULL AND account_id = :account_id"
                    ),
                    {"portfolio_id": portfolio_id, "account_id": account_id},
                )

        transaction_column_types = {
            row[1]: (row[2] or "").upper()
            for row in connection.execute(text("PRAGMA table_info(transactions)")).fetchall()
        }

        decimal_columns = ("price", "fees", "total_value", "currency_exchange_rate")
        needs_decimal_type_upgrade = any(
            "DECIMAL" not in transaction_column_types.get(column, "")
            for column in decimal_columns
        )
        needs_quantity_type_upgrade = "INT" not in transaction_column_types.get("quantity", "")

        if "account_id" in transaction_columns or needs_decimal_type_upgrade or needs_quantity_type_upgrade:
            raw_rows = connection.execute(
                text(
                    """
                    SELECT
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
                    FROM transactions
                    WHERE portfolio_id IS NOT NULL
                    """
                )
            ).mappings().all()

            converted_rows = []
            non_integer_quantities: list[tuple[int, str]] = []

            for row in raw_rows:
                try:
                    quantity_decimal = Decimal(str(row["quantity"]))
                except (InvalidOperation, ValueError) as exc:
                    raise ValueError(
                        f"Cannot migrate transactions.quantity for row id {row['id']}: {row['quantity']}"
                    ) from exc

                if quantity_decimal != quantity_decimal.to_integral_value():
                    non_integer_quantities.append((row["id"], str(row["quantity"])))
                    continue

                converted_rows.append(
                    {
                        "id": row["id"],
                        "portfolio_id": row["portfolio_id"],
                        "security_id": row["security_id"],
                        "date": row["date"],
                        "type": row["type"],
                        "description": row["description"],
                        "quantity": int(quantity_decimal),
                        "price": str(Decimal(str(row["price"]))),
                        "fees": str(Decimal(str(row["fees"]))),
                        "total_value": str(Decimal(str(row["total_value"]))),
                        "currency_exchange_rate": str(Decimal(str(row["currency_exchange_rate"]))),
                    }
                )

            if non_integer_quantities:
                sample = ", ".join(
                    f"id={row_id} quantity={value}"
                    for row_id, value in non_integer_quantities[:5]
                )
                raise ValueError(
                    "Cannot migrate quantity to INTEGER without data loss. "
                    f"Found non-integer quantities: {sample}"
                )

            connection.execute(text("PRAGMA foreign_keys=OFF"))
            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS transactions_new (
                        id INTEGER NOT NULL,
                        portfolio_id INTEGER NOT NULL,
                        security_id INTEGER,
                        date DATETIME NOT NULL,
                        type VARCHAR(10) NOT NULL,
                        description VARCHAR(1000),
                        quantity INTEGER NOT NULL,
                        price DECIMAL(32, 10) NOT NULL,
                        fees DECIMAL(32, 10) NOT NULL,
                        total_value DECIMAL(32, 10) NOT NULL,
                        currency_exchange_rate DECIMAL(32, 10) NOT NULL,
                        PRIMARY KEY (id),
                        FOREIGN KEY(portfolio_id) REFERENCES portfolios (id),
                        FOREIGN KEY(security_id) REFERENCES securities (id)
                    )
                    """
                )
            )
            for row in converted_rows:
                connection.execute(
                    text(
                        """
                        INSERT INTO transactions_new (
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
                            :id,
                            :portfolio_id,
                            :security_id,
                            :date,
                            :type,
                            :description,
                            :quantity,
                            :price,
                            :fees,
                            :total_value,
                            :currency_exchange_rate
                        )
                        """
                    ),
                    row,
                )
            connection.execute(text("DROP TABLE transactions"))
            connection.execute(text("ALTER TABLE transactions_new RENAME TO transactions"))
            connection.execute(text("PRAGMA foreign_keys=ON"))

        _migrate_account_strategies_decimal(connection)
        _migrate_price_history_decimal(connection)
        _migrate_fx_rate_history_decimal(connection)


def _migrate_account_strategies_decimal(connection: object) -> None:
    """Migrate account_strategies.allocation_weight from VARCHAR to DECIMAL."""
    column_type = _get_column_type(connection, "account_strategies", "allocation_weight")
    if column_type and "DECIMAL" not in column_type:
        raw_rows = connection.execute(
            text("SELECT account_id, strategy_id, allocation_weight FROM account_strategies")
        ).mappings().all()

        connection.execute(text("PRAGMA foreign_keys=OFF"))
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS account_strategies_new (
                    account_id INTEGER NOT NULL,
                    strategy_id INTEGER NOT NULL,
                    allocation_weight DECIMAL(32, 10) NOT NULL,
                    PRIMARY KEY (account_id, strategy_id),
                    FOREIGN KEY(account_id) REFERENCES accounts (id),
                    FOREIGN KEY(strategy_id) REFERENCES strategies (id)
                )
                """
            )
        )
        for row in raw_rows:
            connection.execute(
                text(
                    """
                    INSERT INTO account_strategies_new (account_id, strategy_id, allocation_weight)
                    VALUES (:account_id, :strategy_id, :allocation_weight)
                    """
                ),
                {
                    "account_id": row["account_id"],
                    "strategy_id": row["strategy_id"],
                    "allocation_weight": str(Decimal(str(row["allocation_weight"]))),
                },
            )
        connection.execute(text("DROP TABLE account_strategies"))
        connection.execute(text("ALTER TABLE account_strategies_new RENAME TO account_strategies"))
        connection.execute(text("PRAGMA foreign_keys=ON"))


def _migrate_price_history_decimal(connection: object) -> None:
    """Upgrade price history to the symbol/date/OHLCV schema."""
    columns = _get_columns(connection, "price_history")
    if not columns:
        return
    required = {"security_id", "symbol", "date", "open", "high", "low", "close", "volume"}
    close_column = "close" if "close" in columns else "close_price"
    needs_upgrade = (
        not required.issubset(columns)
        or close_column == "close_price"
        or not _is_decimal_column(columns.get("close", ""))
    )
    if needs_upgrade:
        selected = ["security_id", "date", close_column]
        selected.extend(
            column for column in ("symbol", "open", "high", "low", "volume") if column in columns
        )
        raw_rows = connection.execute(
            text(f"SELECT {', '.join(selected)} FROM price_history")
        ).mappings().all()

        connection.execute(text("PRAGMA foreign_keys=OFF"))
        connection.execute(text("DROP TABLE IF EXISTS price_history_new"))
        connection.execute(
            text(
                """
                CREATE TABLE price_history_new (
                    security_id INTEGER NOT NULL,
                    symbol VARCHAR(32),
                    date DATE NOT NULL,
                    open NUMERIC(32, 10),
                    high NUMERIC(32, 10),
                    low NUMERIC(32, 10),
                    close NUMERIC(32, 10) NOT NULL,
                    volume NUMERIC(32, 10),
                    PRIMARY KEY (security_id, date),
                    FOREIGN KEY(security_id) REFERENCES securities (id)
                )
                """
            )
        )
        for row in raw_rows:
            close_value = str(Decimal(str(row[close_column])))
            symbol = row.get("symbol")
            if not symbol:
                symbol = connection.execute(
                    text("SELECT ticker FROM securities WHERE id = :security_id"),
                    {"security_id": row["security_id"]},
                ).scalar_one_or_none()
            connection.execute(
                text(
                    """
                    INSERT INTO price_history_new (
                        security_id, symbol, date, open, high, low, close, volume
                    ) VALUES (
                        :security_id, :symbol, :date, :open, :high, :low, :close, :volume
                    )
                    """
                ),
                {
                    "security_id": row["security_id"],
                    "symbol": symbol,
                    "date": row["date"],
                    "open": _decimal_or_default(row.get("open"), close_value),
                    "high": _decimal_or_default(row.get("high"), close_value),
                    "low": _decimal_or_default(row.get("low"), close_value),
                    "close": close_value,
                    "volume": _decimal_or_none(row.get("volume")),
                },
            )
        connection.execute(text("DROP TABLE price_history"))
        connection.execute(text("ALTER TABLE price_history_new RENAME TO price_history"))
        connection.execute(text("PRAGMA foreign_keys=ON"))


def _migrate_fx_rate_history_decimal(connection: object) -> None:
    """Upgrade FX history to the symbol/date/OHLCV schema."""
    columns = _get_columns(connection, "fx_rate_history")
    if not columns:
        return
    required = {
        "base_currency_code",
        "quote_currency_code",
        "symbol",
        "date",
        "open",
        "high",
        "low",
        "close",
        "volume",
    }
    close_column = "close" if "close" in columns else "rate"
    needs_upgrade = (
        not required.issubset(columns)
        or close_column == "rate"
        or not _is_decimal_column(columns.get("close", ""))
    )
    if needs_upgrade:
        selected = ["base_currency_code", "quote_currency_code", "date", close_column]
        selected.extend(
            column for column in ("symbol", "open", "high", "low", "volume") if column in columns
        )
        raw_rows = connection.execute(
            text(f"SELECT {', '.join(selected)} FROM fx_rate_history")
        ).mappings().all()

        connection.execute(text("PRAGMA foreign_keys=OFF"))
        connection.execute(text("DROP TABLE IF EXISTS fx_rate_history_new"))
        connection.execute(
            text(
                """
                CREATE TABLE fx_rate_history_new (
                    base_currency_code VARCHAR(3) NOT NULL,
                    quote_currency_code VARCHAR(3) NOT NULL,
                    symbol VARCHAR(32),
                    date DATE NOT NULL,
                    open NUMERIC(32, 10),
                    high NUMERIC(32, 10),
                    low NUMERIC(32, 10),
                    close NUMERIC(32, 10) NOT NULL,
                    volume NUMERIC(32, 10),
                    PRIMARY KEY (base_currency_code, quote_currency_code, date)
                )
                """
            )
        )
        for row in raw_rows:
            close_value = str(Decimal(str(row[close_column])))
            symbol = row.get("symbol") or (
                f"{row['base_currency_code']}{row['quote_currency_code']}=X"
            )
            connection.execute(
                text(
                    """
                    INSERT INTO fx_rate_history_new (
                        base_currency_code, quote_currency_code, symbol, date,
                        open, high, low, close, volume
                    ) VALUES (
                        :base_currency_code, :quote_currency_code, :symbol, :date,
                        :open, :high, :low, :close, :volume
                    )
                    """
                ),
                {
                    "base_currency_code": row["base_currency_code"],
                    "quote_currency_code": row["quote_currency_code"],
                    "symbol": symbol,
                    "date": row["date"],
                    "open": _decimal_or_default(row.get("open"), close_value),
                    "high": _decimal_or_default(row.get("high"), close_value),
                    "low": _decimal_or_default(row.get("low"), close_value),
                    "close": close_value,
                    "volume": _decimal_or_none(row.get("volume")),
                },
            )
        connection.execute(text("DROP TABLE fx_rate_history"))
        connection.execute(text("ALTER TABLE fx_rate_history_new RENAME TO fx_rate_history"))
        connection.execute(text("PRAGMA foreign_keys=ON"))


def _get_column_type(connection: object, table_name: str, column_name: str) -> str | None:
    """Get the type of a column if the table exists, otherwise return None."""
    try:
        rows = connection.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
        for row in rows:
            if row[1] == column_name:
                return row[2].upper() if row[2] else None
        return None
    except Exception:
        return None


def _get_columns(connection: object, table_name: str) -> dict[str, str]:
    try:
        return {
            row[1]: (row[2] or "").upper()
            for row in connection.execute(text(f"PRAGMA table_info({table_name})")).fetchall()
        }
    except Exception:
        return {}


def _is_decimal_column(column_type: str) -> bool:
    return "DECIMAL" in column_type or "NUMERIC" in column_type


def _decimal_or_default(value: object, default: str) -> str:
    if value is None:
        return default
    return str(Decimal(str(value)))


def _decimal_or_none(value: object) -> str | None:
    if value is None:
        return None
    return str(Decimal(str(value)))


def main() -> None:
    initialize_database(seed=True)
    settings = load_settings()
    print(f"Initialized database at {settings.database_path}")


if __name__ == "__main__":
    main()
