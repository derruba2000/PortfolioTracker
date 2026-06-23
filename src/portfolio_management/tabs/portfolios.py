from __future__ import annotations

from typing import Any

import gradio as gr

from portfolio_management.services.accounts import (
    account_choices,
    create_portfolio,
    list_portfolios,
    portfolio_choices_for_account,
)


def create_portfolio_callback(
    account_choice: str,
    portfolio_name: str,
    description: str,
    portfolios_filter: str = "All",
) -> tuple[Any, ...]:
    try:
        status = create_portfolio(
            account_choice=account_choice,
            portfolio_name=portfolio_name,
            description=description,
        )
    except Exception as exc:
        return (
            f"Could not create portfolio: {exc}",
            gr.update(), gr.update(), gr.update(),
            list_portfolios(portfolios_filter),
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
        list_portfolios(portfolios_filter),
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
        new_portfolio_description = gr.Textbox(label="Description", lines=3)
        create_portfolio_button = gr.Button("Create Portfolio", variant="primary")

        portfolios_filter = gr.Radio(
            label="Show",
            choices=["All", "Real", "Test"],
            value="All",
        )
        portfolios_table = gr.Dataframe(
            value=list_portfolios,
            headers=["ID", "Broker", "Account", "Portfolio", "Description", "Currency", "Simulated Account"],
            datatype=["number", "str", "str", "str", "str", "str", "str"],
            label="Portfolios",
            interactive=False,
        )
        refresh_portfolios_button = gr.Button("Refresh Portfolios")

        refresh_portfolios_button.click(fn=list_portfolios, inputs=[portfolios_filter], outputs=[portfolios_table])
        portfolios_filter.change(fn=list_portfolios, inputs=[portfolios_filter], outputs=[portfolios_table])

    return {
        "portfolio_status": portfolio_status,
        "portfolio_account_choice": portfolio_account_choice,
        "new_portfolio_name": new_portfolio_name,
        "new_portfolio_description": new_portfolio_description,
        "create_portfolio_button": create_portfolio_button,
        "portfolios_filter": portfolios_filter,
        "portfolios_table": portfolios_table,
    }
