from __future__ import annotations

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from portfolio_management.db.models import AssetClass, Security
from portfolio_management.db.session import get_session_factory
from portfolio_management.services.reference_data import ensure_currency_code, is_known_asset_class


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
