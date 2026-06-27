from __future__ import annotations

from typing import Any

import gradio as gr

from portfolio_management.services.accounts import (
    broker_choices,
    broker_details,
    create_broker,
    delete_broker,
    list_brokers,
    list_brokers_detailed,
    update_broker,
)


def _refresh_broker_outputs() -> tuple[Any, ...]:
    choices = broker_choices(include_inactive=True)
    selected = choices[0] if choices else None
    name, description, is_active = broker_details(selected)
    return (
        gr.update(choices=choices, value=selected),
        name,
        description,
        is_active,
        list_brokers_detailed(),
    )


def _broker_selected(broker_choice: str) -> tuple[str, str, bool]:
    return broker_details(broker_choice)


def _create_broker_callback(broker_name: str, description: str) -> tuple[Any, ...]:
    try:
        status = create_broker(broker_name, description)
    except Exception as exc:
        return f"Could not save broker: {exc}", *_refresh_broker_outputs()
    return status, *_refresh_broker_outputs()


def _save_broker_callback(
    broker_choice: str,
    broker_name: str,
    description: str,
    is_active: bool,
) -> tuple[Any, ...]:
    try:
        status = update_broker(broker_choice, broker_name, description, is_active)
    except Exception as exc:
        return f"Could not update broker: {exc}", *_refresh_broker_outputs()
    return status, *_refresh_broker_outputs()


def _delete_broker_callback(broker_choice: str) -> tuple[Any, ...]:
    try:
        status = delete_broker(broker_choice)
    except Exception as exc:
        return f"Could not delete broker: {exc}", *_refresh_broker_outputs()
    return status, *_refresh_broker_outputs()


def build_brokers_tab() -> dict[str, Any]:
    with gr.Tab("Brokers"):
        broker_status = gr.Textbox(label="Status", interactive=False)

        with gr.Row():
            new_broker_name = gr.Textbox(label="Broker", value="Default Broker")
            new_broker_description = gr.Textbox(label="Description")
        create_broker_button = gr.Button("Save Broker", variant="primary")

        edit_broker_choice = gr.Dropdown(
            label="Edit Broker",
            choices=broker_choices(include_inactive=True),
        )
        edit_broker_name = gr.Textbox(label="Broker Name")
        edit_broker_description = gr.Textbox(label="Description", lines=3)
        edit_broker_active = gr.Checkbox(label="Active", value=True)

        with gr.Row():
            update_broker_button = gr.Button("Update Broker")
            delete_broker_button = gr.Button("Delete Broker", variant="stop")

        brokers_table = gr.Dataframe(
            value=list_brokers_detailed,
            headers=["ID", "Broker", "Description", "Active"],
            datatype=["number", "str", "str", "str"],
            label="Brokers",
            interactive=False,
        )
        refresh_brokers_button = gr.Button("Refresh Brokers")

        edit_broker_choice.change(
            fn=_broker_selected,
            inputs=[edit_broker_choice],
            outputs=[edit_broker_name, edit_broker_description, edit_broker_active],
        )
        create_broker_button.click(
            fn=_create_broker_callback,
            inputs=[new_broker_name, new_broker_description],
            outputs=[
                broker_status,
                edit_broker_choice,
                edit_broker_name,
                edit_broker_description,
                edit_broker_active,
                brokers_table,
            ],
        )
        update_broker_button.click(
            fn=_save_broker_callback,
            inputs=[edit_broker_choice, edit_broker_name, edit_broker_description, edit_broker_active],
            outputs=[
                broker_status,
                edit_broker_choice,
                edit_broker_name,
                edit_broker_description,
                edit_broker_active,
                brokers_table,
            ],
        )
        delete_broker_button.click(
            fn=_delete_broker_callback,
            inputs=[edit_broker_choice],
            outputs=[
                broker_status,
                edit_broker_choice,
                edit_broker_name,
                edit_broker_description,
                edit_broker_active,
                brokers_table,
            ],
        )
        refresh_brokers_button.click(
            fn=lambda: list_brokers_detailed(),
            outputs=[brokers_table],
        )

    return {
        "brokers_table": brokers_table,
        "create_broker_button": create_broker_button,
        "update_broker_button": update_broker_button,
        "delete_broker_button": delete_broker_button,
        "refresh_brokers_button": refresh_brokers_button,
    }
