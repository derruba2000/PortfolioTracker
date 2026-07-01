from __future__ import annotations

import pandas as pd

from portfolio_management.tabs import data_entry


def test_selected_or_first_replaces_stale_dropdown_value() -> None:
    choices = [
        "6 | BPI PT / Alice - NUC 4259582",
        "5 | BPI PT / BPI Portugal",
    ]

    assert data_entry._selected_or_first(  # noqa: SLF001
        "13 | SIMULATION LAB / EUR Test Environment [TEST]",
        choices,
    ) == choices[0]


def test_filter_changed_keeps_account_values_in_refreshed_choices(monkeypatch) -> None:
    live_choices = [
        "6 | BPI PT / Alice - NUC 4259582",
        "5 | BPI PT / BPI Portugal",
    ]

    monkeypatch.setattr(
        data_entry,
        "_account_choices_for_mode",
        lambda account_mode: live_choices,
    )
    monkeypatch.setattr(
        data_entry,
        "_portfolio_choices_for_account_filter",
        lambda account_choice: ["All Portfolios", "1 | Core Portfolio"] if account_choice == live_choices[0] else ["All Portfolios"],
    )
    monkeypatch.setattr(
        data_entry,
        "transactions_table",
        lambda account_mode, **kwargs: pd.DataFrame(),
    )

    _, account_update, portfolio_update, source_update, target_update = (
        data_entry._filter_changed("Live Mode")  # noqa: SLF001
    )

    assert account_update["choices"] == live_choices
    assert account_update["value"] == live_choices[0]
    assert portfolio_update["choices"] == ["All Portfolios", "1 | Core Portfolio"]
    assert portfolio_update["value"] == "All Portfolios"
    assert source_update["value"] == live_choices[0]
    assert target_update["value"] == live_choices[0]


def test_transactions_table_includes_order_id_and_trend_tag(monkeypatch) -> None:
    monkeypatch.setattr(
        data_entry,
        "list_transactions",
        lambda **kwargs: pd.DataFrame(
            [
                {
                    "ID": 10,
                    "Order ID": 7,
                    "Date": "2026-07-01",
                    "Broker": "Broker",
                    "Account": "Live",
                    "Portfolio": "Core",
                    "Portfolio URL": "https://example.com/core",
                    "Ticker": "AAPL",
                    "Type": "BUY",
                    "Description": "Executed from order #7",
                    "Quantity": "1",
                    "Price": "100",
                    "Fees": "1",
                    "Total Value": "101",
                    "FX Rate": "1",
                }
            ]
        ),
    )
    monkeypatch.setattr(
        data_entry,
        "get_ticker_price_and_trend",
        lambda _ticker: ("102.0000", "up"),
    )

    table = data_entry.transactions_table("Live Mode")

    assert isinstance(table, pd.DataFrame)
    assert "Order ID" in table.columns
    assert "Price Trend" in table.columns
    assert "finance.yahoo.com/quote/AAPL" in str(table.iloc[0]["Ticker"])
    assert "102.0000" in str(table.iloc[0]["Price Trend"])
