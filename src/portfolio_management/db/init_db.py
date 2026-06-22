from __future__ import annotations

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

        if "account_id" in transaction_columns:
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
                        quantity VARCHAR NOT NULL,
                        price VARCHAR NOT NULL,
                        fees VARCHAR NOT NULL,
                        total_value VARCHAR NOT NULL,
                        currency_exchange_rate VARCHAR NOT NULL,
                        PRIMARY KEY (id),
                        FOREIGN KEY(portfolio_id) REFERENCES portfolios (id),
                        FOREIGN KEY(security_id) REFERENCES securities (id)
                    )
                    """
                )
            )
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
                    )
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
            )
            connection.execute(text("DROP TABLE transactions"))
            connection.execute(text("ALTER TABLE transactions_new RENAME TO transactions"))
            connection.execute(text("PRAGMA foreign_keys=ON"))


def main() -> None:
    initialize_database(seed=True)
    settings = load_settings()
    print(f"Initialized database at {settings.database_path}")


if __name__ == "__main__":
    main()
