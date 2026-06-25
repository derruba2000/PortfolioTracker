from __future__ import annotations

from sqlalchemy import create_engine, text

from portfolio_management.services.securities import (
    security_detail_symbols,
    yahoo_security_details,
)


def _engine():
    engine = create_engine("sqlite:///:memory:", future=True)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE yahoo_security_snapshots (
                    symbol TEXT PRIMARY KEY,
                    quote_type TEXT,
                    long_name TEXT,
                    raw_info_json TEXT,
                    extracted_at TEXT NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE yahoo_security_info (
                    symbol TEXT NOT NULL,
                    attribute TEXT NOT NULL,
                    value_text TEXT,
                    value_number REAL,
                    value_boolean INTEGER,
                    value_date TEXT,
                    extracted_at TEXT NOT NULL,
                    PRIMARY KEY (symbol, attribute)
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO yahoo_security_snapshots
                    (symbol, quote_type, long_name, raw_info_json, extracted_at)
                VALUES
                    ('AAA', 'ETF', 'Alpha Fund', '{}', '2026-06-25')
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO yahoo_security_info
                    (symbol, attribute, value_number, extracted_at)
                VALUES
                    ('AAA', 'regularMarketPrice', 12.5, '2026-06-25')
                """
            )
        )
    return engine


def test_yahoo_security_details_are_grouped_for_display(monkeypatch) -> None:
    engine = _engine()
    monkeypatch.setattr(
        "portfolio_management.services.securities.get_engine",
        lambda: engine,
    )
    monkeypatch.setattr(
        "portfolio_management.services.securities.list_security_tickers",
        lambda: ["LOCAL"],
    )

    details = yahoo_security_details("AAA")

    assert details["snapshot"].to_dict("records") == [
        {"Attribute": "Quote Type", "Value": "ETF"},
        {"Attribute": "Long Name", "Value": "Alpha Fund"},
        {"Attribute": "Extracted At", "Value": "2026-06-25"},
    ]
    assert details["security_info"].loc[0, "Attribute"] == "regularMarketPrice"
    assert security_detail_symbols() == ["AAA", "LOCAL"]
