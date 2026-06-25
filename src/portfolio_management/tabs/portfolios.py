from __future__ import annotations

from typing import Any

import gradio as gr
import pandas as pd

from portfolio_management.services.accounts import (
    account_choices,
    create_portfolio,
    list_portfolios,
    parse_choice_id,
    portfolio_choices_for_account,
    portfolio_details,
    update_portfolio,
)
from portfolio_management.services.analytics import ALL_ACCOUNTS_MODE, current_positions
from portfolio_management.tabs._shared import (
    format_integer_with_commas,
    format_two_decimals,
    portfolio_link,
    ticker_link,
)


ALL_MASTER_PORTFOLIOS = "All Portfolios"


def create_portfolio_callback(
    account_choice: str,
    portfolio_name: str,
    description: str,
    portfolio_url: str,
    portfolios_filter: str = "All",
    portfolio_view_choice: str | int | None = None,
) -> tuple[Any, ...]:
    try:
        status = create_portfolio(
            account_choice=account_choice,
            portfolio_name=portfolio_name,
            description=description,
            portfolio_url=portfolio_url,
        )
    except Exception as exc:
        choices = portfolio_view_choices(portfolios_filter)
        return (
            f"Could not create portfolio: {exc}",
            gr.update(),
            gr.update(),
            gr.update(),
            gr.update(choices=choices, value=portfolio_view_choice),
            portfolios_table_data(portfolios_filter, portfolio_view_choice),
            portfolio_assets_table_data(portfolio_view_choice),
        )

    accounts = account_choices(include_simulated=True)
    portfolios = portfolio_choices_for_account(account_choice)
    selected_portfolio = next(
        (choice for choice in portfolios if f"| {portfolio_name}" in choice),
        portfolios[0] if portfolios else None,
    )
    choices = portfolio_view_choices(portfolios_filter)
    selected_view = _portfolio_view_choice_for_id(
        choices,
        parse_choice_id(selected_portfolio),
    )
    return (
        status,
        gr.update(choices=accounts, value=account_choice),
        gr.update(choices=accounts, value=account_choice),
        gr.update(choices=portfolios, value=selected_portfolio),
        gr.update(choices=choices, value=selected_view),
        portfolios_table_data(portfolios_filter, selected_view),
        portfolio_assets_table_data(selected_view),
    )


def _load_portfolio_details(portfolio_choice: str) -> tuple[str, str, str, bool]:
    return portfolio_details(portfolio_choice)


def _update_portfolio_callback(
    portfolio_choice: str,
    portfolio_name: str,
    description: str,
    portfolio_url: str,
    is_active: bool,
    portfolios_filter: str = "All",
    portfolio_view_choice: str | int | None = None,
) -> tuple[Any, ...]:
    try:
        status = update_portfolio(
            portfolio_choice=portfolio_choice,
            portfolio_name=portfolio_name,
            description=description,
            portfolio_url=portfolio_url,
            is_active=is_active,
        )
    except Exception as exc:
        status = f"Could not update portfolio: {exc}"

    choices = portfolio_view_choices(portfolios_filter)
    selected_view = _portfolio_view_choice_for_id(
        choices,
        _parse_portfolio_view_id(portfolio_view_choice),
    )
    return (
        status,
        gr.update(),
        gr.update(choices=choices, value=selected_view),
        portfolios_table_data(portfolios_filter, selected_view),
        portfolio_assets_table_data(selected_view),
    )


def portfolio_view_choices(portfolios_filter: str = "All") -> list[str]:
    portfolios = list_portfolios(portfolios_filter)
    choices = [ALL_MASTER_PORTFOLIOS]
    if not isinstance(portfolios, pd.DataFrame):
        return choices
    for _, row in portfolios.iterrows():
        choices.append(
            f"{row['ID']} | {row['Broker']} / {row['Account']} / {row['Portfolio']}"
        )
    return choices


def portfolios_table_data(
    portfolios_filter: str = "All",
    portfolio_view_choice: str | int | None = None,
) -> object:
    portfolios = list_portfolios(portfolios_filter)
    portfolio_id = _parse_portfolio_view_id(portfolio_view_choice)
    if (
        portfolio_id is not None
        and isinstance(portfolios, pd.DataFrame)
        and "ID" in portfolios.columns
    ):
        portfolios = portfolios[portfolios["ID"] == portfolio_id].copy()
    if isinstance(portfolios, pd.DataFrame) and "Portfolio" in portfolios.columns:
        if "Portfolio URL" in portfolios.columns:
            portfolios["Portfolio"] = portfolios.apply(
                lambda row: portfolio_link(row["Portfolio"], row["Portfolio URL"]),
                axis=1,
            )
        portfolios = portfolios.drop(columns=["Portfolio URL"], errors="ignore")
    return portfolios


def portfolio_assets_table_data(
    portfolio_view_choice: str | int | None = None,
) -> object:
    columns = [
        "Ticker",
        "Asset",
        "Asset Class",
        "Volume",
        "Price",
        "Value",
        "Currency",
        "Portfolio Description",
    ]
    portfolio_id = _parse_portfolio_view_id(portfolio_view_choice)
    if portfolio_id is None:
        return pd.DataFrame(columns=columns)

    positions = current_positions(
        account_mode=ALL_ACCOUNTS_MODE,
        portfolio_id=portfolio_id,
    ).copy()
    if positions.empty:
        return pd.DataFrame(columns=columns)

    _, description, _, _ = portfolio_details(portfolio_id)
    assets = positions.rename(
        columns={
            "Name": "Asset",
            "Quantity": "Volume",
            "Latest Price": "Price",
            "Market Value": "Value",
        }
    )
    assets["Portfolio Description"] = description
    assets["Ticker"] = assets["Ticker"].map(ticker_link)
    assets["Volume"] = assets["Volume"].map(format_integer_with_commas)
    for column in ["Price", "Value"]:
        assets[column] = assets[column].map(format_two_decimals)
    return assets[columns]


def _parse_portfolio_view_id(
    portfolio_view_choice: str | int | None,
) -> int | None:
    if portfolio_view_choice in (None, "", ALL_MASTER_PORTFOLIOS):
        return None
    return parse_choice_id(portfolio_view_choice)


def _portfolio_view_choice_for_id(
    choices: list[str],
    portfolio_id: int | None,
) -> str:
    if portfolio_id is None:
        return ALL_MASTER_PORTFOLIOS
    prefix = f"{portfolio_id} |"
    return next(
        (choice for choice in choices if choice.startswith(prefix)),
        ALL_MASTER_PORTFOLIOS,
    )


def _portfolio_scope_changed(portfolios_filter: str) -> tuple[Any, ...]:
    choices = portfolio_view_choices(portfolios_filter)
    return (
        gr.update(choices=choices, value=ALL_MASTER_PORTFOLIOS),
        portfolios_table_data(portfolios_filter, ALL_MASTER_PORTFOLIOS),
        portfolio_assets_table_data(ALL_MASTER_PORTFOLIOS),
    )


def _portfolio_view_changed(
    portfolios_filter: str,
    portfolio_view_choice: str | int | None,
) -> tuple[Any, ...]:
    return (
        portfolios_table_data(portfolios_filter, portfolio_view_choice),
        portfolio_assets_table_data(portfolio_view_choice),
    )


def _refresh_portfolio_view(
    portfolios_filter: str,
    portfolio_view_choice: str | int | None,
) -> tuple[Any, ...]:
    choices = portfolio_view_choices(portfolios_filter)
    selected_view = _portfolio_view_choice_for_id(
        choices,
        _parse_portfolio_view_id(portfolio_view_choice),
    )
    return (
        gr.update(choices=choices, value=selected_view),
        portfolios_table_data(portfolios_filter, selected_view),
        portfolio_assets_table_data(selected_view),
    )


def build_portfolios_tab(selected_account: str | None) -> dict[str, Any]:
    with gr.Tab("Portfolios"):
        portfolio_status = gr.Textbox(label="Status", interactive=False)

        with gr.Row():
            portfolio_account_choice = gr.Dropdown(
                label="Account",
                choices=account_choices(include_simulated=True),
                value=selected_account,
            )
            new_portfolio_name = gr.Textbox(label="Portfolio", value="Default Portfolio")
            new_portfolio_url = gr.Textbox(label="Portfolio URL", placeholder="https://")
        new_portfolio_description = gr.Textbox(label="Description", lines=3)
        create_portfolio_button = gr.Button("Create Portfolio", variant="primary")

        edit_portfolio_choice = gr.Dropdown(
            label="Edit Portfolio",
            choices=portfolio_choices_for_account(
                selected_account,
                include_inactive=True,
            ),
        )
        edit_portfolio_name = gr.Textbox(label="Edit Portfolio Name")
        edit_portfolio_url = gr.Textbox(label="Edit Portfolio URL", placeholder="https://")
        edit_portfolio_description = gr.Textbox(label="Edit Description", lines=3)
        edit_portfolio_active = gr.Checkbox(label="Active", value=True)
        update_portfolio_button = gr.Button("Update Portfolio")

        with gr.Row():
            portfolios_filter = gr.Radio(
                label="Show",
                choices=["All", "Real", "Test"],
                value="All",
            )
            portfolio_view_filter = gr.Dropdown(
                label="Portfolio",
                choices=portfolio_view_choices(),
                value=ALL_MASTER_PORTFOLIOS,
                allow_custom_value=False,
                filterable=True,
            )
        portfolios_table = gr.Dataframe(
            value=portfolios_table_data,
            headers=[
                "ID",
                "Broker",
                "Account",
                "Portfolio",
                "Description",
                "Currency",
                "Simulated Account",
                "Active",
            ],
            datatype=[
                "number",
                "str",
                "str",
                "markdown",
                "str",
                "str",
                "str",
                "str",
            ],
            label="Portfolios",
            interactive=False,
        )
        portfolio_assets_table = gr.Dataframe(
            value=portfolio_assets_table_data,
            headers=[
                "Ticker",
                "Asset",
                "Asset Class",
                "Volume",
                "Price",
                "Value",
                "Currency",
                "Portfolio Description",
            ],
            datatype=[
                "markdown",
                "str",
                "str",
                "str",
                "str",
                "str",
                "str",
                "str",
            ],
            label="Portfolio Assets",
            interactive=False,
        )
        refresh_portfolios_button = gr.Button("Refresh Portfolios")

        portfolio_account_choice.change(
            fn=lambda account_choice: gr.update(
                choices=portfolio_choices_for_account(
                    account_choice,
                    include_inactive=True,
                ),
                value=None,
            ),
            inputs=[portfolio_account_choice],
            outputs=[edit_portfolio_choice],
        )
        edit_portfolio_choice.change(
            fn=_load_portfolio_details,
            inputs=[edit_portfolio_choice],
            outputs=[
                edit_portfolio_name,
                edit_portfolio_description,
                edit_portfolio_url,
                edit_portfolio_active,
            ],
        )
        update_portfolio_button.click(
            fn=_update_portfolio_callback,
            inputs=[
                edit_portfolio_choice,
                edit_portfolio_name,
                edit_portfolio_description,
                edit_portfolio_url,
                edit_portfolio_active,
                portfolios_filter,
                portfolio_view_filter,
            ],
            outputs=[
                portfolio_status,
                edit_portfolio_choice,
                portfolio_view_filter,
                portfolios_table,
                portfolio_assets_table,
            ],
        )
        refresh_portfolios_button.click(
            fn=_refresh_portfolio_view,
            inputs=[portfolios_filter, portfolio_view_filter],
            outputs=[
                portfolio_view_filter,
                portfolios_table,
                portfolio_assets_table,
            ],
        )
        portfolios_filter.change(
            fn=_portfolio_scope_changed,
            inputs=[portfolios_filter],
            outputs=[
                portfolio_view_filter,
                portfolios_table,
                portfolio_assets_table,
            ],
        )
        portfolio_view_filter.change(
            fn=_portfolio_view_changed,
            inputs=[portfolios_filter, portfolio_view_filter],
            outputs=[portfolios_table, portfolio_assets_table],
        )

    return {
        "portfolio_status": portfolio_status,
        "portfolio_account_choice": portfolio_account_choice,
        "new_portfolio_name": new_portfolio_name,
        "new_portfolio_url": new_portfolio_url,
        "new_portfolio_description": new_portfolio_description,
        "edit_portfolio_choice": edit_portfolio_choice,
        "create_portfolio_button": create_portfolio_button,
        "portfolios_filter": portfolios_filter,
        "portfolio_view_filter": portfolio_view_filter,
        "portfolios_table": portfolios_table,
        "portfolio_assets_table": portfolio_assets_table,
    }
