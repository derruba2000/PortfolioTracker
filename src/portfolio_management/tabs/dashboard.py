from __future__ import annotations

from typing import Any

import gradio as gr

from portfolio_management.services.analytics import (
    allocation_by_asset_class,
    allocation_by_currency,
    current_positions,
    dashboard_summary,
)
from portfolio_management.services.analysis_filters import (
    ACCOUNT_SCOPE_CHOICES,
    ALL_PORTFOLIOS,
    parse_portfolio_filter,
    portfolio_filter_choices,
)
from portfolio_management.services.analytics import LIVE_MODE
from portfolio_management.tabs._shared import (
    format_integer_with_commas,
    format_two_decimals,
    mode_banner,
    portfolio_link,
    ticker_link,
)


REPORTING_CURRENCIES = ["GBP", "EUR", "USD"]
ALL_POSITION_ACCOUNTS = "All Accounts"
ALL_POSITION_PORTFOLIOS = "All Portfolios"
ALL_ASSET_CLASSES = "All Asset Classes"


def dashboard_summary_table(
    account_mode: str,
    reporting_currency: str,
    portfolio_choice: str | int | None = None,
) -> object:
    summary = dashboard_summary(
        account_mode=account_mode,
        reporting_currency=reporting_currency,
        portfolio_id=parse_portfolio_filter(portfolio_choice),
    ).copy()
    if "Value" in summary.columns:
        summary["Value"] = summary["Value"].map(format_two_decimals)
    return summary


def dashboard_positions(
    account_mode: str,
    reporting_currency: str,
    portfolio_choice: str | int | None = None,
    account_filter: str | None = None,
    position_portfolio_filter: str | None = None,
    asset_class_filter: str | None = None,
) -> object:
    positions = current_positions(
        account_mode=account_mode,
        reporting_currency=reporting_currency,
        portfolio_id=parse_portfolio_filter(portfolio_choice),
    ).copy()
    positions = _filter_dashboard_positions(
        positions,
        account_filter=account_filter,
        portfolio_filter=position_portfolio_filter,
        asset_class_filter=asset_class_filter,
    )
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


def dashboard_position_filter_choices(
    account_mode: str,
    reporting_currency: str,
    portfolio_choice: str | int | None = None,
    account_filter: str | None = None,
    position_portfolio_filter: str | None = None,
) -> tuple[list[str], list[str], list[str]]:
    positions = current_positions(
        account_mode=account_mode,
        reporting_currency=reporting_currency,
        portfolio_id=parse_portfolio_filter(portfolio_choice),
    )
    portfolio_positions = _filter_dashboard_positions(
        positions,
        account_filter=account_filter,
        portfolio_filter=None,
        asset_class_filter=None,
    )
    asset_class_positions = _filter_dashboard_positions(
        portfolio_positions,
        account_filter=None,
        portfolio_filter=position_portfolio_filter,
        asset_class_filter=None,
    )
    return (
        [ALL_POSITION_ACCOUNTS, *_column_choices(positions, "Account")],
        [
            ALL_POSITION_PORTFOLIOS,
            *_column_choices(portfolio_positions, "Portfolio"),
        ],
        [
            ALL_ASSET_CLASSES,
            *_column_choices(asset_class_positions, "Asset Class"),
        ],
    )


def _column_choices(positions: object, column: str) -> list[str]:
    if not hasattr(positions, "columns") or column not in positions.columns:
        return []
    return sorted(
        {
            str(value).strip()
            for value in positions[column].dropna()
            if str(value).strip()
        }
    )


def _filter_dashboard_positions(
    positions: object,
    account_filter: str | None,
    portfolio_filter: str | None,
    asset_class_filter: str | None,
) -> object:
    filters = (
        ("Account", account_filter, ALL_POSITION_ACCOUNTS),
        ("Portfolio", portfolio_filter, ALL_POSITION_PORTFOLIOS),
        ("Asset Class", asset_class_filter, ALL_ASSET_CLASSES),
    )
    for column, selected_value, all_value in filters:
        if selected_value not in (None, "", all_value) and column in positions.columns:
            normalized_selection = str(selected_value).strip()
            normalized_values = positions[column].astype(str).str.strip()
            positions = positions[normalized_values == normalized_selection]
    return positions.copy()


def refresh_dashboard(
    account_mode: str,
    reporting_currency: str,
    portfolio_choice: str | int | None = None,
    account_filter: str | None = None,
    position_portfolio_filter: str | None = None,
    asset_class_filter: str | None = None,
) -> tuple[Any, ...]:
    """Returns (mode_banner_html, summary, positions, asset_alloc, currency_alloc)."""
    return (
        mode_banner(account_mode),
        dashboard_summary_table(account_mode, reporting_currency, portfolio_choice),
        dashboard_positions(
            account_mode,
            reporting_currency,
            portfolio_choice,
            account_filter,
            position_portfolio_filter,
            asset_class_filter,
        ),
        allocation_by_asset_class(
            account_mode=account_mode,
            reporting_currency=reporting_currency,
            portfolio_id=parse_portfolio_filter(portfolio_choice),
        ),
        allocation_by_currency(
            account_mode=account_mode,
            reporting_currency=reporting_currency,
            portfolio_id=parse_portfolio_filter(portfolio_choice),
        ),
    )


def dashboard_scope_changed(
    account_mode: str,
    reporting_currency: str,
) -> tuple[Any, ...]:
    choices = portfolio_filter_choices(account_mode)
    account_choices, position_portfolio_choices, asset_class_choices = (
        dashboard_position_filter_choices(
            account_mode,
            reporting_currency,
            ALL_PORTFOLIOS,
        )
    )
    return (
        gr.update(choices=choices, value=ALL_PORTFOLIOS),
        gr.update(choices=account_choices, value=ALL_POSITION_ACCOUNTS),
        gr.update(
            choices=position_portfolio_choices,
            value=ALL_POSITION_PORTFOLIOS,
        ),
        gr.update(choices=asset_class_choices, value=ALL_ASSET_CLASSES),
        *refresh_dashboard(account_mode, reporting_currency, ALL_PORTFOLIOS),
    )


def dashboard_portfolio_scope_changed(
    account_mode: str,
    reporting_currency: str,
    portfolio_choice: str | int | None,
) -> tuple[Any, ...]:
    account_choices, position_portfolio_choices, asset_class_choices = (
        dashboard_position_filter_choices(
            account_mode,
            reporting_currency,
            portfolio_choice,
        )
    )
    return (
        gr.update(choices=account_choices, value=ALL_POSITION_ACCOUNTS),
        gr.update(
            choices=position_portfolio_choices,
            value=ALL_POSITION_PORTFOLIOS,
        ),
        gr.update(choices=asset_class_choices, value=ALL_ASSET_CLASSES),
        *refresh_dashboard(account_mode, reporting_currency, portfolio_choice),
    )


def dashboard_position_account_changed(
    account_mode: str,
    reporting_currency: str,
    portfolio_choice: str | int | None,
    account_filter: str | None,
) -> tuple[Any, ...]:
    _, portfolio_choices, asset_class_choices = dashboard_position_filter_choices(
        account_mode,
        reporting_currency,
        portfolio_choice,
        account_filter=account_filter,
    )
    return (
        gr.update(choices=portfolio_choices, value=ALL_POSITION_PORTFOLIOS),
        gr.update(choices=asset_class_choices, value=ALL_ASSET_CLASSES),
        dashboard_positions(
            account_mode,
            reporting_currency,
            portfolio_choice,
            account_filter,
            ALL_POSITION_PORTFOLIOS,
            ALL_ASSET_CLASSES,
        ),
    )


def dashboard_position_portfolio_changed(
    account_mode: str,
    reporting_currency: str,
    portfolio_choice: str | int | None,
    account_filter: str | None,
    position_portfolio_filter: str | None,
) -> tuple[Any, ...]:
    _, _, asset_class_choices = dashboard_position_filter_choices(
        account_mode,
        reporting_currency,
        portfolio_choice,
        account_filter=account_filter,
        position_portfolio_filter=position_portfolio_filter,
    )
    return (
        gr.update(choices=asset_class_choices, value=ALL_ASSET_CLASSES),
        dashboard_positions(
            account_mode,
            reporting_currency,
            portfolio_choice,
            account_filter,
            position_portfolio_filter,
            ALL_ASSET_CLASSES,
        ),
    )


def build_dashboard_tab() -> dict[str, Any]:
    account_choices, position_portfolio_choices, asset_class_choices = (
        dashboard_position_filter_choices(LIVE_MODE, "GBP")
    )
    with gr.Tab("Dashboard"):
        with gr.Row():
            mode_toggle = gr.Radio(
                label="Account Scope",
                choices=ACCOUNT_SCOPE_CHOICES,
                value=LIVE_MODE,
            )
            portfolio_filter = gr.Dropdown(
                label="Dashboard Portfolio Scope",
                choices=portfolio_filter_choices(LIVE_MODE),
                value=ALL_PORTFOLIOS,
                allow_custom_value=False,
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
        with gr.Row():
            positions_account_filter = gr.Dropdown(
                label="Account",
                choices=account_choices,
                value=ALL_POSITION_ACCOUNTS,
                allow_custom_value=False,
                filterable=True,
            )
            positions_portfolio_filter = gr.Dropdown(
                label="Portfolio",
                choices=position_portfolio_choices,
                value=ALL_POSITION_PORTFOLIOS,
                allow_custom_value=False,
                filterable=True,
            )
            positions_asset_class_filter = gr.Dropdown(
                label="Asset Class",
                choices=asset_class_choices,
                value=ALL_ASSET_CLASSES,
                allow_custom_value=False,
                filterable=True,
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
        "portfolio_filter": portfolio_filter,
        "positions_account_filter": positions_account_filter,
        "positions_portfolio_filter": positions_portfolio_filter,
        "positions_asset_class_filter": positions_asset_class_filter,
        "mode_banner_html": mode_banner_html,
        "summary_table": summary_table,
        "positions_table": positions_table,
        "asset_allocation_plot": asset_allocation_plot,
        "currency_allocation_plot": currency_allocation_plot,
        "refresh_dashboard_button": refresh_dashboard_button,
    }
