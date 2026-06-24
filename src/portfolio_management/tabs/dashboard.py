from __future__ import annotations

from typing import Any

import gradio as gr

from portfolio_management.services.analytics import (
    LIVE_MODE,
    allocation_by_asset_class,
    allocation_by_currency,
    current_positions,
    dashboard_summary,
)
from portfolio_management.tabs._shared import (
    format_integer_with_commas,
    format_two_decimals,
    mode_banner,
    portfolio_link,
    ticker_link,
)


REPORTING_CURRENCIES = ["GBP", "EUR", "USD"]


def dashboard_summary_table(account_mode: str, reporting_currency: str) -> object:
    summary = dashboard_summary(
        account_mode=account_mode,
        reporting_currency=reporting_currency,
    ).copy()
    if "Value" in summary.columns:
        summary["Value"] = summary["Value"].map(format_two_decimals)
    return summary


def dashboard_positions(account_mode: str, reporting_currency: str) -> object:
    positions = current_positions(
        account_mode=account_mode,
        reporting_currency=reporting_currency,
    ).copy()
    if "Portfolio" in positions.columns and "Portfolio URL" in positions.columns:
        positions["Portfolio"] = positions.apply(
            lambda row: portfolio_link(row["Portfolio"], row["Portfolio URL"]),
            axis=1,
        )
        positions = positions.drop(columns=["Portfolio URL"])
    if "Ticker" in positions.columns:
        positions["Ticker"] = positions["Ticker"].map(ticker_link)
    if "Quantity" in positions.columns:
        positions["Quantity"] = positions["Quantity"].map(format_integer_with_commas)
    for column in ["Average Cost", "Latest Price", "Market Value", "Unrealized P&L"]:
        if column in positions.columns:
            positions[column] = positions[column].map(format_two_decimals)
    return positions


def refresh_dashboard(account_mode: str, reporting_currency: str) -> tuple[Any, ...]:
    """Returns (mode_banner_html, summary, positions, asset_alloc, currency_alloc)."""
    return (
        mode_banner(account_mode),
        dashboard_summary_table(account_mode, reporting_currency),
        dashboard_positions(account_mode, reporting_currency),
        allocation_by_asset_class(
            account_mode=account_mode,
            reporting_currency=reporting_currency,
        ),
        allocation_by_currency(
            account_mode=account_mode,
            reporting_currency=reporting_currency,
        ),
    )


def build_dashboard_tab() -> dict[str, Any]:
    from portfolio_management.services.analytics import SANDBOX_MODE

    with gr.Tab("Dashboard"):
        mode_toggle = gr.Radio(
            label="Mode",
            choices=[LIVE_MODE, SANDBOX_MODE],
            value=LIVE_MODE,
        )
        reporting_currency = gr.Dropdown(
            label="Reporting Currency",
            choices=REPORTING_CURRENCIES,
            value="GBP",
            allow_custom_value=False,
        )
        mode_banner_html = gr.HTML(value=mode_banner(LIVE_MODE))
        summary_table = gr.Dataframe(
            value=lambda: dashboard_summary_table(LIVE_MODE, "GBP"),
            headers=["Metric", "Value"],
            datatype=["str", "str"],
            label="Summary",
            interactive=False,
        )
        positions_table = gr.Dataframe(
            value=lambda: dashboard_positions(LIVE_MODE, "GBP"),
            headers=[
                "Broker", "Account", "Portfolio", "Ticker", "Name",
                "Asset Class", "Currency", "Reporting Currency", "Quantity", "Average Cost",
                "Latest Price", "Market Value", "Unrealized P&L",
            ],
            datatype=[
                "str", "str", "markdown", "markdown", "str",
                "str", "str", "str", "str", "str",
                "str", "str", "str",
            ],
            label="Current Positions",
            interactive=False,
        )
        with gr.Row():
            asset_allocation_plot = gr.BarPlot(
                value=lambda: allocation_by_asset_class(
                    account_mode=LIVE_MODE,
                    reporting_currency="GBP",
                ),
                x="Asset Class",
                y="Market Value",
                title="Allocation by Asset Class (Reporting Currency)",
                y_title="Market Value in Selected Currency",
            )
            currency_allocation_plot = gr.BarPlot(
                value=lambda: allocation_by_currency(
                    account_mode=LIVE_MODE,
                    reporting_currency="GBP",
                ),
                x="Currency",
                y="Market Value",
                title="Allocation by Source Currency (Reporting Currency)",
                y_title="Market Value in Selected Currency",
            )
        refresh_dashboard_button = gr.Button("Refresh Dashboard")

    return {
        "mode_toggle": mode_toggle,
        "reporting_currency": reporting_currency,
        "mode_banner_html": mode_banner_html,
        "summary_table": summary_table,
        "positions_table": positions_table,
        "asset_allocation_plot": asset_allocation_plot,
        "currency_allocation_plot": currency_allocation_plot,
        "refresh_dashboard_button": refresh_dashboard_button,
    }
