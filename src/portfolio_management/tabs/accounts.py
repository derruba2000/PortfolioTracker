from __future__ import annotations

from typing import Any

import gradio as gr

from portfolio_management.services.accounts import (
    account_choices,
    account_details,
    broker_choices,
    broker_details,
    create_account,
    list_accounts,
    list_brokers_detailed,
    update_account,
)
from portfolio_management.services.analysis_filters import account_mode_to_table_filter
from portfolio_management.services.analytics import LIVE_MODE
from portfolio_management.services.reference_data import list_currency_codes


def accounts_for_mode(account_mode: str) -> object:
    return list_accounts(account_mode_to_table_filter(account_mode))


def account_edit_choices_for_mode(account_mode: str, selected: str | None = None) -> object:
    choices = account_choices(
        include_simulated=True,
        include_inactive=True,
        account_mode=account_mode,
    )
    value = selected if selected in choices else (choices[0] if choices else None)
    return gr.update(choices=choices, value=value)


def broker_dropdown_choices(include_inactive: bool = False) -> list[str]:
    return broker_choices(include_inactive=include_inactive)


def _broker_name_from_choice(broker_choice: str | None) -> str:
    broker_name, _description, _active = broker_details(broker_choice)
    return broker_name


def _broker_choice_for_name(
    broker_name: str,
    include_inactive: bool = True,
) -> str | None:
    for choice in broker_dropdown_choices(include_inactive=include_inactive):
        choice_name, _description, _active = broker_details(choice)
        if choice_name == broker_name:
            return choice
    return None


def create_account_callback(
    broker_choice: str,
    account_name: str,
    currency_code: str,
    description: str,
    tax_wrapper_type: str,
    is_simulated: bool,
    account_mode: str = LIVE_MODE,
) -> tuple[Any, ...]:
    accounts_filter = account_mode_to_table_filter(account_mode)
    broker_name = _broker_name_from_choice(broker_choice)
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

    accounts = account_choices(
        include_simulated=True,
        include_inactive=False,
        account_mode=account_mode,
    )
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


def _load_account_details(account_choice: str) -> tuple[Any, ...]:
    broker_name, account_name, currency, description, tax_wrapper, simulated, active = (
        account_details(account_choice)
    )
    return (
        _broker_choice_for_name(broker_name),
        account_name,
        currency,
        description,
        tax_wrapper,
        simulated,
        active,
    )


def _update_account_callback(
    account_choice: str,
    broker_choice: str,
    account_name: str,
    currency_code: str,
    description: str,
    tax_wrapper_type: str,
    is_simulated: bool,
    is_active: bool,
    account_mode: str = LIVE_MODE,
) -> tuple[Any, ...]:
    accounts_filter = account_mode_to_table_filter(account_mode)
    broker_name = _broker_name_from_choice(broker_choice)
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
    updated_accounts = account_choices(
        include_simulated=True,
        include_inactive=True,
        account_mode=account_mode,
    )
    selected = next((choice for choice in updated_accounts if choice.startswith(str(account_choice).split('|')[0].strip())), account_choice)
    return status, gr.update(choices=updated_accounts, value=selected), list_accounts(accounts_filter)


def build_accounts_tab(selected_account: str | None, mode_toggle: gr.Radio) -> dict[str, Any]:
    with gr.Tab("Accounts"):
        account_status = gr.Textbox(label="Status", interactive=False)
        active_brokers = broker_dropdown_choices()
        all_brokers = broker_dropdown_choices(include_inactive=True)
        selected_broker = active_brokers[0] if active_brokers else None

        with gr.Row():
            broker_name_input = gr.Dropdown(
                label="Broker",
                choices=active_brokers,
                value=selected_broker,
                allow_custom_value=False,
            )
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

        edit_choices = account_choices(
            include_simulated=True,
            include_inactive=True,
            account_mode=LIVE_MODE,
        )
        edit_selected = selected_account if selected_account in edit_choices else (edit_choices[0] if edit_choices else None)
        broker_name, account_name, currency, description, tax_wrapper, simulated, active = account_details(edit_selected)
        edit_selected_broker = _broker_choice_for_name(broker_name)

        edit_account_choice = gr.Dropdown(
            label="Edit Account",
            choices=edit_choices,
            value=edit_selected,
        )
        with gr.Row():
            edit_broker_name = gr.Dropdown(
                label="Edit Broker",
                choices=all_brokers,
                value=edit_selected_broker,
                allow_custom_value=False,
            )
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

        accounts_table = gr.Dataframe(
            value=lambda: accounts_for_mode(LIVE_MODE),
            headers=["ID", "Broker", "Account", "Description", "Currency", "Tax Wrapper", "Simulated", "Active"],
            datatype=["number", "str", "str", "str", "str", "str", "str", "str"],
            label="Accounts",
            interactive=False,
        )
        refresh_accounts_button = gr.Button("Refresh Accounts")

        refresh_accounts_button.click(
            fn=accounts_for_mode,
            inputs=[mode_toggle],
            outputs=[accounts_table],
        )
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
                mode_toggle,
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
        "edit_broker_name": edit_broker_name,
        "accounts_table": accounts_table,
        "refresh_accounts_button": refresh_accounts_button,
    }
