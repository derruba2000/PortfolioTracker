from __future__ import annotations

import re
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
    PortfolioAlert,
    PriceHistory,
    Portfolio,
    PortfolioStrategy,
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
        _ensure_orders_table(connection)
        _ensure_portfolio_strategies_table(connection)

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
        broker_fee_columns = [
            "trade_fee_fixed",
            "trade_fee_percent",
            "fx_fee_percent",
            "spread_fee_percent",
            "custody_fee_percent_annual",
            "platform_fee_fixed_monthly",
            "account_fee_fixed_monthly",
            "inactivity_fee_fixed_monthly",
            "withdrawal_fee_fixed",
            "deposit_fee_fixed",
            "stamp_duty_percent",
            "regulatory_fee_percent",
            "margin_interest_percent_annual",
            "short_borrow_fee_percent_annual",
        ]
        for column in broker_fee_columns:
            if broker_columns and column not in broker_columns:
                connection.execute(
                    text(
                        f"ALTER TABLE brokers ADD COLUMN {column} NUMERIC NOT NULL DEFAULT 0"
                    )
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
        if portfolio_columns and "portfolio_goals" not in portfolio_columns:
            connection.execute(text("ALTER TABLE portfolios ADD COLUMN portfolio_goals TEXT"))
        if portfolio_columns and "goal_type" not in portfolio_columns:
            connection.execute(text("ALTER TABLE portfolios ADD COLUMN goal_type VARCHAR(64)"))
        if portfolio_columns and "goal_timeline" not in portfolio_columns:
            connection.execute(text("ALTER TABLE portfolios ADD COLUMN goal_timeline VARCHAR(64)"))
        if portfolio_columns and "rewritten_goals" not in portfolio_columns:
            connection.execute(text("ALTER TABLE portfolios ADD COLUMN rewritten_goals TEXT"))
        if portfolio_columns and "strategy_recommendation" not in portfolio_columns:
            connection.execute(text("ALTER TABLE portfolios ADD COLUMN strategy_recommendation TEXT"))
        if portfolio_columns and "portfolio_profile" not in portfolio_columns:
            connection.execute(text("ALTER TABLE portfolios ADD COLUMN portfolio_profile TEXT"))
        if portfolio_columns and "ai_notes" not in portfolio_columns:
            connection.execute(text("ALTER TABLE portfolios ADD COLUMN ai_notes TEXT"))
        if portfolio_columns and "llm_updated_at" not in portfolio_columns:
            connection.execute(text("ALTER TABLE portfolios ADD COLUMN llm_updated_at DATETIME"))
        if portfolio_columns and "is_active" not in portfolio_columns:
            connection.execute(
                text("ALTER TABLE portfolios ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1")
            )
        portfolio_columns = {
            row[1]
            for row in connection.execute(text("PRAGMA table_info(portfolios)")).fetchall()
        }
        if "target_drift_percent" in portfolio_columns:
            _drop_portfolio_target_drift_column(connection)

        security_columns = {
            row[1]
            for row in connection.execute(text("PRAGMA table_info(securities)"))
        }
        if security_columns and "description" not in security_columns:
            connection.execute(text("ALTER TABLE securities ADD COLUMN description VARCHAR(1000)"))
        if security_columns and "asset_subclass" not in security_columns:
            connection.execute(
                text(
                    "ALTER TABLE securities "
                    "ADD COLUMN asset_subclass VARCHAR(64) NOT NULL DEFAULT 'STOCK'"
                )
            )
            security_columns.add("asset_subclass")
            connection.execute(
                text(
                    """
                    UPDATE securities
                    SET asset_subclass = CASE asset_class
                        WHEN 'BOND' THEN 'BOND'
                        WHEN 'ETF' THEN 'ETF 100% EQUITY'
                        WHEN 'CRYPTO' THEN 'CRYPTO'
                        WHEN 'REAL_ESTATE' THEN 'REAL ESTATE'
                        WHEN 'COMMODITY' THEN 'COMMODITY'
                        WHEN 'CASH' THEN 'CASH'
                        ELSE 'STOCK'
                    END
                    """
                )
            )
        if security_columns and "asset_class" in security_columns:
            connection.execute(
                text("UPDATE securities SET asset_class = 'EQUITY' WHERE asset_class = 'ETF'")
            )

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
        else:
            connection.execute(text("DELETE FROM asset_classes WHERE code = 'ETF'"))
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
        if "order_id" not in transaction_columns:
            connection.execute(text("ALTER TABLE transactions ADD COLUMN order_id INTEGER"))
            transaction_columns.add("order_id")
        if "description" not in transaction_columns:
            connection.execute(text("ALTER TABLE transactions ADD COLUMN description VARCHAR(1000)"))
            transaction_columns.add("description")

        account_rows = connection.execute(text("SELECT id FROM accounts")).fetchall()
        for (account_id,) in account_rows:
            if "account_id" in transaction_columns:
                needs_backfill = connection.execute(
                    text(
                        "SELECT 1 FROM transactions "
                        "WHERE portfolio_id IS NULL AND account_id = :account_id "
                        "LIMIT 1"
                    ),
                    {"account_id": account_id},
                ).scalar_one_or_none()
                if needs_backfill is None:
                    continue

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
        needs_quantity_type_upgrade = "DECIMAL" not in transaction_column_types.get("quantity", "")

        if "account_id" in transaction_columns or needs_decimal_type_upgrade or needs_quantity_type_upgrade:
            raw_rows = connection.execute(
                text(
                    """
                    SELECT
                        id,
                        order_id,
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

            for row in raw_rows:
                try:
                    quantity_decimal = Decimal(str(row["quantity"]))
                except (InvalidOperation, ValueError) as exc:
                    raise ValueError(
                        f"Cannot migrate transactions.quantity for row id {row['id']}: {row['quantity']}"
                    ) from exc

                converted_rows.append(
                    {
                        "id": row["id"],
                        "order_id": row["order_id"],
                        "portfolio_id": row["portfolio_id"],
                        "security_id": row["security_id"],
                        "date": row["date"],
                        "type": row["type"],
                        "description": row["description"],
                        "quantity": str(quantity_decimal),
                        "price": str(Decimal(str(row["price"]))),
                        "fees": str(Decimal(str(row["fees"]))),
                        "total_value": str(Decimal(str(row["total_value"]))),
                        "currency_exchange_rate": str(Decimal(str(row["currency_exchange_rate"]))),
                    }
                )

            connection.execute(text("PRAGMA foreign_keys=OFF"))
            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS transactions_new (
                        id INTEGER NOT NULL,
                        order_id INTEGER,
                        portfolio_id INTEGER NOT NULL,
                        security_id INTEGER,
                        date DATETIME NOT NULL,
                        type VARCHAR(10) NOT NULL,
                        description VARCHAR(1000),
                        quantity DECIMAL(32, 10) NOT NULL,
                        price DECIMAL(32, 10) NOT NULL,
                        fees DECIMAL(32, 10) NOT NULL,
                        total_value DECIMAL(32, 10) NOT NULL,
                        currency_exchange_rate DECIMAL(32, 10) NOT NULL,
                        PRIMARY KEY (id),
                        FOREIGN KEY(order_id) REFERENCES orders (id),
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
                            order_id,
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
                            :order_id,
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
        _migrate_alert_account_names(connection)
        _migrate_legacy_transactions_to_orders(connection)


def _ensure_orders_table(connection: object) -> None:
    tables = {
        row[0]
        for row in connection.execute(
            text("SELECT name FROM sqlite_master WHERE type='table'")
        ).fetchall()
    }
    if "orders" in tables:
        columns = {row[1] for row in connection.execute(text("PRAGMA table_info(orders)")).fetchall()}
        if "currency_code" not in columns:
            connection.execute(text("ALTER TABLE orders ADD COLUMN currency_code VARCHAR(3)"))
            connection.execute(
                text(
                    """
                    UPDATE orders
                    SET currency_code = COALESCE(
                        (
                            SELECT accounts.currency_code
                            FROM portfolios
                            JOIN accounts ON accounts.id = portfolios.account_id
                            WHERE portfolios.id = orders.portfolio_id
                        ),
                        'USD'
                    )
                    WHERE currency_code IS NULL OR currency_code = ''
                    """
                )
            )
        return
    connection.execute(
        text(
            """
            CREATE TABLE orders (
                id INTEGER NOT NULL,
                portfolio_id INTEGER NOT NULL,
                security_id INTEGER,
                order_type VARCHAR(8) NOT NULL,
                status VARCHAR(9) NOT NULL DEFAULT 'PENDING',
                target_quantity DECIMAL(32, 10),
                target_price DECIMAL(32, 10),
                target_cash_amount DECIMAL(32, 10),
                currency_code VARCHAR(3) NOT NULL DEFAULT 'USD',
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                executed_at DATETIME,
                PRIMARY KEY (id),
                FOREIGN KEY(portfolio_id) REFERENCES portfolios (id),
                FOREIGN KEY(security_id) REFERENCES securities (id)
            )
            """
        )
    )


def _ensure_portfolio_strategies_table(connection: object) -> None:
    tables = {
        row[0]
        for row in connection.execute(
            text("SELECT name FROM sqlite_master WHERE type='table'")
        ).fetchall()
    }
    if "portfolio_strategies" in tables:
        return
    connection.execute(
        text(
            """
            CREATE TABLE portfolio_strategies (
                portfolio_id INTEGER NOT NULL,
                strategy_id INTEGER NOT NULL,
                allocation_weight DECIMAL(32, 10) NOT NULL,
                drift_up_percent DECIMAL(32, 10) NOT NULL DEFAULT 5,
                drift_down_percent DECIMAL(32, 10) NOT NULL DEFAULT 5,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (portfolio_id, strategy_id),
                FOREIGN KEY(portfolio_id) REFERENCES portfolios (id),
                FOREIGN KEY(strategy_id) REFERENCES strategies (id)
            )
            """
        )
    )


def _drop_portfolio_target_drift_column(connection: object) -> None:
    connection.execute(text("PRAGMA foreign_keys=OFF"))
    connection.execute(
        text(
            """
            CREATE TABLE portfolios_new (
                id INTEGER NOT NULL,
                account_id INTEGER NOT NULL,
                name VARCHAR(255) NOT NULL,
                description VARCHAR(1000),
                portfolio_url VARCHAR(2000),
                portfolio_goals TEXT,
                goal_type VARCHAR(64),
                goal_timeline VARCHAR(64),
                rewritten_goals TEXT,
                strategy_recommendation TEXT,
                portfolio_profile TEXT,
                ai_notes TEXT,
                llm_updated_at DATETIME,
                is_active BOOLEAN NOT NULL DEFAULT 1,
                PRIMARY KEY (id),
                CONSTRAINT uq_portfolios_account_name UNIQUE (account_id, name),
                FOREIGN KEY(account_id) REFERENCES accounts (id)
            )
            """
        )
    )
    connection.execute(
        text(
            """
            INSERT INTO portfolios_new (
                id,
                account_id,
                name,
                description,
                portfolio_url,
                portfolio_goals,
                goal_type,
                goal_timeline,
                rewritten_goals,
                strategy_recommendation,
                portfolio_profile,
                ai_notes,
                llm_updated_at,
                is_active
            )
            SELECT
                id,
                account_id,
                name,
                description,
                portfolio_url,
                portfolio_goals,
                goal_type,
                goal_timeline,
                rewritten_goals,
                strategy_recommendation,
                portfolio_profile,
                ai_notes,
                llm_updated_at,
                COALESCE(is_active, 1)
            FROM portfolios
            """
        )
    )
    connection.execute(text("DROP TABLE portfolios"))
    connection.execute(text("ALTER TABLE portfolios_new RENAME TO portfolios"))
    connection.execute(text("PRAGMA foreign_keys=ON"))


def _migrate_legacy_transactions_to_orders(connection: object) -> None:
    tables = {
        row[0]
        for row in connection.execute(
            text("SELECT name FROM sqlite_master WHERE type='table'")
        ).fetchall()
    }
    if "transactions" not in tables or "orders" not in tables:
        return

    transaction_columns = {
        row[1]
        for row in connection.execute(text("PRAGMA table_info(transactions)")).fetchall()
    }
    if "order_id" not in transaction_columns:
        return

    rows = connection.execute(
        text(
            """
            SELECT
                id,
                portfolio_id,
                security_id,
                type,
                quantity,
                price,
                total_value,
                date
            FROM transactions
            WHERE order_id IS NULL
            ORDER BY date, id
            """
        )
    ).mappings().all()

    for row in rows:
        order_type = _order_type_from_transaction_type(str(row["type"]), row["security_id"])
        target_quantity = _decimal_or_none(row["quantity"])
        target_price = _decimal_or_none(row["price"]) if row["security_id"] is not None else None
        target_cash_amount = (
            _decimal_or_none(abs(Decimal(str(row["total_value"]))))
            if order_type in {"DEPOSIT", "WITHDRAW"}
            else None
        )
        transaction_timestamp = row["date"]

        connection.execute(
            text(
                """
                INSERT INTO orders (
                    portfolio_id,
                    security_id,
                    order_type,
                    status,
                    target_quantity,
                    target_price,
                    target_cash_amount,
                    created_at,
                    executed_at
                ) VALUES (
                    :portfolio_id,
                    :security_id,
                    :order_type,
                    'EXECUTED',
                    :target_quantity,
                    :target_price,
                    :target_cash_amount,
                    :created_at,
                    :executed_at
                )
                """
            ),
            {
                "portfolio_id": row["portfolio_id"],
                "security_id": row["security_id"],
                "order_type": order_type,
                "target_quantity": target_quantity,
                "target_price": target_price,
                "target_cash_amount": target_cash_amount,
                "created_at": transaction_timestamp,
                "executed_at": transaction_timestamp,
            },
        )
        new_order_id = connection.execute(text("SELECT last_insert_rowid()")).scalar_one()
        connection.execute(
            text("UPDATE transactions SET order_id = :order_id WHERE id = :transaction_id"),
            {"order_id": new_order_id, "transaction_id": row["id"]},
        )


def _order_type_from_transaction_type(transaction_type: str, security_id: object) -> str:
    if transaction_type == "BUY":
        return "BUY"
    if transaction_type == "SELL":
        return "SELL"
    if transaction_type == "DEPOSIT":
        return "DEPOSIT"
    if transaction_type == "WITHDRAWAL":
        return "WITHDRAW"
    if transaction_type == "DIVIDEND":
        return "DEPOSIT"
    if transaction_type == "SPLIT":
        return "BUY"
    return "BUY" if security_id is not None else "DEPOSIT"


def _migrate_alert_account_names(connection: object) -> None:
    """Replace legacy account IDs in drift messages with account names."""
    tables = {
        row[0]
        for row in connection.execute(
            text("SELECT name FROM sqlite_master WHERE type='table'")
        ).fetchall()
    }
    if "portfolio_alerts" not in tables or "accounts" not in tables:
        return

    account_names = dict(
        connection.execute(text("SELECT id, name FROM accounts")).fetchall()
    )
    alerts = connection.execute(
        text(
            """
            SELECT id, message
            FROM portfolio_alerts
            WHERE alert_type = 'DRIFT' AND message LIKE '%for account %'
            """
        )
    ).fetchall()
    pattern = re.compile(r"\bfor account (\d+)\b", re.IGNORECASE)
    for alert_id, message in alerts:
        updated_message = pattern.sub(
            lambda match: (
                f"for {account_names[int(match.group(1))]}"
                if int(match.group(1)) in account_names
                else match.group(0)
            ),
            message,
        )
        if updated_message != message:
            connection.execute(
                text(
                    "UPDATE portfolio_alerts SET message = :message WHERE id = :alert_id"
                ),
                {"message": updated_message, "alert_id": alert_id},
            )


def _migrate_account_strategies_decimal(connection: object) -> None:
    """Migrate account targets and move legacy drift bands to portfolio targets."""
    columns = _get_columns(connection, "account_strategies")
    if not columns:
        return

    timestamp = connection.execute(text("SELECT CURRENT_TIMESTAMP")).scalar_one()
    if "created_at" not in columns:
        connection.execute(text("ALTER TABLE account_strategies ADD COLUMN created_at DATETIME"))
        connection.execute(
            text(
                """
                UPDATE account_strategies
                SET created_at = :timestamp
                WHERE created_at IS NULL
                """
            ),
            {"timestamp": timestamp},
        )
        columns["created_at"] = "DATETIME"
    if "updated_at" not in columns:
        connection.execute(text("ALTER TABLE account_strategies ADD COLUMN updated_at DATETIME"))
        connection.execute(
            text(
                """
                UPDATE account_strategies
                SET updated_at = :timestamp
                WHERE updated_at IS NULL
                """
            ),
            {"timestamp": timestamp},
        )
        columns["updated_at"] = "DATETIME"
    column_type = _get_column_type(connection, "account_strategies", "allocation_weight")
    has_legacy_drift = "drift_up_percent" in columns or "drift_down_percent" in columns
    drift_up_expr = "drift_up_percent" if "drift_up_percent" in columns else "5"
    drift_down_expr = "drift_down_percent" if "drift_down_percent" in columns else "5"
    raw_rows = connection.execute(
        text(
            f"""
            SELECT
                account_id,
                strategy_id,
                allocation_weight,
                {drift_up_expr} AS drift_up_percent,
                {drift_down_expr} AS drift_down_percent,
                created_at,
                updated_at
            FROM account_strategies
            """
        )
    ).mappings().all()

    for row in raw_rows:
        _copy_account_target_to_portfolios(connection, row, timestamp)

    if (column_type and "DECIMAL" not in column_type) or has_legacy_drift:
        connection.execute(text("PRAGMA foreign_keys=OFF"))
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS account_strategies_new (
                    account_id INTEGER NOT NULL,
                    strategy_id INTEGER NOT NULL,
                    allocation_weight DECIMAL(32, 10) NOT NULL,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
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
                    INSERT INTO account_strategies_new (
                        account_id,
                        strategy_id,
                        allocation_weight,
                        created_at,
                        updated_at
                    ) VALUES (
                        :account_id,
                        :strategy_id,
                        :allocation_weight,
                        :created_at,
                        :updated_at
                    )
                    """
                ),
                {
                    "account_id": row["account_id"],
                    "strategy_id": row["strategy_id"],
                    "allocation_weight": str(Decimal(str(row["allocation_weight"]))),
                    "created_at": row["created_at"] or timestamp,
                    "updated_at": row["updated_at"] or timestamp,
                },
            )
        connection.execute(text("DROP TABLE account_strategies"))
        connection.execute(text("ALTER TABLE account_strategies_new RENAME TO account_strategies"))
        connection.execute(text("PRAGMA foreign_keys=ON"))


def _copy_account_target_to_portfolios(
    connection: object,
    row: object,
    timestamp: object,
) -> None:
    portfolio_ids = connection.execute(
        text("SELECT id FROM portfolios WHERE account_id = :account_id"),
        {"account_id": row["account_id"]},
    ).fetchall()
    for (portfolio_id,) in portfolio_ids:
        existing = connection.execute(
            text(
                """
                SELECT 1
                FROM portfolio_strategies
                WHERE portfolio_id = :portfolio_id AND strategy_id = :strategy_id
                """
            ),
            {"portfolio_id": portfolio_id, "strategy_id": row["strategy_id"]},
        ).fetchone()
        if existing:
            continue
        connection.execute(
            text(
                """
                INSERT INTO portfolio_strategies (
                    portfolio_id,
                    strategy_id,
                    allocation_weight,
                    drift_up_percent,
                    drift_down_percent,
                    created_at,
                    updated_at
                ) VALUES (
                    :portfolio_id,
                    :strategy_id,
                    :allocation_weight,
                    :drift_up_percent,
                    :drift_down_percent,
                    :created_at,
                    :updated_at
                )
                """
            ),
            {
                "portfolio_id": portfolio_id,
                "strategy_id": row["strategy_id"],
                "allocation_weight": str(Decimal(str(row["allocation_weight"]))),
                "drift_up_percent": str(Decimal(str(row["drift_up_percent"]))),
                "drift_down_percent": str(Decimal(str(row["drift_down_percent"]))),
                "created_at": row["created_at"] or timestamp,
                "updated_at": row["updated_at"] or timestamp,
            },
        )


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
