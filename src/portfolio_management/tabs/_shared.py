from __future__ import annotations

from datetime import date as date_type
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

import pandas as pd

_POPULAR_CURRENCIES = [
    "GBP", "EUR", "USD",
    "JPY", "CHF", "CAD", "AUD", "NZD",
    "HKD", "SGD", "SEK", "NOK", "DKK",
    "CNY", "INR", "BRL", "MXN", "ZAR",
    "TRY", "PLN",
]


def parse_optional_date(raw_value: str) -> date_type | None:
    clean_value = (raw_value or "").strip()
    if not clean_value:
        return None
    return date_type.fromisoformat(clean_value)


def as_date_table(dataframe: object, date_columns: list[str]) -> object:
    if not isinstance(dataframe, pd.DataFrame):
        return dataframe
    formatted = dataframe.copy()
    for column in date_columns:
        if column in formatted.columns:
            parsed = pd.to_datetime(formatted[column], errors="coerce")
            formatted[column] = parsed.dt.date.where(parsed.notna(), None)
    return formatted


def format_two_decimals(value: object) -> str:
    try:
        return f"{Decimal(str(value)):,.2f}"
    except (InvalidOperation, ValueError, TypeError):
        return str(value)


def format_integer_with_commas(value: object) -> str:
    try:
        return f"{int(Decimal(str(value))):,}"
    except (InvalidOperation, ValueError, TypeError):
        return str(value)


def format_decimal_with_commas(value: object) -> str:
    try:
        return f"{Decimal(str(value)):,.2f}"
    except (InvalidOperation, ValueError, TypeError):
        return str(value)


def format_quantity_input(value: str) -> str:
    raw = (value or "").strip().replace(",", "")
    if not raw:
        return ""
    digits = "".join(char for char in raw if char.isdigit())
    if not digits:
        return ""
    return f"{int(digits):,}"


def format_decimal_input(value: str) -> str:
    raw = (value or "").strip().replace(",", "")
    if not raw:
        return ""
    if raw == ".":
        return "0."

    sign = ""
    if raw.startswith("-"):
        sign = "-"
        raw = raw[1:]

    sanitized = "".join(char for char in raw if char.isdigit() or char == ".")
    if not sanitized:
        return sign

    if sanitized.count(".") > 1:
        parts = sanitized.split(".")
        sanitized = f"{parts[0]}.{''.join(parts[1:])}"

    if "." in sanitized:
        whole, fractional = sanitized.split(".", 1)
        whole_display = f"{int(whole):,}" if whole else "0"
        return f"{sign}{whole_display}.{fractional}"

    return f"{sign}{int(sanitized):,}"


def ticker_link(ticker: object) -> str:
    clean_ticker = str(ticker or "").strip()
    if not clean_ticker:
        return ""
    ticker_path = quote(clean_ticker, safe="")
    url = f"https://uk.finance.yahoo.com/quote/{ticker_path}/"
    return f'<a href="{url}" target="_blank" rel="noopener noreferrer">{clean_ticker}</a>'


def mode_banner(account_mode: str) -> str:
    from portfolio_management.services.analytics import SANDBOX_MODE

    if account_mode == SANDBOX_MODE:
        return (
            "<div style='background:#fff3cd;border:1px solid #f1c40f;"
            "padding:12px;border-radius:6px;color:#664d03;'>"
            "<strong>Sandbox Mode</strong> showing simulated accounts only.</div>"
        )
    return (
        "<div style='background:#d1e7dd;border:1px solid #198754;"
        "padding:12px;border-radius:6px;color:#0f5132;'>"
        "<strong>Live Mode</strong> showing real accounts only.</div>"
    )
