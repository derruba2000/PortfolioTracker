from __future__ import annotations

import pandas as pd
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session

from portfolio_management.db.models import AssetClass, Security
from portfolio_management.db.session import get_engine, get_session_factory
from portfolio_management.services.reference_data import ensure_currency_code, is_known_asset_class


YAHOO_DETAIL_TABLES = {
    "snapshot": "yahoo_security_snapshots",
    "security_info": "yahoo_security_info",
    "analyst_targets": "yahoo_analyst_targets",
    "calendar_events": "yahoo_calendar_events",
    "financial_facts": "yahoo_financial_facts",
    "fund_profile": "yahoo_fund_profiles",
    "fund_holdings": "yahoo_fund_holdings",
    "fund_metrics": "yahoo_fund_metrics",
    "fund_performance": "yahoo_fund_performance",
    "fund_asset_allocation": "yahoo_fund_asset_allocation",
    "fund_sector_weightings": "yahoo_fund_sector_weightings",
    "option_contracts": "yahoo_option_contracts",
}


def create_security(
    ticker: str,
    description: str,
    asset_class: str,
    currency_code: str,
) -> str:
    clean_ticker = (ticker or "").strip().upper()
    if not clean_ticker:
        raise ValueError("Ticker is required.")

    clean_description = (description or "").strip() or None
    clean_asset_class = (asset_class or "").strip().upper()
    if not is_known_asset_class(clean_asset_class):
        raise ValueError("Asset class must be selected from the database list.")
    asset_class_value = AssetClass(clean_asset_class)

    session_factory = get_session_factory()
    with session_factory() as session:
        normalized_currency = ensure_currency_code(session, currency_code)
        security = session.scalar(select(Security).where(Security.ticker == clean_ticker))
        if security is None:
            security = Security(
                ticker=clean_ticker,
                name=clean_description or clean_ticker,
                description=clean_description,
                asset_class=asset_class_value,
                currency_code=normalized_currency,
            )
            session.add(security)
        else:
            security.name = clean_description or security.name
            security.description = clean_description
            security.asset_class = asset_class_value
            security.currency_code = normalized_currency
        session.commit()

    return f"Saved security '{clean_ticker}'."


def list_securities() -> pd.DataFrame:
    session_factory = get_session_factory()
    with session_factory() as session:
        rows = session.scalars(select(Security).order_by(Security.ticker)).all()

    return pd.DataFrame(
        [
            {
                "Ticker": security.ticker,
                "Description": security.description or security.name,
                "Asset Class": security.asset_class.value,
                "Currency": security.currency_code,
            }
            for security in rows
        ],
        columns=["Ticker", "Description", "Asset Class", "Currency"],
    )


def list_security_tickers() -> list[str]:
    session_factory = get_session_factory()
    with session_factory() as session:
        tickers = session.scalars(select(Security.ticker).order_by(Security.ticker)).all()
    return list(tickers)


def security_detail_symbols() -> list[str]:
    symbols = set(list_security_tickers())
    engine = get_engine()
    existing_tables = set(inspect(engine).get_table_names())
    with engine.connect() as connection:
        for table in YAHOO_DETAIL_TABLES.values():
            if table not in existing_tables:
                continue
            rows = connection.execute(
                text(f'SELECT DISTINCT symbol FROM "{table}" ORDER BY symbol')
            ).scalars()
            symbols.update(str(symbol).strip() for symbol in rows if str(symbol).strip())
    return sorted(symbols)


def yahoo_security_details(symbol: str | None) -> dict[str, pd.DataFrame]:
    clean_symbol = (symbol or "").strip().upper()
    details = {
        key: _empty_yahoo_table(table)
        for key, table in YAHOO_DETAIL_TABLES.items()
    }
    if not clean_symbol:
        return details

    engine = get_engine()
    existing_tables = set(inspect(engine).get_table_names())
    with engine.connect() as connection:
        for key, table in YAHOO_DETAIL_TABLES.items():
            if table not in existing_tables:
                continue
            details[key] = pd.read_sql_query(
                text(f'SELECT * FROM "{table}" WHERE symbol = :symbol'),
                connection,
                params={"symbol": clean_symbol},
            )

    details["snapshot"] = _vertical_record(
        details["snapshot"],
        excluded_columns={"symbol", "raw_info_json"},
    )
    details["fund_profile"] = _vertical_record(
        details["fund_profile"],
        excluded_columns={"symbol"},
    )
    for key, dataframe in details.items():
        if key not in {"snapshot", "fund_profile"}:
            details[key] = _display_dataframe(dataframe)
    return details


def _empty_yahoo_table(table: str) -> pd.DataFrame:
    engine = get_engine()
    inspector = inspect(engine)
    if table not in inspector.get_table_names():
        return pd.DataFrame()
    columns = [column["name"] for column in inspector.get_columns(table)]
    return pd.DataFrame(columns=columns)


def _vertical_record(
    dataframe: pd.DataFrame,
    excluded_columns: set[str],
) -> pd.DataFrame:
    if dataframe.empty:
        return pd.DataFrame(columns=["Attribute", "Value"])
    row = dataframe.iloc[0]
    return pd.DataFrame(
        [
            {
                "Attribute": _display_column_name(column),
                "Value": _display_value(row[column]),
            }
            for column in dataframe.columns
            if column not in excluded_columns
        ],
        columns=["Attribute", "Value"],
    )


def _display_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame:
    displayed = dataframe.drop(columns=["symbol"], errors="ignore").copy()
    displayed.columns = [_display_column_name(column) for column in displayed.columns]
    return displayed.map(_display_value)


def _display_column_name(column: str) -> str:
    return str(column).replace("_", " ").title()


def _display_value(value: object) -> object:
    if pd.isna(value):
        return ""
    if isinstance(value, float):
        return f"{value:,.6g}"
    return value


def get_security_defaults(
    ticker: str,
    current_description: str,
    current_asset_class: str,
    current_currency: str,
) -> tuple[str, str, str]:
    clean_ticker = (ticker or "").strip().upper()
    if not clean_ticker:
        return current_description, current_asset_class, current_currency

    session_factory = get_session_factory()
    with session_factory() as session:
        security = session.scalar(select(Security).where(Security.ticker == clean_ticker))

    if security is None:
        return current_description, current_asset_class, current_currency

    return (
        security.description or security.name,
        security.asset_class.value,
        security.currency_code,
    )
