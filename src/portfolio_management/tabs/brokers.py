from __future__ import annotations

from typing import Any

import gradio as gr

from portfolio_management.services.accounts import list_brokers


def build_brokers_tab() -> dict[str, Any]:
    with gr.Tab("Brokers"):
        brokers_table = gr.Dataframe(
            value=list_brokers,
            headers=["ID", "Broker"],
            datatype=["number", "str"],
            label="Brokers",
            interactive=False,
        )
        refresh_brokers_button = gr.Button("Refresh Brokers")
        refresh_brokers_button.click(fn=list_brokers, outputs=[brokers_table])

    return {"brokers_table": brokers_table}
