from __future__ import annotations

from typing import Any

import gradio as gr

from portfolio_management.services.accounts import account_choices
from portfolio_management.services.analytics import LIVE_MODE
from portfolio_management.services.rebalancing import (
    create_target_allocation,
    default_rebalance_account_choice,
    delete_target_allocation,
    rebalance_report,
    target_allocations,
    target_allocations_cash_void_message,
)
from portfolio_management.services.reference_data import list_asset_class_codes
from portfolio_management.tabs._shared import format_two_decimals


def rebalance_positions(account_choice: str, account_mode: str) -> object:
    rebalance = rebalance_report(account_choice, account_mode=account_mode).copy()
    for column in [
        "Current Value",
        "Actual %",
        "Target %",
        "Drift %",
        "Drift Up %",
        "Drift Down %",
        "Trade Value",
    ]:
        if column in rebalance.columns:
            rebalance[column] = rebalance[column].map(format_two_decimals)
    return rebalance


def _formatted_target_allocations(account_choice: str) -> object:
    df = target_allocations(account_choice).copy()
    for column in ["Target %", "Drift Up %", "Drift Down %"]:
        if column in df.columns:
            df[column] = df[column].map(format_two_decimals)
    return df


def _target_asset_class_choices(account_choice: str) -> list[str]:
    df = target_allocations(account_choice)
    if "Asset Class" not in df.columns:
        return []
    return [str(asset_class) for asset_class in df["Asset Class"].dropna().tolist()]


def _saved_target_update(account_choice: str, selected_asset_class: str | None = None) -> object:
    choices = _target_asset_class_choices(account_choice)
    value = selected_asset_class if selected_asset_class in choices else None
    return gr.update(choices=choices, value=value)


def _rebalance_accounts_for_mode(account_mode: str) -> list[str]:
    return account_choices(include_simulated=True, account_mode=account_mode)


def _rebalance_mode_changed(account_mode: str) -> tuple[Any, ...]:
    accounts = _rebalance_accounts_for_mode(account_mode)
    selected_account = accounts[0] if accounts else None
    return (
        gr.update(choices=accounts, value=selected_account),
        _saved_target_update(selected_account),
        _formatted_target_allocations(selected_account),
        target_allocations_cash_void_message(selected_account),
        rebalance_positions(selected_account, account_mode=account_mode),
    )


def _set_target_allocation(
    account_choice: str,
    asset_class: str,
    target_weight_percent: str,
    drift_up_percent: str,
    drift_down_percent: str,
    account_mode: str,
) -> tuple[Any, ...]:
    try:
        status = create_target_allocation(
            account_choice=account_choice,
            asset_class=asset_class,
            target_weight_percent=target_weight_percent,
            drift_up_percent=drift_up_percent,
            drift_down_percent=drift_down_percent,
        )
    except Exception as exc:
        status = f"Could not set target allocation: {exc}"
    return (
        status,
        _formatted_target_allocations(account_choice),
        target_allocations_cash_void_message(account_choice),
        rebalance_positions(account_choice, account_mode=account_mode),
        _saved_target_update(account_choice, asset_class),
    )


def _delete_target_allocation(
    account_choice: str,
    asset_class: str | None,
    account_mode: str,
) -> tuple[Any, ...]:
    try:
        status = delete_target_allocation(account_choice, asset_class)
    except Exception as exc:
        status = f"Could not delete target allocation: {exc}"
    return (
        status,
        _formatted_target_allocations(account_choice),
        target_allocations_cash_void_message(account_choice),
        rebalance_positions(account_choice, account_mode=account_mode),
        _saved_target_update(account_choice),
    )


def _load_saved_target(account_choice: str, asset_class: str | None) -> tuple[Any, ...]:
    if not asset_class:
        return gr.update(), gr.update(), gr.update(), gr.update()

    df = target_allocations(account_choice)
    if df.empty:
        return gr.update(value=asset_class), gr.update(), gr.update(), gr.update()

    row = df[df["Asset Class"] == asset_class]
    if row.empty:
        return gr.update(value=asset_class), gr.update(), gr.update(), gr.update()

    return (
        gr.update(value=asset_class),
        gr.update(value=format_two_decimals(row.iloc[0]["Target %"])),
        gr.update(value=format_two_decimals(row.iloc[0]["Drift Up %"])),
        gr.update(value=format_two_decimals(row.iloc[0]["Drift Down %"])),
    )


def _refresh_rebalance(account_choice: str, account_mode: str) -> tuple[Any, ...]:
    return (
        _formatted_target_allocations(account_choice),
        target_allocations_cash_void_message(account_choice),
        rebalance_positions(account_choice, account_mode=account_mode),
        _saved_target_update(account_choice),
    )


def build_rebalance_tab(mode_toggle: gr.Radio) -> dict[str, Any]:
    selected_rebalance_account = (
        _rebalance_accounts_for_mode(LIVE_MODE)[0]
        if _rebalance_accounts_for_mode(LIVE_MODE)
        else default_rebalance_account_choice()
    )

    with gr.Tab("Rebalance"):
        rebalance_status = gr.Textbox(label="Status", interactive=False)
        with gr.Row():
            rebalance_account = gr.Dropdown(
                label="Account",
                choices=_rebalance_accounts_for_mode(LIVE_MODE),
                value=selected_rebalance_account,
            )
            saved_target = gr.Dropdown(
                label="Saved Target",
                choices=_target_asset_class_choices(selected_rebalance_account),
            )
            rebalance_asset_class = gr.Dropdown(
                label="Target Asset Class",
                choices=list_asset_class_codes(),
                value="EQUITY",
            )
            target_weight_percent = gr.Textbox(label="Target %", value="60")
            drift_up_percent = gr.Textbox(label="Drift Up %", value="5")
            drift_down_percent = gr.Textbox(label="Drift Down %", value="5")
        with gr.Row():
            set_target_button = gr.Button("Set Target Allocation", variant="primary")
            delete_target_button = gr.Button("Delete Target Allocation")
        cash_void_message = gr.Textbox(
            label="Cash Void",
            value=target_allocations_cash_void_message(selected_rebalance_account),
            interactive=False,
        )
        target_allocations_table = gr.Dataframe(
            value=lambda: _formatted_target_allocations(selected_rebalance_account),
            headers=["Asset Class", "Target %", "Drift Up %", "Drift Down %"],
            datatype=["str", "str", "str", "str"],
            label="Target Allocations",
            interactive=False,
        )
        rebalance_table = gr.Dataframe(
            value=lambda: rebalance_positions(selected_rebalance_account, account_mode=LIVE_MODE),
            headers=[
                "Asset Class",
                "Current Value",
                "Actual %",
                "Target %",
                "Drift %",
                "Drift Up %",
                "Drift Down %",
                "Action",
                "Trade Value",
            ],
            datatype=["str", "str", "str", "str", "str", "str", "str", "str", "str"],
            label="Rebalance Suggestions",
            interactive=False,
        )
        refresh_rebalance_button = gr.Button("Refresh Rebalance")

        set_target_button.click(
            fn=_set_target_allocation,
            inputs=[
                rebalance_account,
                rebalance_asset_class,
                target_weight_percent,
                drift_up_percent,
                drift_down_percent,
                mode_toggle,
            ],
            outputs=[
                rebalance_status,
                target_allocations_table,
                cash_void_message,
                rebalance_table,
                saved_target,
            ],
        )
        delete_target_button.click(
            fn=_delete_target_allocation,
            inputs=[rebalance_account, saved_target, mode_toggle],
            outputs=[
                rebalance_status,
                target_allocations_table,
                cash_void_message,
                rebalance_table,
                saved_target,
            ],
        )
        saved_target.change(
            fn=_load_saved_target,
            inputs=[rebalance_account, saved_target],
            outputs=[
                rebalance_asset_class,
                target_weight_percent,
                drift_up_percent,
                drift_down_percent,
            ],
        )
        refresh_rebalance_button.click(
            fn=_refresh_rebalance,
            inputs=[rebalance_account, mode_toggle],
            outputs=[
                target_allocations_table,
                cash_void_message,
                rebalance_table,
                saved_target,
            ],
        )
        rebalance_account.change(
            fn=_refresh_rebalance,
            inputs=[rebalance_account, mode_toggle],
            outputs=[
                target_allocations_table,
                cash_void_message,
                rebalance_table,
                saved_target,
            ],
        )

    return {
        "rebalance_account": rebalance_account,
        "saved_target": saved_target,
        "target_allocations_table": target_allocations_table,
        "cash_void_message": cash_void_message,
        "rebalance_table": rebalance_table,
    }
