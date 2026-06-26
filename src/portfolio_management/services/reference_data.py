from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from portfolio_management.db.models import AssetClassOption, Currency
from portfolio_management.db.session import get_session_factory


DEFAULT_ASSET_CLASSES = [
    ("CASH", "Cash", 0),
    ("EQUITY", "Equity", 1),
    ("BOND", "Bond", 2),
    ("FUND", "Fund", 3),
    ("CRYPTO", "Crypto", 4),
    ("REAL_ESTATE", "Real Estate", 5),
    ("COMMODITY", "Commodity", 6),
    ("OTHER", "Other", 7),
]

DEFAULT_CURRENCIES = [
    ("GBP", "British Pound Sterling", 0),
    ("EUR", "Euro", 1),
    ("USD", "US Dollar", 2),
    ("JPY", "Japanese Yen", 3),
    ("CHF", "Swiss Franc", 4),
    ("CAD", "Canadian Dollar", 5),
    ("AUD", "Australian Dollar", 6),
    ("NZD", "New Zealand Dollar", 7),
    ("HKD", "Hong Kong Dollar", 8),
    ("SGD", "Singapore Dollar", 9),
    ("SEK", "Swedish Krona", 10),
    ("NOK", "Norwegian Krone", 11),
    ("DKK", "Danish Krone", 12),
    ("CNY", "Chinese Yuan", 13),
    ("INR", "Indian Rupee", 14),
    ("BRL", "Brazilian Real", 15),
    ("MXN", "Mexican Peso", 16),
    ("ZAR", "South African Rand", 17),
    ("TRY", "Turkish Lira", 18),
    ("PLN", "Polish Zloty", 19),
]


def seed_reference_data(session: Session) -> None:
    stale_etf = session.get(AssetClassOption, "ETF")
    if stale_etf is not None:
        session.delete(stale_etf)

    for code, name, display_order in DEFAULT_ASSET_CLASSES:
        if session.scalar(select(AssetClassOption).where(AssetClassOption.code == code)) is None:
            session.add(AssetClassOption(code=code, name=name, display_order=display_order))

    for code, name, display_order in DEFAULT_CURRENCIES:
        if session.scalar(select(Currency).where(Currency.code == code)) is None:
            session.add(Currency(code=code, name=name, display_order=display_order))


def list_asset_class_codes() -> list[str]:
    session_factory = get_session_factory()
    with session_factory() as session:
        rows = session.scalars(
            select(AssetClassOption).order_by(AssetClassOption.display_order, AssetClassOption.code)
        ).all()
    return [row.code for row in rows]


def list_currency_codes() -> list[str]:
    session_factory = get_session_factory()
    with session_factory() as session:
        rows = session.scalars(select(Currency).order_by(Currency.display_order, Currency.code)).all()
    return [row.code for row in rows]


def list_asset_class_table() -> pd.DataFrame:
    session_factory = get_session_factory()
    with session_factory() as session:
        rows = session.scalars(
            select(AssetClassOption).order_by(AssetClassOption.display_order, AssetClassOption.code)
        ).all()
    return pd.DataFrame(
        [
            {"Code": row.code, "Name": row.name, "Order": row.display_order}
            for row in rows
        ],
        columns=["Code", "Name", "Order"],
    )


def list_currency_table() -> pd.DataFrame:
    session_factory = get_session_factory()
    with session_factory() as session:
        rows = session.scalars(select(Currency).order_by(Currency.display_order, Currency.code)).all()
    return pd.DataFrame(
        [
            {"Code": row.code, "Name": row.name, "Order": row.display_order}
            for row in rows
        ],
        columns=["Code", "Name", "Order"],
    )


def ensure_currency_code(session: Session, code: str) -> str:
    normalized = (code or "").strip().upper()
    if not normalized:
        raise ValueError("Currency code is required.")
    currency = session.scalar(select(Currency).where(Currency.code == normalized))
    if currency is None:
        max_order = session.scalar(select(Currency.display_order).order_by(Currency.display_order.desc()).limit(1))
        session.add(
            Currency(
                code=normalized,
                name=normalized,
                display_order=(int(max_order) + 1) if max_order is not None else 999,
            )
        )
    return normalized


def is_known_asset_class(code: str) -> bool:
    normalized = (code or "").strip().upper()
    if not normalized:
        return False
    session_factory = get_session_factory()
    with session_factory() as session:
        return session.scalar(select(AssetClassOption).where(AssetClassOption.code == normalized)) is not None
