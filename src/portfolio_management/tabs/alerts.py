from __future__ import annotations

from typing import Any

import gradio as gr

from portfolio_management.services.alerts import (
    acknowledge_alerts,
    active_alert_choices,
    list_alerts,
    purge_all_alerts,
)


def _alert_table(is_acknowledged: bool) -> object:
    return list_alerts(is_acknowledged)


def refresh_alerts() -> tuple[object, object, object]:
    return (
        _alert_table(False),
        _alert_table(True),
        gr.update(choices=active_alert_choices(), value=[]),
    )


def acknowledge_selected_alerts(
    selected_hashes: list[str] | None,
) -> tuple[str, object, object, object]:
    acknowledged = acknowledge_alerts(selected_hashes)
    active, historical, choices = refresh_alerts()
    if acknowledged:
        status = f"Acknowledged {acknowledged} alert(s)."
    else:
        status = "Select one or more active alerts to acknowledge."
    return status, active, historical, choices


def purge_alert_data() -> tuple[str, object, object, object]:
    alerts_deleted, errors_deleted = purge_all_alerts()
    active, historical, choices = refresh_alerts()
    status = (
        f"Purged {alerts_deleted} alert(s) and {errors_deleted} import error log(s)."
    )
    return status, active, historical, choices


def build_alerts_tab() -> dict[str, Any]:
    with gr.Tab("Alerts"):
        with gr.Row():
            refresh_button = gr.Button("Refresh Alerts")
            acknowledge_button = gr.Button(
                "Acknowledge Selected",
                variant="primary",
            )
            purge_button = gr.Button("Purge All Data", variant="stop")
        status = gr.Textbox(label="Status", interactive=False)
        active_table = gr.Dataframe(
            value=lambda: _alert_table(False),
            headers=["ID", "Timestamp", "Type", "Message"],
            datatype=["number", "str", "str", "str"],
            label="Active Alerts",
            interactive=False,
            show_fullscreen_button=True,
        )
        selected_alerts = gr.CheckboxGroup(
            label="Alerts to acknowledge",
            choices=active_alert_choices(),
            value=[],
        )
        historical_table = gr.Dataframe(
            value=lambda: _alert_table(True),
            headers=["ID", "Timestamp", "Type", "Message"],
            datatype=["number", "str", "str", "str"],
            label="Acknowledged Alerts",
            interactive=False,
            show_fullscreen_button=True,
        )

        refresh_button.click(
            fn=refresh_alerts,
            outputs=[active_table, historical_table, selected_alerts],
        )
        acknowledge_button.click(
            fn=acknowledge_selected_alerts,
            inputs=[selected_alerts],
            outputs=[status, active_table, historical_table, selected_alerts],
        )
        purge_button.click(
            fn=purge_alert_data,
            outputs=[status, active_table, historical_table, selected_alerts],
        )

    return {
        "active_table": active_table,
        "historical_table": historical_table,
        "selected_alerts": selected_alerts,
        "status": status,
        "refresh_button": refresh_button,
        "acknowledge_button": acknowledge_button,
        "purge_button": purge_button,
    }
