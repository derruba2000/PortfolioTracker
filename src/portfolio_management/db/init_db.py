from __future__ import annotations

from decimal import Decimal, InvalidOperation

from portfolio_management.config import load_settings
from portfolio_management.db.base import Base
from portfolio_management.db.models import (
    Account,
    AccountStrategy,
    Benchmark,
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
from sqlalchemy import text


def initialize_database(seed: bool = True) -> None:
    settings = load_settings()
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)

    engine = get_engine()
    Base.metadata.create_all(engine)
    migrate_sqlite_schema(engine)

    if seed:
        seed_defaults(engine)


def migrate_sqlite_schema(engine: object) -> None:
    """Apply small SQLite schema upgrades until a migration tool is introduced."""

    with engine.begin() as connection:
        account_columns = {
            row[1]
            for row in connection.execute(text("PRAGMA table_info(accounts)")).fetchall()
        }
        if "description" not in account_columns:
            connection.execute(text("ALTER TABLE accounts ADD COLUMN description VARCHAR(1000)"))
        if "tax_wrapper_type" not in account_columns:
            connection.execute(text("ALTER TABLE accounts ADD COLUMN tax_wrapper_type VARCHAR(64)"))
        if "is_simulated" not in account_columns:
            connection.execute(
                text("ALTER TABLE accounts ADD COLUMN is_simulated BOOLEAN NOT NULL DEFAULT 0")
            )

        portfolio_columns = {
            row[1]
            for row in connection.execute(text("PRAGMA table_info(portfolios)")).fetchall()
        }
        if "description" not in portfolio_columns:
            connection.execute(text("ALTER TABLE portfolios ADD COLUMN description VARCHAR(1000)"))

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
    """Migrate price_history.close_price from VARCHAR to DECIMAL."""
    column_type = _get_column_type(connection, "price_history", "close_price")
    if column_type and "DECIMAL" not in column_type:
        raw_rows = connection.execute(
            text("SELECT security_id, date, close_price FROM price_history")
        ).mappings().all()

        connection.execute(text("PRAGMA foreign_keys=OFF"))
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS price_history_new (
                    security_id INTEGER NOT NULL,
                    date DATE NOT NULL,
                    close_price DECIMAL(32, 10) NOT NULL,
                    PRIMARY KEY (security_id, date),
                    FOREIGN KEY(security_id) REFERENCES securities (id)
                )
                """
            )
        )
        for row in raw_rows:
            connection.execute(
                text(
                    """
                    INSERT INTO price_history_new (security_id, date, close_price)
                    VALUES (:security_id, :date, :close_price)
                    """
                ),
                {
                    "security_id": row["security_id"],
                    "date": row["date"],
                    "close_price": str(Decimal(str(row["close_price"]))),
                },
            )
        connection.execute(text("DROP TABLE price_history"))
        connection.execute(text("ALTER TABLE price_history_new RENAME TO price_history"))
        connection.execute(text("PRAGMA foreign_keys=ON"))


def _migrate_fx_rate_history_decimal(connection: object) -> None:
    """Migrate fx_rate_history.rate from VARCHAR to DECIMAL."""
    column_type = _get_column_type(connection, "fx_rate_history", "rate")
    if column_type and "DECIMAL" not in column_type:
        raw_rows = connection.execute(
            text(
                "SELECT base_currency_code, quote_currency_code, date, rate FROM fx_rate_history"
            )
        ).mappings().all()

        connection.execute(text("PRAGMA foreign_keys=OFF"))
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS fx_rate_history_new (
                    base_currency_code VARCHAR(3) NOT NULL,
                    quote_currency_code VARCHAR(3) NOT NULL,
                    date DATE NOT NULL,
                    rate DECIMAL(32, 10) NOT NULL,
                    PRIMARY KEY (base_currency_code, quote_currency_code, date)
                )
                """
            )
        )
        for row in raw_rows:
            connection.execute(
                text(
                    """
                    INSERT INTO fx_rate_history_new (base_currency_code, quote_currency_code, date, rate)
                    VALUES (:base_currency_code, :quote_currency_code, :date, :rate)
                    """
                ),
                {
                    "base_currency_code": row["base_currency_code"],
                    "quote_currency_code": row["quote_currency_code"],
                    "date": row["date"],
                    "rate": str(Decimal(str(row["rate"]))),
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


def main() -> None:
    initialize_database(seed=True)
    settings = load_settings()
    print(f"Initialized database at {settings.database_path}")


if __name__ == "__main__":
    main()
