from __future__ import annotations

import pandas as pd

from portfolio_management.tabs.dashboard import (
    ALL_ASSET_CLASSES,
    ALL_POSITION_ACCOUNTS,
    ALL_POSITION_PORTFOLIOS,
    dashboard_position_filter_choices,
    dashboard_positions,
    dashboard_positions_and_charts,
)


def _positions() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Broker": "Broker A",
                "Account": "ISA",
                "Portfolio": "Core",
                "Portfolio URL": "",
                "Ticker": "AAA",
                "Name": "Alpha",
                "Asset Class": "EQUITY",
                "Currency": "GBP",
                "Reporting Currency": "GBP",
                "Quantity": "10",
                "Average Cost": "10",
                "Latest Price": "12",
                "Market Value": "120",
                "Unrealized P&L": "20",
            },
            {
                "Broker": "Broker B",
                "Account": "Trading",
                "Portfolio": "Income",
                "Portfolio URL": "",
                "Ticker": "BBB",
                "Name": "Beta",
                "Asset Class": "BOND",
                "Currency": "USD",
                "Reporting Currency": "GBP",
                "Quantity": "5",
                "Average Cost": "20",
                "Latest Price": "22",
                "Market Value": "110",
                "Unrealized P&L": "10",
            },
        ]
    )


def test_dashboard_position_filters_are_cumulative(monkeypatch) -> None:
    monkeypatch.setattr(
        "portfolio_management.tabs.dashboard.current_positions",
        lambda **_: _positions(),
    )

    filtered = dashboard_positions(
        "Live Mode",
        "GBP",
        account_filter="ISA",
        position_portfolio_filter="Core",
        asset_class_filter="EQUITY",
    )

    assert filtered["Account"].tolist() == ["ISA"]
    assert filtered["Portfolio"].tolist() == ["Core"]
    assert filtered["Asset Class"].tolist() == ["EQUITY"]


def test_dashboard_position_filter_choices_include_all_options(monkeypatch) -> None:
    monkeypatch.setattr(
        "portfolio_management.tabs.dashboard.current_positions",
        lambda **_: _positions(),
    )

    account_choices, portfolio_choices, asset_class_choices = (
        dashboard_position_filter_choices("Live Mode", "GBP")
    )

    assert account_choices == [ALL_POSITION_ACCOUNTS, "ISA", "Trading"]
    assert portfolio_choices == [ALL_POSITION_PORTFOLIOS, "Core", "Income"]
    assert asset_class_choices == [ALL_ASSET_CLASSES, "BOND", "EQUITY"]


def test_dashboard_position_filter_choices_cascade(monkeypatch) -> None:
    positions = _positions()
    positions.loc[2] = {
        **positions.loc[0].to_dict(),
        "Portfolio": "Growth",
        "Ticker": "CCC",
        "Asset Class": "BOND",
    }
    monkeypatch.setattr(
        "portfolio_management.tabs.dashboard.current_positions",
        lambda **_: positions,
    )

    _, portfolio_choices, account_asset_classes = dashboard_position_filter_choices(
        "Live Mode",
        "GBP",
        account_filter="ISA",
    )
    _, _, portfolio_asset_classes = dashboard_position_filter_choices(
        "Live Mode",
        "GBP",
        account_filter="ISA",
        position_portfolio_filter="Core",
    )

    assert portfolio_choices == [ALL_POSITION_PORTFOLIOS, "Core", "Growth"]
    assert account_asset_classes == [ALL_ASSET_CLASSES, "BOND", "EQUITY"]
    assert portfolio_asset_classes == [ALL_ASSET_CLASSES, "EQUITY"]


def test_dashboard_position_filters_ignore_surrounding_whitespace(monkeypatch) -> None:
    positions = _positions()
    positions.loc[0, "Account"] = "ISA\n"
    positions.loc[0, "Portfolio"] = " Core "
    positions.loc[0, "Asset Class"] = "EQUITY "
    monkeypatch.setattr(
        "portfolio_management.tabs.dashboard.current_positions",
        lambda **_: positions,
    )

    filtered = dashboard_positions(
        "Live Mode",
        "GBP",
        account_filter="ISA",
        position_portfolio_filter="Core",
        asset_class_filter="EQUITY",
    )

    assert len(filtered) == 1
    assert filtered.iloc[0]["Ticker"].endswith(">AAA</a>")


def test_dashboard_chart_allocations_follow_active_filters(monkeypatch) -> None:
    monkeypatch.setattr(
        "portfolio_management.tabs.dashboard.current_positions",
        lambda **_: _positions(),
    )

    _, asset_allocation, currency_allocation = dashboard_positions_and_charts(
        "Live Mode",
        "GBP",
        account_filter="ISA",
        position_portfolio_filter="Core",
        asset_class_filter="EQUITY",
    )

    assert asset_allocation.to_dict("records") == [
        {"Asset Class": "EQUITY", "Market Value": 120.0}
    ]
    assert currency_allocation.to_dict("records") == [
        {"Currency": "GBP", "Market Value": 120.0}
    ]
