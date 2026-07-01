from __future__ import annotations

from datetime import date as date_type
from datetime import timedelta
from typing import Any

import gradio as gr
import pandas as pd

from portfolio_management.db.models import AssetClass, TransactionType
from portfolio_management.services.accounts import account_choices, portfolio_choices_for_account
from portfolio_management.services.analysis_filters import ALL_PORTFOLIOS, account_mode_to_table_filter
from portfolio_management.services.analytics import LIVE_MODE
from portfolio_management.services.transactions import list_transactions
from portfolio_management.services.securities import (
    get_ticker_price_and_trend,
)
from portfolio_management.tabs._shared import (
    as_date_table,
    format_decimal_with_commas,
    format_integer_with_commas,
    portfolio_link,
    ticker_link,
)
def transactions_table(
    account_mode: str = LIVE_MODE,
    portfolio_filter: str | int | None = None,
    start_date: str | date_type | None = None,
    end_date: str | date_type | None = None,
    asset_class_filter: str = "All",
    transaction_type_filter: str = "All",
) -> object:
    transactions_filter = account_mode_to_table_filter(account_mode)
    selected_portfolio = None if portfolio_filter in (None, "", ALL_PORTFOLIOS) else portfolio_filter
    txns = as_date_table(
        list_transactions(
            account_filter=transactions_filter,
            portfolio_filter=selected_portfolio,
            start_date=start_date,
            end_date=end_date,
            asset_class_filter=asset_class_filter,
            transaction_type_filter=transaction_type_filter,
        ),
        ["Date"],
    )
    if isinstance(txns, pd.DataFrame):
        if "Portfolio" in txns.columns and "Portfolio URL" in txns.columns:
            txns["Portfolio"] = txns.apply(
                lambda row: portfolio_link(row["Portfolio"], row["Portfolio URL"]),
                axis=1,
            )
            txns = txns.drop(columns=["Portfolio URL"])
        if "Ticker" in txns.columns:
            txns["Ticker"] = txns["Ticker"].map(ticker_link)
            txns["Price Trend"] = txns["Ticker"].map(_ticker_trend_for_ledger)
        if "Quantity" in txns.columns:
            txns["Quantity"] = txns["Quantity"].map(format_integer_with_commas)
        for column in ["Price", "Fees", "Total Value", "FX Rate"]:
            if column in txns.columns:
                txns[column] = txns[column].map(format_decimal_with_commas)
        if "Price Trend" not in txns.columns:
            txns["Price Trend"] = ""
    return txns


_PRICE_TREND_CSS = """
<style>
@keyframes blink-green {
  0%, 100% { background: #16a34a; }
  50% { background: #4ade80; }
}
@keyframes blink-red {
  0%, 100% { background: #dc2626; }
  50% { background: #f87171; }
}
</style>"""


def _build_price_trend_html(trend: str, price_str: str) -> str:
    if not price_str or trend == "none":
        return ""
    if trend == "up":
        color, arrow, anim = "#16a34a", "▲", "blink-green 1s ease-in-out 4"
    elif trend == "down":
        color, arrow, anim = "#dc2626", "▼", "blink-red 1s ease-in-out 4"
    else:
        color, arrow, anim = "#6b7280", "─", ""

    blink = f"animation:{anim};" if anim else ""
    style = (
        f"background:{color};color:white;padding:3px 10px;"
        f"border-radius:4px;font-weight:bold;font-size:0.9em;{blink}"
    )
    return f'{_PRICE_TREND_CSS}<span style="{style}">{arrow} {price_str}</span>'


def _ticker_trend_for_ledger(ticker_cell: object) -> str:
    raw_ticker = str(ticker_cell or "").strip()
    if not raw_ticker:
        return ""
    # ticker_cell may already contain anchor markup.
    if ">" in raw_ticker and "<" in raw_ticker:
        raw_ticker = raw_ticker.split(">")[-2].split("<")[0]
    price_str, trend = get_ticker_price_and_trend(raw_ticker)
    return _build_price_trend_html(trend, price_str)


def _account_choices_for_mode(account_mode: str) -> list[str]:
    return account_choices(include_simulated=True, account_mode=account_mode)


def _asset_class_filter_choices() -> list[str]:
    return ["All", *[asset.value for asset in AssetClass]]


def _transaction_type_filter_choices() -> list[str]:
    return ["All", *[transaction_type.value for transaction_type in TransactionType]]


def _selected_or_first(current_value: str | None, choices: list[str]) -> str | None:
    return current_value if current_value in choices else choices[0] if choices else None


def _filter_changed(account_mode: str) -> tuple[Any, ...]:
    accounts = _account_choices_for_mode(account_mode)
    selected_account = _selected_or_first(None, accounts)
    portfolios = _portfolio_choices_for_account_filter(selected_account)
    selected_portfolio = _selected_or_first(ALL_PORTFOLIOS, portfolios)
    return (
        transactions_table(account_mode, portfolio_filter=selected_portfolio),
        gr.update(choices=accounts, value=selected_account),
        gr.update(choices=portfolios, value=selected_portfolio),
        gr.update(choices=accounts, value=selected_account),
        gr.update(choices=accounts, value=selected_account),
    )


data_entry_mode_changed = _filter_changed


def _update_portfolios(account_choice: str) -> object:
    portfolios = _portfolio_choices_for_account_filter(account_choice)
    selected_portfolio = ALL_PORTFOLIOS if portfolios else None
    return gr.update(choices=portfolios, value=selected_portfolio)


def _portfolio_choices_for_account_filter(account_choice: str | None) -> list[str]:
    return [ALL_PORTFOLIOS, *portfolio_choices_for_account(account_choice)]


def _ledger_filtered_table(
    account_mode: str,
    portfolio_filter: str,
    start_date: str,
    end_date: str,
    asset_class_filter: str,
    transaction_type_filter: str,
) -> object:
    return transactions_table(
        account_mode=account_mode,
        portfolio_filter=portfolio_filter,
        start_date=start_date,
        end_date=end_date,
        asset_class_filter=asset_class_filter,
        transaction_type_filter=transaction_type_filter,
    )


def _account_changed(
    account_choice: str,
    account_mode: str,
    start_date: str,
    end_date: str,
    asset_class_filter: str,
    transaction_type_filter: str,
) -> tuple[object, object]:
    portfolio_update = _update_portfolios(account_choice)
    return (
        portfolio_update,
        _ledger_filtered_table(
            account_mode=account_mode,
            portfolio_filter=portfolio_update.get("value", ALL_PORTFOLIOS),
            start_date=start_date,
            end_date=end_date,
            asset_class_filter=asset_class_filter,
            transaction_type_filter=transaction_type_filter,
        ),
    )


def build_data_entry_tab(
    selected_account: str | None,
    selected_portfolio: str | None,
    mode_toggle: gr.Radio,
) -> dict[str, Any]:
    initial_accounts = _account_choices_for_mode(LIVE_MODE)
    selected_account = _selected_or_first(selected_account, initial_accounts)
    initial_portfolios = _portfolio_choices_for_account_filter(selected_account)
    selected_portfolio = _selected_or_first(selected_portfolio, initial_portfolios) or ALL_PORTFOLIOS
    default_end_date = date_type.today()
    default_start_date = default_end_date - timedelta(days=29)

    with gr.Tab("Transactions"):
        status = gr.Textbox(
            label="Status",
            value="Read-only ledger mode: add/edit/delete actions are disabled.",
            interactive=False,
        )

        with gr.Row():
            account_choice = gr.Dropdown(
                label="Account",
                choices=initial_accounts,
                value=selected_account,
            )
            portfolio_choice = gr.Dropdown(
                label="Portfolio",
                choices=initial_portfolios,
                value=selected_portfolio,
            )

        with gr.Row():
            start_date_filter = gr.DateTime(
                label="Start Date",
                include_time=False,
                type="string",
                value=default_start_date.isoformat(),
            )
            end_date_filter = gr.DateTime(
                label="End Date",
                include_time=False,
                type="string",
                value=default_end_date.isoformat(),
            )
            asset_class_filter = gr.Dropdown(
                label="Asset Class",
                choices=_asset_class_filter_choices(),
                value="All",
            )
            transaction_type_filter = gr.Dropdown(
                label="Transaction Type",
                choices=_transaction_type_filter_choices(),
                value="All",
            )

        txns_table = gr.Dataframe(
            value=lambda: transactions_table(
                LIVE_MODE,
                portfolio_filter=selected_portfolio,
                start_date=default_start_date.isoformat(),
                end_date=default_end_date.isoformat(),
                asset_class_filter="All",
                transaction_type_filter="All",
            ),
            headers=[
                "ID",
                "Order ID",
                "Date",
                "Broker",
                "Account",
                "Portfolio",
                "Ticker",
                "Price Trend",
                "Type",
                "Description",
                "Quantity",
                "Price",
                "Fees",
                "Total Value",
                "FX Rate",
            ],
            datatype=[
                "number",
                "str",
                "date",
                "str",
                "str",
                "markdown",
                "markdown",
                "markdown",
                "str",
                "str",
                "str",
                "str",
                "str",
                "str",
                "str",
            ],
            label="Transactions Ledger",
            interactive=False,
            show_fullscreen_button=True,
        )
        refresh_transactions_button = gr.Button("Refresh Ledger")

        transfer_source_account = gr.Dropdown(
            label="Transfer Source Account",
            choices=initial_accounts,
            value=selected_account,
            visible=False,
        )
        transfer_target_account = gr.Dropdown(
            label="Transfer Target Account",
            choices=initial_accounts,
            value=selected_account,
            visible=False,
        )

        refresh_transactions_button.click(
            fn=_ledger_filtered_table,
            inputs=[
                mode_toggle,
                portfolio_choice,
                start_date_filter,
                end_date_filter,
                asset_class_filter,
                transaction_type_filter,
            ],
            outputs=[txns_table],
        )
        account_choice.change(
            fn=_account_changed,
            inputs=[
                account_choice,
                mode_toggle,
                start_date_filter,
                end_date_filter,
                asset_class_filter,
                transaction_type_filter,
            ],
            outputs=[portfolio_choice, txns_table],
        )
        portfolio_choice.change(
            fn=_ledger_filtered_table,
            inputs=[
                mode_toggle,
                portfolio_choice,
                start_date_filter,
                end_date_filter,
                asset_class_filter,
                transaction_type_filter,
            ],
            outputs=[txns_table],
        )
        start_date_filter.change(
            fn=_ledger_filtered_table,
            inputs=[
                mode_toggle,
                portfolio_choice,
                start_date_filter,
                end_date_filter,
                asset_class_filter,
                transaction_type_filter,
            ],
            outputs=[txns_table],
        )
        end_date_filter.change(
            fn=_ledger_filtered_table,
            inputs=[
                mode_toggle,
                portfolio_choice,
                start_date_filter,
                end_date_filter,
                asset_class_filter,
                transaction_type_filter,
            ],
            outputs=[txns_table],
        )
        asset_class_filter.change(
            fn=_ledger_filtered_table,
            inputs=[
                mode_toggle,
                portfolio_choice,
                start_date_filter,
                end_date_filter,
                asset_class_filter,
                transaction_type_filter,
            ],
            outputs=[txns_table],
        )
        transaction_type_filter.change(
            fn=_ledger_filtered_table,
            inputs=[
                mode_toggle,
                portfolio_choice,
                start_date_filter,
                end_date_filter,
                asset_class_filter,
                transaction_type_filter,
            ],
            outputs=[txns_table],
        )

    return {
        "status": status,
        "account_choice": account_choice,
        "portfolio_choice": portfolio_choice,
        "transfer_source_account": transfer_source_account,
        "transfer_target_account": transfer_target_account,
        "txns_table": txns_table,
        "refresh_transactions_button": refresh_transactions_button,
    }
