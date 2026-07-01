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
        "portfolio_choices_for_account",
        lambda account_choice: ["1 | Core Portfolio"] if account_choice == live_choices[0] else [],
    )
    monkeypatch.setattr(
        data_entry,
        "transactions_table",
        lambda account_mode: pd.DataFrame(),
    )

    _, account_update, portfolio_update, source_update, target_update = (
        data_entry._filter_changed("Live Mode")  # noqa: SLF001
    )

    assert account_update["choices"] == live_choices
    assert account_update["value"] == live_choices[0]
    assert portfolio_update["value"] == "1 | Core Portfolio"
    assert source_update["value"] == live_choices[0]
    assert target_update["value"] == live_choices[0]
