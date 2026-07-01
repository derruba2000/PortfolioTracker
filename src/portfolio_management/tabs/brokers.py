from __future__ import annotations

from typing import Any

import gradio as gr

from portfolio_management.services.accounts import (
    broker_choices,
    broker_details,
    create_broker,
    delete_broker,
    list_brokers_detailed,
    parse_choice_id,
    update_broker,
)


def _refresh_broker_outputs() -> tuple[Any, ...]:
    choices = broker_choices(include_inactive=True)
    selected = choices[0] if choices else None
    details = broker_details(selected)
    return (
        gr.update(choices=choices, value=selected),
        *details,
        list_brokers_detailed(),
    )


def _empty_fee_values() -> list[str]:
    return list(broker_details(None)[3:])


def _broker_choice_for_name(name: str) -> str | None:
    clean_name = (name or "").strip()
    if not clean_name:
        return None
    for choice in broker_choices(include_inactive=True):
        choice_name = str(broker_details(choice)[0]).strip()
        if choice_name.casefold() == clean_name.casefold():
            return choice
    return None


def _broker_selected(broker_name_choice: str) -> tuple[object, ...]:
    broker_id = parse_choice_id(broker_name_choice)
    if broker_id is not None:
        return broker_details(broker_name_choice)

    matched_choice = _broker_choice_for_name(str(broker_name_choice or ""))
    if matched_choice is not None:
        return broker_details(matched_choice)

    clean_name = (broker_name_choice or "").strip()
    return (
        clean_name,
        "",
        True,
        *_empty_fee_values(),
    )


def _save_broker_callback(
    broker_name_choice: str,
    description: str,
    is_active: bool,
    trade_fee_fixed: str,
    trade_fee_percent: str,
    fx_fee_percent: str,
    spread_fee_percent: str,
    custody_fee_percent_annual: str,
    platform_fee_fixed_monthly: str,
    account_fee_fixed_monthly: str,
    inactivity_fee_fixed_monthly: str,
    withdrawal_fee_fixed: str,
    deposit_fee_fixed: str,
    stamp_duty_percent: str,
    regulatory_fee_percent: str,
    margin_interest_percent_annual: str,
    short_borrow_fee_percent_annual: str,
) -> tuple[Any, ...]:
    clean_name = (broker_name_choice or "").strip()
    if not clean_name:
        return "Could not save broker: Broker is required.", *_refresh_broker_outputs()

    parsed_id = parse_choice_id(broker_name_choice)
    matched_choice = _broker_choice_for_name(clean_name)

    try:
        if parsed_id is not None or matched_choice is not None:
            status = update_broker(
                broker_choice=broker_name_choice if parsed_id is not None else matched_choice,
                broker_name=clean_name,
                description=description,
                is_active=is_active,
                trade_fee_fixed=trade_fee_fixed,
                trade_fee_percent=trade_fee_percent,
                fx_fee_percent=fx_fee_percent,
                spread_fee_percent=spread_fee_percent,
                custody_fee_percent_annual=custody_fee_percent_annual,
                platform_fee_fixed_monthly=platform_fee_fixed_monthly,
                account_fee_fixed_monthly=account_fee_fixed_monthly,
                inactivity_fee_fixed_monthly=inactivity_fee_fixed_monthly,
                withdrawal_fee_fixed=withdrawal_fee_fixed,
                deposit_fee_fixed=deposit_fee_fixed,
                stamp_duty_percent=stamp_duty_percent,
                regulatory_fee_percent=regulatory_fee_percent,
                margin_interest_percent_annual=margin_interest_percent_annual,
                short_borrow_fee_percent_annual=short_borrow_fee_percent_annual,
            )
        else:
            status = create_broker(
                broker_name=clean_name,
                description=description,
                trade_fee_fixed=trade_fee_fixed,
                trade_fee_percent=trade_fee_percent,
                fx_fee_percent=fx_fee_percent,
                spread_fee_percent=spread_fee_percent,
                custody_fee_percent_annual=custody_fee_percent_annual,
                platform_fee_fixed_monthly=platform_fee_fixed_monthly,
                account_fee_fixed_monthly=account_fee_fixed_monthly,
                inactivity_fee_fixed_monthly=inactivity_fee_fixed_monthly,
                withdrawal_fee_fixed=withdrawal_fee_fixed,
                deposit_fee_fixed=deposit_fee_fixed,
                stamp_duty_percent=stamp_duty_percent,
                regulatory_fee_percent=regulatory_fee_percent,
                margin_interest_percent_annual=margin_interest_percent_annual,
                short_borrow_fee_percent_annual=short_borrow_fee_percent_annual,
            )
    except Exception as exc:
        return f"Could not save broker: {exc}", *_refresh_broker_outputs()
    return status, *_refresh_broker_outputs()


def _delete_broker_callback(broker_name_choice: str) -> tuple[Any, ...]:
    parsed_id = parse_choice_id(broker_name_choice)
    matched_choice = broker_name_choice if parsed_id is not None else _broker_choice_for_name(
        str(broker_name_choice or "")
    )
    if matched_choice is None:
        return "Could not delete broker: Select an existing broker.", *_refresh_broker_outputs()

    try:
        status = delete_broker(matched_choice)
    except Exception as exc:
        return f"Could not delete broker: {exc}", *_refresh_broker_outputs()
    return status, *_refresh_broker_outputs()


def build_brokers_tab() -> dict[str, Any]:
    with gr.Tab("Brokers"):
        broker_status = gr.Textbox(label="Status", interactive=False)

        with gr.Row():
            broker_name = gr.Dropdown(
                label="Broker Name",
                choices=broker_choices(include_inactive=True),
                value=None,
                allow_custom_value=True,
                filterable=True,
            )
            broker_description = gr.Textbox(label="Description")
            broker_active = gr.Checkbox(label="Active", value=True)
        with gr.Row():
            trade_fee_fixed = gr.Textbox(label="Trade Fee (Fixed)", value="0")
            trade_fee_percent = gr.Textbox(label="Trade Fee (%)", value="0")
            fx_fee_percent = gr.Textbox(label="FX Fee (%)", value="0")
            spread_fee_percent = gr.Textbox(label="Spread Fee (%)", value="0")
        with gr.Row():
            custody_fee_percent_annual = gr.Textbox(
                label="Custody Fee Annual (%)",
                value="0",
            )
            platform_fee_fixed_monthly = gr.Textbox(
                label="Platform Fee Monthly (Fixed)",
                value="0",
            )
            account_fee_fixed_monthly = gr.Textbox(
                label="Account Fee Monthly (Fixed)",
                value="0",
            )
            inactivity_fee_fixed_monthly = gr.Textbox(
                label="Inactivity Fee Monthly (Fixed)",
                value="0",
            )
        with gr.Row():
            withdrawal_fee_fixed = gr.Textbox(label="Withdrawal Fee (Fixed)", value="0")
            deposit_fee_fixed = gr.Textbox(label="Deposit Fee (Fixed)", value="0")
            stamp_duty_percent = gr.Textbox(label="Stamp Duty (%)", value="0")
            regulatory_fee_percent = gr.Textbox(label="Regulatory Fee (%)", value="0")
        with gr.Row():
            margin_interest_percent_annual = gr.Textbox(
                label="Margin Interest Annual (%)",
                value="0",
            )
            short_borrow_fee_percent_annual = gr.Textbox(
                label="Short Borrow Fee Annual (%)",
                value="0",
            )
        save_broker_button = gr.Button("Save Broker", variant="primary")

        with gr.Row():
            delete_broker_button = gr.Button("Delete Broker", variant="stop")

        brokers_table = gr.Dataframe(
            value=list_brokers_detailed,
            headers=[
                "ID",
                "Broker",
                "Description",
                "Active",
                "Trade Fee (Fixed)",
                "Trade Fee (%)",
                "FX Fee (%)",
                "Spread Fee (%)",
                "Custody Fee Annual (%)",
                "Platform Fee Monthly (Fixed)",
                "Account Fee Monthly (Fixed)",
                "Inactivity Fee Monthly (Fixed)",
                "Withdrawal Fee (Fixed)",
                "Deposit Fee (Fixed)",
                "Stamp Duty (%)",
                "Regulatory Fee (%)",
                "Margin Interest Annual (%)",
                "Short Borrow Fee Annual (%)",
            ],
            datatype=[
                "number",
                "str",
                "str",
                "str",
                "str",
                "str",
                "str",
                "str",
                "str",
                "str",
                "str",
                "str",
                "str",
                "str",
                "str",
                "str",
                "str",
                "str",
            ],
            label="Brokers",
            interactive=False,
        )
        refresh_brokers_button = gr.Button("Refresh Brokers")

        broker_name.change(
            fn=_broker_selected,
            inputs=[broker_name],
            outputs=[
                broker_name,
                broker_description,
                broker_active,
                trade_fee_fixed,
                trade_fee_percent,
                fx_fee_percent,
                spread_fee_percent,
                custody_fee_percent_annual,
                platform_fee_fixed_monthly,
                account_fee_fixed_monthly,
                inactivity_fee_fixed_monthly,
                withdrawal_fee_fixed,
                deposit_fee_fixed,
                stamp_duty_percent,
                regulatory_fee_percent,
                margin_interest_percent_annual,
                short_borrow_fee_percent_annual,
            ],
        )
        save_broker_button.click(
            fn=_save_broker_callback,
            inputs=[
                broker_name,
                broker_description,
                broker_active,
                trade_fee_fixed,
                trade_fee_percent,
                fx_fee_percent,
                spread_fee_percent,
                custody_fee_percent_annual,
                platform_fee_fixed_monthly,
                account_fee_fixed_monthly,
                inactivity_fee_fixed_monthly,
                withdrawal_fee_fixed,
                deposit_fee_fixed,
                stamp_duty_percent,
                regulatory_fee_percent,
                margin_interest_percent_annual,
                short_borrow_fee_percent_annual,
            ],
            outputs=[
                broker_status,
                broker_name,
                broker_description,
                broker_active,
                trade_fee_fixed,
                trade_fee_percent,
                fx_fee_percent,
                spread_fee_percent,
                custody_fee_percent_annual,
                platform_fee_fixed_monthly,
                account_fee_fixed_monthly,
                inactivity_fee_fixed_monthly,
                withdrawal_fee_fixed,
                deposit_fee_fixed,
                stamp_duty_percent,
                regulatory_fee_percent,
                margin_interest_percent_annual,
                short_borrow_fee_percent_annual,
                brokers_table,
            ],
        )
        delete_broker_button.click(
            fn=_delete_broker_callback,
            inputs=[broker_name],
            outputs=[
                broker_status,
                broker_name,
                broker_description,
                broker_active,
                trade_fee_fixed,
                trade_fee_percent,
                fx_fee_percent,
                spread_fee_percent,
                custody_fee_percent_annual,
                platform_fee_fixed_monthly,
                account_fee_fixed_monthly,
                inactivity_fee_fixed_monthly,
                withdrawal_fee_fixed,
                deposit_fee_fixed,
                stamp_duty_percent,
                regulatory_fee_percent,
                margin_interest_percent_annual,
                short_borrow_fee_percent_annual,
                brokers_table,
            ],
        )
        refresh_brokers_button.click(
            fn=lambda: list_brokers_detailed(),
            outputs=[brokers_table],
        )

    return {
        "brokers_table": brokers_table,
        "save_broker_button": save_broker_button,
        "delete_broker_button": delete_broker_button,
        "refresh_brokers_button": refresh_brokers_button,
    }
