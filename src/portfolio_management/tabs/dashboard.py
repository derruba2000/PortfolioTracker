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
    format_two_decimals,
    mode_banner,
    ticker_link,
)


def dashboard_summary_table(account_mode: str) -> object:
    summary = dashboard_summary(account_mode=account_mode).copy()
    if "Value" in summary.columns:
        summary["Value"] = summary["Value"].map(format_two_decimals)
    return summary


def dashboard_positions(account_mode: str) -> object:
    positions = current_positions(account_mode=account_mode).copy()
    if "Ticker" in positions.columns:
        positions["Ticker"] = positions["Ticker"].map(ticker_link)
    for column in ["Quantity", "Market Value", "Unrealized P&L"]:
        if column in positions.columns:
            positions[column] = positions[column].map(format_two_decimals)
    return positions


def refresh_dashboard(account_mode: str) -> tuple[Any, ...]:
    """Returns (mode_banner_html, summary, positions, asset_alloc, currency_alloc)."""
    return (
        mode_banner(account_mode),
        dashboard_summary_table(account_mode=account_mode),
        dashboard_positions(account_mode=account_mode),
        allocation_by_asset_class(account_mode=account_mode),
        allocation_by_currency(account_mode=account_mode),
    )


def build_dashboard_tab() -> dict[str, Any]:
    from portfolio_management.services.analytics import SANDBOX_MODE

    with gr.Tab("Dashboard"):
        mode_toggle = gr.Radio(
            label="Mode",
            choices=[LIVE_MODE, SANDBOX_MODE],
            value=LIVE_MODE,
        )
        mode_banner_html = gr.HTML(value=mode_banner(LIVE_MODE))
        summary_table = gr.Dataframe(
            value=lambda: dashboard_summary_table(account_mode=LIVE_MODE),
            headers=["Metric", "Value"],
            datatype=["str", "str"],
            label="Summary",
            interactive=False,
        )
        positions_table = gr.Dataframe(
            value=lambda: dashboard_positions(account_mode=LIVE_MODE),
            headers=[
                "Broker", "Account", "Portfolio", "Ticker", "Name",
                "Asset Class", "Currency", "Quantity", "Average Cost",
                "Latest Price", "Market Value", "Unrealized P&L",
            ],
            datatype=[
                "str", "str", "str", "markdown", "str",
                "str", "str", "str", "str",
                "str", "str", "str",
            ],
            label="Current Positions",
            interactive=False,
        )
        with gr.Row():
            asset_allocation_plot = gr.BarPlot(
                value=lambda: allocation_by_asset_class(account_mode=LIVE_MODE),
                x="Asset Class",
                y="Market Value",
                title="Allocation by Asset Class",
                y_title="Market Value",
            )
            currency_allocation_plot = gr.BarPlot(
                value=lambda: allocation_by_currency(account_mode=LIVE_MODE),
                x="Currency",
                y="Market Value",
                title="Allocation by Currency",
                y_title="Market Value",
            )
        refresh_dashboard_button = gr.Button("Refresh Dashboard")

    return {
        "mode_toggle": mode_toggle,
        "mode_banner_html": mode_banner_html,
        "summary_table": summary_table,
        "positions_table": positions_table,
        "asset_allocation_plot": asset_allocation_plot,
        "currency_allocation_plot": currency_allocation_plot,
        "refresh_dashboard_button": refresh_dashboard_button,
    }
