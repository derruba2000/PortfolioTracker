from __future__ import annotations

from typing import Any

import gradio as gr

from portfolio_management.services.market_data import market_data_summary, update_market_data
from portfolio_management.tabs._shared import as_date_table, parse_optional_date


def _market_data_table() -> object:
    return as_date_table(market_data_summary(), ["Latest Date"])


def _update_market_data_callback(start_date: str, end_date: str) -> tuple[Any, ...]:
    try:
        result = update_market_data(
            start_date=parse_optional_date(start_date),
            end_date=parse_optional_date(end_date),
        )
        return result.message, _market_data_table()
    except Exception as exc:
        return f"Could not update market data: {exc}", _market_data_table()


def build_market_data_tab() -> dict[str, Any]:
    with gr.Tab("Market Data"):
        market_data_status = gr.Textbox(label="Status", interactive=False)
        with gr.Row():
            market_start_date = gr.Textbox(label="Start Date", placeholder="YYYY-MM-DD")
            market_end_date = gr.Textbox(label="End Date", placeholder="YYYY-MM-DD")
        update_market_data_button = gr.Button("Update Market Data", variant="primary")
        market_data_table = gr.Dataframe(
            value=_market_data_table,
            headers=["Type", "Symbol", "Name", "Currency", "Latest Date"],
            datatype=["str", "str", "str", "str", "date"],
            label="Stored Market Data",
            interactive=False,
            show_fullscreen_button=True,
        )
        update_market_data_button.click(
            fn=_update_market_data_callback,
            inputs=[market_start_date, market_end_date],
            outputs=[market_data_status, market_data_table],
        )

    return {}
