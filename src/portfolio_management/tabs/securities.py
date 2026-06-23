from __future__ import annotations

from typing import Any

import gradio as gr
import pandas as pd

from portfolio_management.services.reference_data import list_asset_class_codes, list_currency_codes
from portfolio_management.services.securities import create_security, list_securities
from portfolio_management.tabs._shared import ticker_link


def securities_table_data() -> object:
    securities = list_securities()
    if isinstance(securities, pd.DataFrame) and "Ticker" in securities.columns:
        securities["Ticker"] = securities["Ticker"].map(ticker_link)
    return securities


def _create_security(
    ticker: str,
    description: str,
    asset_class: str,
    currency_code: str,
) -> tuple[str, object]:
    try:
        status = create_security(
            ticker=ticker,
            description=description,
            asset_class=asset_class,
            currency_code=currency_code,
        )
    except Exception as exc:
        return f"Could not save security: {exc}", securities_table_data()
    return status, securities_table_data()


def build_securities_tab() -> dict[str, Any]:
    with gr.Tab("Securities"):
        securities_status = gr.Textbox(label="Security Status", interactive=False)
        with gr.Row():
            security_ticker = gr.Textbox(label="Ticker", placeholder="VWRP.L")
            security_description = gr.Textbox(
                label="Description",
                placeholder="Vanguard FTSE All-World UCITS ETF",
            )
        with gr.Row():
            security_asset_class = gr.Dropdown(
                label="Asset Class",
                choices=list_asset_class_codes(),
                value="EQUITY",
                allow_custom_value=True,
            )
            security_currency = gr.Dropdown(
                label="Currency",
                choices=list_currency_codes(),
                value="GBP",
                allow_custom_value=True,
            )
        add_security_button = gr.Button("Save Security", variant="primary")
        securities_table = gr.Dataframe(
            value=securities_table_data,
            headers=["Ticker", "Description", "Asset Class", "Currency"],
            datatype=["markdown", "str", "str", "str"],
            label="Securities",
            interactive=False,
        )
        refresh_securities_button = gr.Button("Refresh Securities")

        add_security_button.click(
            fn=_create_security,
            inputs=[security_ticker, security_description, security_asset_class, security_currency],
            outputs=[securities_status, securities_table],
        )
        refresh_securities_button.click(fn=securities_table_data, outputs=[securities_table])

    return {
        "securities_status": securities_status,
        "securities_table": securities_table,
    }
