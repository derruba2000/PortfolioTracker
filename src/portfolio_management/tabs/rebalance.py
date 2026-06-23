from __future__ import annotations

from typing import Any

import gradio as gr

from portfolio_management.db.models import AssetClass
from portfolio_management.services.accounts import account_choices
from portfolio_management.services.analytics import LIVE_MODE
from portfolio_management.services.rebalancing import (
    create_target_allocation,
    default_rebalance_account_choice,
    rebalance_report,
    target_allocations,
)
from portfolio_management.tabs._shared import format_two_decimals


def rebalance_positions(account_choice: str, account_mode: str) -> object:
    rebalance = rebalance_report(account_choice, account_mode=account_mode).copy()
    for column in ["Current Value", "Trade Value"]:
        if column in rebalance.columns:
            rebalance[column] = rebalance[column].map(format_two_decimals)
    return rebalance


def _set_target_allocation(
    account_choice: str,
    asset_class: str,
    target_weight_percent: str,
    account_mode: str,
) -> tuple[Any, ...]:
    try:
        status = create_target_allocation(
            account_choice=account_choice,
            asset_class=asset_class,
            target_weight_percent=target_weight_percent,
        )
    except Exception as exc:
        status = f"Could not set target allocation: {exc}"
    return (
        status,
        target_allocations(account_choice),
        rebalance_positions(account_choice, account_mode=account_mode),
    )


def _refresh_rebalance(account_choice: str, account_mode: str) -> tuple[Any, ...]:
    return (
        target_allocations(account_choice),
        rebalance_positions(account_choice, account_mode=account_mode),
    )


def build_rebalance_tab(mode_toggle: gr.Radio) -> dict[str, Any]:
    selected_rebalance_account = default_rebalance_account_choice()

    with gr.Tab("Rebalance"):
        rebalance_status = gr.Textbox(label="Status", interactive=False)
        with gr.Row():
            rebalance_account = gr.Dropdown(
                label="Account",
                choices=account_choices(include_simulated=True),
                value=selected_rebalance_account,
            )
            rebalance_asset_class = gr.Dropdown(
                label="Target Asset Class",
                choices=[ac.value for ac in AssetClass],
                value=AssetClass.EQUITY.value,
            )
            target_weight_percent = gr.Textbox(label="Target %", value="60")
        set_target_button = gr.Button("Set Target Allocation", variant="primary")
        target_allocations_table = gr.Dataframe(
            value=lambda: target_allocations(selected_rebalance_account),
            headers=["Asset Class", "Target %"],
            datatype=["str", "str"],
            label="Target Allocations",
            interactive=False,
        )
        rebalance_table = gr.Dataframe(
            value=lambda: rebalance_positions(selected_rebalance_account, account_mode=LIVE_MODE),
            headers=[
                "Asset Class", "Current Value", "Actual %",
                "Target %", "Drift %", "Action", "Trade Value",
            ],
            datatype=["str", "str", "str", "str", "str", "str", "str"],
            label="Rebalance Suggestions",
            interactive=False,
        )
        refresh_rebalance_button = gr.Button("Refresh Rebalance")

        set_target_button.click(
            fn=_set_target_allocation,
            inputs=[rebalance_account, rebalance_asset_class, target_weight_percent, mode_toggle],
            outputs=[rebalance_status, target_allocations_table, rebalance_table],
        )
        refresh_rebalance_button.click(
            fn=_refresh_rebalance,
            inputs=[rebalance_account, mode_toggle],
            outputs=[target_allocations_table, rebalance_table],
        )
        rebalance_account.change(
            fn=_refresh_rebalance,
            inputs=[rebalance_account, mode_toggle],
            outputs=[target_allocations_table, rebalance_table],
        )

    return {}
