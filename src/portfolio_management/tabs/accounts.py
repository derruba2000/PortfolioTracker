from __future__ import annotations

from typing import Any

import gradio as gr

from portfolio_management.services.accounts import (
    account_choices,
    account_details,
    create_account,
    list_accounts,
    list_brokers_detailed,
    update_account,
)
from portfolio_management.services.reference_data import list_currency_codes


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
            list_brokers_detailed(),
            list_accounts(accounts_filter),
        )

    accounts = account_choices(include_simulated=True, include_inactive=False)
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
        list_brokers_detailed(),
        list_accounts(accounts_filter),
    )


def _load_account_details(account_choice: str) -> tuple[str, str, str, str, str, bool, bool]:
    return account_details(account_choice)


def _update_account_callback(
    account_choice: str,
    broker_name: str,
    account_name: str,
    currency_code: str,
    description: str,
    tax_wrapper_type: str,
    is_simulated: bool,
    is_active: bool,
    accounts_filter: str = "All",
) -> tuple[Any, ...]:
    try:
        status = update_account(
            account_choice=account_choice,
            broker_name=broker_name,
            account_name=account_name,
            currency_code=currency_code,
            description=description,
            tax_wrapper_type=tax_wrapper_type,
            is_simulated=is_simulated,
            is_active=is_active,
        )
    except Exception as exc:
        status = f"Could not update account: {exc}"
    updated_accounts = account_choices(include_simulated=True, include_inactive=True)
    selected = next((choice for choice in updated_accounts if choice.startswith(str(account_choice).split('|')[0].strip())), account_choice)
    return status, gr.update(choices=updated_accounts, value=selected), list_accounts(accounts_filter)


def build_accounts_tab(selected_account: str | None) -> dict[str, Any]:
    with gr.Tab("Accounts"):
        account_status = gr.Textbox(label="Status", interactive=False)

        with gr.Row():
            broker_name_input = gr.Textbox(label="Broker", value="Default Broker")
            account_name_input = gr.Textbox(label="Account", value="Default Account")
            account_currency_code = gr.Dropdown(
                label="Account Currency",
                choices=list_currency_codes(),
                value="GBP",
                allow_custom_value=True,
            )
        new_account_description = gr.Textbox(label="Description", lines=3)
        with gr.Row():
            tax_wrapper_type = gr.Textbox(label="Tax Wrapper", placeholder="ISA, SIPP, Taxable")
            is_simulated = gr.Checkbox(label="Simulation / Paper Trading account")
        create_account_button = gr.Button("Create Account", variant="primary")

        edit_choices = account_choices(include_simulated=True, include_inactive=True)
        edit_selected = selected_account if selected_account in edit_choices else (edit_choices[0] if edit_choices else None)
        broker_name, account_name, currency, description, tax_wrapper, simulated, active = account_details(edit_selected)

        edit_account_choice = gr.Dropdown(
            label="Edit Account",
            choices=edit_choices,
            value=edit_selected,
        )
        with gr.Row():
            edit_broker_name = gr.Textbox(label="Edit Broker", value=broker_name)
            edit_account_name = gr.Textbox(label="Edit Account Name", value=account_name)
            edit_account_currency = gr.Dropdown(
                label="Edit Currency",
                choices=list_currency_codes(),
                value=currency,
                allow_custom_value=True,
            )
        edit_account_description = gr.Textbox(
            label="Edit Description",
            value=description,
            lines=3,
        )
        with gr.Row():
            edit_tax_wrapper = gr.Textbox(label="Edit Tax Wrapper", value=tax_wrapper)
            edit_is_simulated = gr.Checkbox(label="Simulation / Paper Trading account", value=simulated)
            edit_is_active = gr.Checkbox(label="Active", value=active)
        save_account_button = gr.Button("Update Account")

        accounts_filter = gr.Radio(
            label="Show",
            choices=["All", "Real", "Test"],
            value="All",
        )
        accounts_table = gr.Dataframe(
            value=list_accounts,
            headers=["ID", "Broker", "Account", "Description", "Currency", "Tax Wrapper", "Simulated", "Active"],
            datatype=["number", "str", "str", "str", "str", "str", "str", "str"],
            label="Accounts",
            interactive=False,
        )
        refresh_accounts_button = gr.Button("Refresh Accounts")

        refresh_accounts_button.click(fn=list_accounts, inputs=[accounts_filter], outputs=[accounts_table])
        accounts_filter.change(fn=list_accounts, inputs=[accounts_filter], outputs=[accounts_table])
        edit_account_choice.change(
            fn=_load_account_details,
            inputs=[edit_account_choice],
            outputs=[
                edit_broker_name,
                edit_account_name,
                edit_account_currency,
                edit_account_description,
                edit_tax_wrapper,
                edit_is_simulated,
                edit_is_active,
            ],
        )
        save_account_button.click(
            fn=_update_account_callback,
            inputs=[
                edit_account_choice,
                edit_broker_name,
                edit_account_name,
                edit_account_currency,
                edit_account_description,
                edit_tax_wrapper,
                edit_is_simulated,
                edit_is_active,
                accounts_filter,
            ],
            outputs=[account_status, edit_account_choice, accounts_table],
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
