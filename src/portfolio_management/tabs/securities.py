from __future__ import annotations

from typing import Any

import gradio as gr
import pandas as pd

from portfolio_management.services.reference_data import (
    list_asset_class_codes,
    list_currency_codes,
)
from portfolio_management.services.securities import (
    create_security,
    list_asset_subclass_choices,
    list_securities,
    security_form_values,
    security_detail_symbols,
    yahoo_security_details,
)
from portfolio_management.tabs._shared import ticker_link


DETAIL_KEYS = [
    "snapshot",
    "security_info",
    "analyst_targets",
    "calendar_events",
    "financial_facts",
    "fund_profile",
    "fund_holdings",
    "fund_metrics",
    "fund_performance",
    "fund_asset_allocation",
    "fund_sector_weightings",
    "option_contracts",
]


def securities_table_data() -> object:
    securities = list_securities()
    if isinstance(securities, pd.DataFrame) and "Ticker" in securities.columns:
        securities["Ticker"] = securities["Ticker"].map(ticker_link)
    return securities


def security_detail_choices() -> list[str]:
    return security_detail_symbols()


def security_detail_tables(symbol: str | None) -> tuple[object, ...]:
    details = yahoo_security_details(symbol)
    return tuple(details[key] for key in DETAIL_KEYS)


def _create_security(
    ticker: str,
    description: str,
    asset_class: str,
    asset_subclass: str,
    currency_code: str,
) -> tuple[str, object, object]:
    try:
        status = create_security(
            ticker=ticker,
            description=description,
            asset_class=asset_class,
            asset_subclass=asset_subclass,
            currency_code=currency_code,
        )
    except Exception as exc:
        return (
            f"Could not save security: {exc}",
            securities_table_data(),
            gr.update(),
        )
    clean_ticker = (ticker or "").strip().upper()
    return (
        status,
        securities_table_data(),
        gr.update(choices=security_detail_choices(), value=clean_ticker),
    )


def _refresh_security_details(symbol: str | None) -> tuple[Any, ...]:
    choices = security_detail_choices()
    selected = symbol if symbol in choices else (choices[0] if choices else None)
    return (
        securities_table_data(),
        gr.update(choices=choices, value=selected),
        *security_detail_tables(selected),
    )


def _detail_table(
    label: str,
    headers: list[str],
    value: object,
    datatypes: list[str] | None = None,
) -> gr.Dataframe:
    return gr.Dataframe(
        value=value,
        headers=headers,
        datatype=datatypes or ["str"] * len(headers),
        label=label,
        interactive=False,
    )


def build_securities_tab() -> dict[str, Any]:
    detail_choices = security_detail_choices()
    selected_detail = detail_choices[0] if detail_choices else None
    detail_values = security_detail_tables(selected_detail)
    detail_value_iterator = iter(detail_values)

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
            security_asset_subclass = gr.Dropdown(
                label="Asset Subclass",
                choices=list_asset_subclass_choices(),
                value="STOCK",
                allow_custom_value=False,
                filterable=True,
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
            headers=["Ticker", "Description", "Asset Class", "Asset Subclass", "Currency"],
            datatype=["markdown", "str", "str", "str", "str"],
            label="Securities",
            interactive=False,
        )

        security_detail_filter = gr.Dropdown(
            label="Security Details",
            choices=detail_choices,
            value=selected_detail,
            allow_custom_value=False,
            filterable=True,
        )
        with gr.Tabs():
            with gr.Tab("Overview"):
                snapshot_table = _detail_table(
                    "Security Snapshot",
                    ["Attribute", "Value"],
                    next(detail_value_iterator),
                )
                security_info_table = _detail_table(
                    "Security Information",
                    [
                        "Attribute",
                        "Value Text",
                        "Value Number",
                        "Value Boolean",
                        "Value Date",
                        "Extracted At",
                    ],
                    next(detail_value_iterator),
                )
            with gr.Tab("Research & Events"):
                analyst_targets_table = _detail_table(
                    "Analyst Targets",
                    ["Target Name", "Target Value", "Extracted At"],
                    next(detail_value_iterator),
                )
                calendar_events_table = _detail_table(
                    "Calendar Events",
                    [
                        "Event Name",
                        "Event Index",
                        "Value Text",
                        "Value Number",
                        "Value Date",
                        "Extracted At",
                    ],
                    next(detail_value_iterator),
                )
            with gr.Tab("Financials"):
                financial_facts_table = _detail_table(
                    "Financial Facts",
                    [
                        "Statement Type",
                        "Frequency",
                        "Period End",
                        "Metric",
                        "Value",
                        "Extracted At",
                    ],
                    next(detail_value_iterator),
                )
            with gr.Tab("Fund Profile"):
                fund_profile_table = _detail_table(
                    "Fund Profile",
                    ["Attribute", "Value"],
                    next(detail_value_iterator),
                )
                fund_holdings_table = _detail_table(
                    "Fund Holdings",
                    [
                        "Holding Rank",
                        "Holding Symbol",
                        "Holding Name",
                        "Weight",
                        "Extracted At",
                    ],
                    next(detail_value_iterator),
                )
            with gr.Tab("Fund Analytics"):
                fund_metrics_table = _detail_table(
                    "Fund Metrics",
                    [
                        "Metric Group",
                        "Metric",
                        "Value Text",
                        "Value Number",
                        "Extracted At",
                    ],
                    next(detail_value_iterator),
                )
                fund_performance_table = _detail_table(
                    "Fund Performance",
                    [
                        "Performance Type",
                        "Period",
                        "As Of Date",
                        "Value",
                        "Category Value",
                        "Extracted At",
                    ],
                    next(detail_value_iterator),
                )
                fund_asset_allocation_table = _detail_table(
                    "Fund Asset Allocation",
                    ["Asset Class", "Weight", "Extracted At"],
                    next(detail_value_iterator),
                )
                fund_sector_weightings_table = _detail_table(
                    "Fund Sector Weightings",
                    ["Sector", "Weight", "Extracted At"],
                    next(detail_value_iterator),
                )
            with gr.Tab("Options"):
                option_contracts_table = _detail_table(
                    "Option Contracts",
                    [
                        "Expiration Date",
                        "Option Type",
                        "Contract Symbol",
                        "Last Trade Date",
                        "Strike",
                        "Last Price",
                        "Bid",
                        "Ask",
                        "Price Change",
                        "Percent Change",
                        "Volume",
                        "Open Interest",
                        "Implied Volatility",
                        "In The Money",
                        "Contract Size",
                        "Currency",
                        "Extracted At",
                    ],
                    next(detail_value_iterator),
                )

        detail_tables = [
            snapshot_table,
            security_info_table,
            analyst_targets_table,
            calendar_events_table,
            financial_facts_table,
            fund_profile_table,
            fund_holdings_table,
            fund_metrics_table,
            fund_performance_table,
            fund_asset_allocation_table,
            fund_sector_weightings_table,
            option_contracts_table,
        ]
        refresh_securities_button = gr.Button("Refresh Securities")

        security_ticker.change(
            fn=security_form_values,
            inputs=[
                security_ticker,
                security_description,
                security_asset_class,
                security_asset_subclass,
                security_currency,
            ],
            outputs=[
                security_description,
                security_asset_class,
                security_asset_subclass,
                security_currency,
                securities_status,
            ],
        )
        add_security_button.click(
            fn=_create_security,
            inputs=[
                security_ticker,
                security_description,
                security_asset_class,
                security_asset_subclass,
                security_currency,
            ],
            outputs=[
                securities_status,
                securities_table,
                security_detail_filter,
            ],
        )
        security_detail_filter.change(
            fn=security_detail_tables,
            inputs=[security_detail_filter],
            outputs=detail_tables,
        )
        refresh_securities_button.click(
            fn=_refresh_security_details,
            inputs=[security_detail_filter],
            outputs=[securities_table, security_detail_filter, *detail_tables],
        )

    return {
        "securities_status": securities_status,
        "securities_table": securities_table,
        "security_detail_filter": security_detail_filter,
    }
