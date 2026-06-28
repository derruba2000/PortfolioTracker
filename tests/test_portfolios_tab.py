from __future__ import annotations

import pandas as pd

from portfolio_management.tabs.portfolios import (
    ALL_MASTER_PORTFOLIOS,
    portfolio_assets_table_data,
    portfolio_view_choices,
    portfolios_table_data,
)


def _portfolios() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ID": 1,
                "Broker": "Broker",
                "Account": "ISA",
                "Portfolio": "Core",
                "Portfolio URL": "",
                "Description": "Long-term allocation",
                "Currency": "GBP",
                "Simulated Account": "No",
                "Active": "Yes",
            },
            {
                "ID": 2,
                "Broker": "Broker",
                "Account": "ISA",
                "Portfolio": "Income",
                "Portfolio URL": "",
                "Description": "Income allocation",
                "Currency": "GBP",
                "Simulated Account": "No",
                "Active": "Yes",
            },
        ]
    )


def test_portfolio_filter_is_shared_by_portfolio_table(monkeypatch) -> None:
    monkeypatch.setattr(
        "portfolio_management.tabs.portfolios.list_portfolios",
        lambda _filter, **_kwargs: _portfolios(),
    )

    choices = portfolio_view_choices("All", active_only=False)
    table = portfolios_table_data("All", choices[1], active_only=False)

    assert choices == [
        ALL_MASTER_PORTFOLIOS,
        "1 | Broker / ISA / Core",
        "2 | Broker / ISA / Income",
    ]
    assert table["Portfolio"].tolist() == ["Core"]


def test_portfolio_assets_table_uses_selected_portfolio(monkeypatch) -> None:
    positions = pd.DataFrame(
        [
            {
                "Ticker": "AAA",
                "Name": "Alpha",
                "Asset Class": "BOND",
                "Quantity": "10",
                "Latest Price": "12.5",
                "Market Value": "125",
                "Currency": "GBP",
            }
        ]
    )
    captured: dict[str, int] = {}

    def current_positions(**kwargs):
        captured["portfolio_id"] = kwargs["portfolio_id"]
        return positions

    monkeypatch.setattr(
        "portfolio_management.tabs.portfolios.current_positions",
        current_positions,
    )
    monkeypatch.setattr(
        "portfolio_management.tabs.portfolios.portfolio_details",
        lambda _: ("Core", "Long-term allocation", "", True),
    )

    table = portfolio_assets_table_data("1 | Broker / ISA / Core")

    assert captured["portfolio_id"] == 1
    assert table.loc[0, "Volume"] == "10"
    assert table.loc[0, "Price"] == "12.50"
    assert table.loc[0, "Value"] == "125.00"
    assert table.loc[0, "Portfolio Description"] == "Long-term allocation"
