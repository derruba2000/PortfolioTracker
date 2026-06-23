from __future__ import annotations

from typing import Any

import gradio as gr
import pandas as pd

from portfolio_management.services.accounts import (
    account_choices,
    create_portfolio,
    list_portfolios,
    portfolio_details,
    portfolio_choices_for_account,
    update_portfolio,
)
from portfolio_management.tabs._shared import portfolio_link


def create_portfolio_callback(
    account_choice: str,
    portfolio_name: str,
    description: str,
    portfolio_url: str,
    portfolios_filter: str = "All",
) -> tuple[Any, ...]:
    try:
        status = create_portfolio(
            account_choice=account_choice,
            portfolio_name=portfolio_name,
            description=description,
            portfolio_url=portfolio_url,
        )
    except Exception as exc:
        return (
            f"Could not create portfolio: {exc}",
            gr.update(), gr.update(), gr.update(),
            portfolios_table_data(portfolios_filter),
        )

    accounts = account_choices(include_simulated=True)
    portfolios = portfolio_choices_for_account(account_choice)
    selected_portfolio = next(
        (choice for choice in portfolios if f"| {portfolio_name}" in choice),
        portfolios[0] if portfolios else None,
    )
    return (
        status,
        gr.update(choices=accounts, value=account_choice),
        gr.update(choices=accounts, value=account_choice),
        gr.update(choices=portfolios, value=selected_portfolio),
        portfolios_table_data(portfolios_filter),
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

    return (
        status,
        gr.update(),
        portfolios_table_data(portfolios_filter),
    )


def portfolios_table_data(portfolios_filter: str = "All") -> object:
    portfolios = list_portfolios(portfolios_filter)
    if isinstance(portfolios, pd.DataFrame) and "Portfolio" in portfolios.columns:
        if "Portfolio URL" in portfolios.columns:
            portfolios["Portfolio"] = portfolios.apply(
                lambda row: portfolio_link(row["Portfolio"], row["Portfolio URL"]),
                axis=1,
            )
        portfolios = portfolios.drop(columns=["Portfolio URL"], errors="ignore")
    return portfolios


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
            choices=portfolio_choices_for_account(selected_account, include_inactive=True),
        )
        edit_portfolio_name = gr.Textbox(label="Edit Portfolio Name")
        edit_portfolio_url = gr.Textbox(label="Edit Portfolio URL", placeholder="https://")
        edit_portfolio_description = gr.Textbox(label="Edit Description", lines=3)
        edit_portfolio_active = gr.Checkbox(label="Active", value=True)
        update_portfolio_button = gr.Button("Update Portfolio")

        portfolios_filter = gr.Radio(
            label="Show",
            choices=["All", "Real", "Test"],
            value="All",
        )
        portfolios_table = gr.Dataframe(
            value=portfolios_table_data,
            headers=["ID", "Broker", "Account", "Portfolio", "Description", "Currency", "Simulated Account", "Active"],
            datatype=["number", "str", "str", "markdown", "str", "str", "str", "str"],
            label="Portfolios",
            interactive=False,
        )
        refresh_portfolios_button = gr.Button("Refresh Portfolios")

        portfolio_account_choice.change(
            fn=lambda account_choice: gr.update(
                choices=portfolio_choices_for_account(account_choice, include_inactive=True),
                value=None,
            ),
            inputs=[portfolio_account_choice],
            outputs=[edit_portfolio_choice],
        )
        edit_portfolio_choice.change(
            fn=_load_portfolio_details,
            inputs=[edit_portfolio_choice],
            outputs=[edit_portfolio_name, edit_portfolio_description, edit_portfolio_url, edit_portfolio_active],
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
            ],
            outputs=[portfolio_status, edit_portfolio_choice, portfolios_table],
        )

        refresh_portfolios_button.click(fn=portfolios_table_data, inputs=[portfolios_filter], outputs=[portfolios_table])
        portfolios_filter.change(fn=portfolios_table_data, inputs=[portfolios_filter], outputs=[portfolios_table])

    return {
        "portfolio_status": portfolio_status,
        "portfolio_account_choice": portfolio_account_choice,
        "new_portfolio_name": new_portfolio_name,
        "new_portfolio_url": new_portfolio_url,
        "new_portfolio_description": new_portfolio_description,
        "edit_portfolio_choice": edit_portfolio_choice,
        "create_portfolio_button": create_portfolio_button,
        "portfolios_filter": portfolios_filter,
        "portfolios_table": portfolios_table,
    }
