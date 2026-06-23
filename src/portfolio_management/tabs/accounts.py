from __future__ import annotations

from typing import Any

import gradio as gr

from portfolio_management.services.accounts import (
    account_choices,
    account_description,
    create_account,
    list_accounts,
    list_brokers,
    update_account_description,
)
from portfolio_management.tabs._shared import _POPULAR_CURRENCIES


def create_account_callback(
    broker_name: str,
    account_name: str,
    currency_code: str,
    description: str,
    tax_wrapper_type: str,
    is_simulated: bool,
    accounts_filter: str = "All",
) -> tuple[Any, ...]:
    try:
        status = create_account(
            broker_name=broker_name,
            account_name=account_name,
            currency_code=currency_code,
            description=description,
            tax_wrapper_type=tax_wrapper_type,
            is_simulated=is_simulated,
        )
    except Exception as exc:
        return (
            f"Could not create account: {exc}",
            gr.update(), gr.update(), gr.update(), gr.update(),
            list_brokers(),
            list_accounts(accounts_filter),
        )

    accounts = account_choices(include_simulated=True)
    selected_account = next(
        (choice for choice in accounts if f"/ {account_name}" in choice),
        accounts[0] if accounts else None,
    )
    return (
        status,
        gr.update(choices=accounts, value=selected_account),
        gr.update(choices=accounts, value=selected_account),
        gr.update(choices=accounts, value=selected_account),
        gr.update(choices=[], value=None),
        list_brokers(),
        list_accounts(accounts_filter),
    )


def _load_account_description(account_choice: str) -> str:
    return account_description(account_choice)


def _update_account_description_callback(
    account_choice: str,
    description: str,
    accounts_filter: str = "All",
) -> tuple[Any, ...]:
    try:
        status = update_account_description(account_choice, description)
    except Exception as exc:
        status = f"Could not update account description: {exc}"
    return status, list_accounts(accounts_filter)


def build_accounts_tab(selected_account: str | None) -> dict[str, Any]:
    with gr.Tab("Accounts"):
        account_status = gr.Textbox(label="Status", interactive=False)

        with gr.Row():
            broker_name_input = gr.Textbox(label="Broker", value="Default Broker")
            account_name_input = gr.Textbox(label="Account", value="Default Account")
            account_currency_code = gr.Dropdown(
                label="Account Currency",
                choices=_POPULAR_CURRENCIES,
                value="GBP",
                allow_custom_value=True,
            )
        new_account_description = gr.Textbox(label="Description", lines=3)
        with gr.Row():
            tax_wrapper_type = gr.Textbox(label="Tax Wrapper", placeholder="ISA, SIPP, Taxable")
            is_simulated = gr.Checkbox(label="Simulation / Paper Trading account")
        create_account_button = gr.Button("Create Account", variant="primary")

        edit_account_choice = gr.Dropdown(
            label="Edit Account",
            choices=account_choices(include_simulated=True),
            value=selected_account,
        )
        edit_account_description = gr.Textbox(
            label="Edit Description",
            value=account_description(selected_account),
            lines=3,
        )
        save_account_description_button = gr.Button("Save Description")

        accounts_filter = gr.Radio(
            label="Show",
            choices=["All", "Real", "Test"],
            value="All",
        )
        accounts_table = gr.Dataframe(
            value=list_accounts,
            headers=["ID", "Broker", "Account", "Description", "Currency", "Tax Wrapper", "Simulated"],
            datatype=["number", "str", "str", "str", "str", "str", "str"],
            label="Accounts",
            interactive=False,
        )
        refresh_accounts_button = gr.Button("Refresh Accounts")

        refresh_accounts_button.click(fn=list_accounts, inputs=[accounts_filter], outputs=[accounts_table])
        accounts_filter.change(fn=list_accounts, inputs=[accounts_filter], outputs=[accounts_table])
        edit_account_choice.change(
            fn=_load_account_description,
            inputs=[edit_account_choice],
            outputs=[edit_account_description],
        )
        save_account_description_button.click(
            fn=_update_account_description_callback,
            inputs=[edit_account_choice, edit_account_description, accounts_filter],
            outputs=[account_status, accounts_table],
        )

    return {
        "account_status": account_status,
        "broker_name_input": broker_name_input,
        "account_name_input": account_name_input,
        "account_currency_code": account_currency_code,
        "new_account_description": new_account_description,
        "tax_wrapper_type": tax_wrapper_type,
        "is_simulated": is_simulated,
        "create_account_button": create_account_button,
        "edit_account_choice": edit_account_choice,
        "accounts_filter": accounts_filter,
        "accounts_table": accounts_table,
    }
