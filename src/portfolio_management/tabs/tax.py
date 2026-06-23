from __future__ import annotations

from typing import Any

import gradio as gr

from portfolio_management.services.analytics import (
    LIVE_MODE,
    export_tax_prep_report_csv,
    realized_pnl_report,
    tax_prep_report,
)
from portfolio_management.tabs._shared import as_date_table


def _tax_report_table(tax_year: str, account_mode: str) -> object:
    clean_year = (tax_year or "").strip()
    report = realized_pnl_report(
        tax_year=int(clean_year) if clean_year else None,
        account_mode=account_mode,
    )
    return as_date_table(report, ["Date"])


def _tax_prep_table(tax_year: str, account_mode: str) -> object:
    clean_year = (tax_year or "").strip()
    report = tax_prep_report(
        tax_year=int(clean_year) if clean_year else None,
        account_mode=account_mode,
    )
    return as_date_table(report, ["Date"])


def _refresh_tax_report(tax_year: str, account_mode: str) -> object:
    return _tax_report_table(tax_year, account_mode)


def _refresh_tax_prep_report(tax_year: str, account_mode: str) -> object:
    return _tax_prep_table(tax_year, account_mode)


def _export_tax_prep_report(tax_year: str, account_mode: str) -> str:
    clean_year = (tax_year or "").strip()
    return export_tax_prep_report_csv(
        tax_year=int(clean_year) if clean_year else None,
        account_mode=account_mode,
    )


def build_tax_tab(mode_toggle: gr.Radio) -> dict[str, Any]:
    with gr.Tab("Tax"):
        tax_year = gr.Textbox(label="Tax Year", placeholder="YYYY")
        tax_report = gr.Dataframe(
            value=lambda: _tax_report_table("", LIVE_MODE),
            headers=[
                "Date", "Broker", "Account", "Portfolio", "Ticker",
                "Quantity Sold", "Proceeds", "Cost Basis", "Realized P&L",
            ],
            datatype=["date", "str", "str", "str", "str", "str", "str", "str", "str"],
            label="Realized Gains",
            interactive=False,
            show_fullscreen_button=True,
        )
        refresh_tax_button = gr.Button("Refresh Tax Report")
        refresh_tax_button.click(
            fn=_refresh_tax_report,
            inputs=[tax_year, mode_toggle],
            outputs=[tax_report],
        )

        tax_prep_table = gr.Dataframe(
            value=lambda: _tax_prep_table("", LIVE_MODE),
            headers=[
                "Type", "Date", "Broker", "Account", "Portfolio",
                "Ticker", "Amount", "Cost Basis", "Realized P&L",
            ],
            datatype=["str", "date", "str", "str", "str", "str", "str", "str", "str"],
            label="Tax Prep Report",
            interactive=False,
            show_fullscreen_button=True,
        )
        tax_export = gr.File(label="Tax CSV Export", interactive=False)
        with gr.Row():
            refresh_tax_prep_button = gr.Button("Refresh Tax Prep")
            export_tax_button = gr.Button("Export Tax CSV", variant="primary")
        refresh_tax_prep_button.click(
            fn=_refresh_tax_prep_report,
            inputs=[tax_year, mode_toggle],
            outputs=[tax_prep_table],
        )
        export_tax_button.click(
            fn=_export_tax_prep_report,
            inputs=[tax_year, mode_toggle],
            outputs=[tax_export],
        )

    return {
        "tax_year": tax_year,
        "tax_report": tax_report,
    }
