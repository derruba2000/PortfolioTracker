from __future__ import annotations

from datetime import date as date_type
from decimal import Decimal, InvalidOperation
from typing import Any

import gradio as gr
import pandas as pd

from portfolio_management.db.models import TransactionType
from portfolio_management.services.accounts import account_choices, portfolio_choices_for_account
from portfolio_management.services.analysis_filters import account_mode_to_table_filter
from portfolio_management.services.analytics import LIVE_MODE
from portfolio_management.services.transactions import (
    add_manual_transaction,
    import_transactions_from_csv,
    list_transactions,
    transfer_cash,
)
from portfolio_management.services.reference_data import list_currency_codes
from portfolio_management.services.securities import get_security_defaults, list_security_tickers
from portfolio_management.tabs._shared import (
    as_date_table,
    format_decimal_input,
    format_decimal_with_commas,
    format_integer_with_commas,
    format_quantity_input,
    portfolio_link,
    ticker_link,
)


def transactions_table(account_mode: str = LIVE_MODE) -> object:
    transactions_filter = account_mode_to_table_filter(account_mode)
    txns = as_date_table(list_transactions(transactions_filter), ["Date"])
    if isinstance(txns, pd.DataFrame):
        if "Portfolio" in txns.columns and "Portfolio URL" in txns.columns:
            txns["Portfolio"] = txns.apply(
                lambda row: portfolio_link(row["Portfolio"], row["Portfolio URL"]),
                axis=1,
            )
            txns = txns.drop(columns=["Portfolio URL"])
        if "Ticker" in txns.columns:
            txns["Ticker"] = txns["Ticker"].map(ticker_link)
        if "Quantity" in txns.columns:
            txns["Quantity"] = txns["Quantity"].map(format_integer_with_commas)
        for column in ["Price", "Fees", "Total Value", "FX Rate"]:
            if column in txns.columns:
                txns[column] = txns[column].map(format_decimal_with_commas)
    return txns


def _auto_total_value(quantity: str, price: str, current_total: str) -> str:
    _ = current_total
    try:
        q = Decimal(str(quantity or "0").replace(",", "") or "0")
        p = Decimal(str(price or "0").replace(",", "") or "0")
        if q <= 0 or p <= 0:
            return ""
        return f"{q * p:,.2f}"
    except (InvalidOperation, ValueError):
        return ""


def _security_currencies() -> list[str]:
    return list_currency_codes()


def _ticker_choices() -> list[str]:
    return list_security_tickers()


def _ticker_changed(
    ticker: str,
    current_description: str,
    current_currency: str,
) -> tuple[str, str]:
    description, _asset_class, currency = get_security_defaults(
        ticker=ticker,
        current_description=current_description,
        current_asset_class="EQUITY",
        current_currency=current_currency,
    )
    return description, currency


def _account_choices_for_mode(account_mode: str) -> list[str]:
    return account_choices(include_simulated=True, account_mode=account_mode)


def _filter_changed(account_mode: str) -> tuple[Any, ...]:
    accounts = _account_choices_for_mode(account_mode)
    selected_account = accounts[0] if accounts else None
    portfolios = portfolio_choices_for_account(selected_account)
    selected_portfolio = portfolios[0] if portfolios else None
    return (
        transactions_table(account_mode),
        gr.update(choices=accounts, value=selected_account),
        gr.update(choices=portfolios, value=selected_portfolio),
        gr.update(choices=accounts, value=selected_account),
        gr.update(choices=accounts, value=selected_account),
    )


data_entry_mode_changed = _filter_changed


def _update_portfolios(account_choice: str) -> object:
    portfolios = portfolio_choices_for_account(account_choice)
    selected_portfolio = portfolios[0] if portfolios else None
    return gr.update(choices=portfolios, value=selected_portfolio)


def _add_manual_transaction(
    portfolio_choice: str,
    date: str,
    transaction_type: str,
    description: str,
    ticker: str,
    security_name: str,
    security_currency_code: str,
    quantity: str,
    price: str,
    fees: str,
    total_value: str,
    currency_exchange_rate: str,
    account_mode: str = LIVE_MODE,
) -> tuple[Any, ...]:
    if not portfolio_choice:
        return (
            "Choose a portfolio before adding a transaction.",
            transactions_table(account_mode),
        )
    try:
        status = add_manual_transaction(
            portfolio_id=portfolio_choice,
            date=date,
            transaction_type=transaction_type,
            description=description,
            ticker=ticker,
            security_name=security_name,
            asset_class="EQUITY",
            security_currency_code=security_currency_code,
            quantity=quantity,
            price=price,
            fees=fees,
            total_value=total_value,
            currency_exchange_rate=currency_exchange_rate,
        )
        return status, transactions_table(account_mode)
    except Exception as exc:
        return f"Could not add transaction: {exc}", transactions_table(account_mode)


def _transfer_cash_between_accounts(
    source_account_choice: str,
    target_account_choice: str,
    amount: str,
    transfer_date: str,
    transfer_description: str,
    account_mode: str = LIVE_MODE,
) -> tuple[Any, ...]:
    try:
        status = transfer_cash(
            source_account_choice=source_account_choice,
            target_account_choice=target_account_choice,
            amount=amount,
            transfer_date=transfer_date,
            description=transfer_description,
        )
        return status, transactions_table(account_mode)
    except Exception as exc:
        return f"Could not transfer cash: {exc}", transactions_table(account_mode)


def _import_csv_to_portfolio(
    file: object,
    portfolio_choice: str,
    account_mode: str = LIVE_MODE,
) -> tuple[Any, ...]:
    if file is None:
        return "Choose a CSV file to import.", transactions_table(account_mode)
    try:
        file_path = getattr(file, "name", file)
        status = import_transactions_from_csv(file_path, portfolio_id=portfolio_choice)
        return status, transactions_table(account_mode)
    except Exception as exc:
        return f"Could not import CSV: {exc}", transactions_table(account_mode)


def build_data_entry_tab(
    selected_account: str | None,
    selected_portfolio: str | None,
    mode_toggle: gr.Radio,
) -> dict[str, Any]:
    with gr.Tab("Transactions Entry"):
        status = gr.Textbox(label="Status", interactive=False)
        with gr.Tabs():
            with gr.Tab("Transactions"):
                with gr.Row():
                    account_choice = gr.Dropdown(
                        label="Account",
                        choices=account_choices(include_simulated=True, account_mode=LIVE_MODE),
                        value=selected_account,
                    )
                    portfolio_choice = gr.Dropdown(
                        label="Portfolio",
                        choices=portfolio_choices_for_account(selected_account),
                        value=selected_portfolio,
                    )

                with gr.Row():
                    date = gr.DateTime(
                        label="Date",
                        include_time=False,
                        type="string",
                        value=lambda: date_type.today().isoformat(),
                    )
                    transaction_type = gr.Dropdown(
                        label="Type",
                        choices=[tt.value for tt in TransactionType],
                        value=TransactionType.BUY.value,
                    )
                    ticker = gr.Dropdown(
                        label="Ticker",
                        choices=_ticker_choices(),
                        allow_custom_value=True,
                        value=None,
                    )
                transaction_description = gr.Textbox(label="Description", lines=2)

                with gr.Row():
                    security_name = gr.Textbox(label="Security Name")
                    security_currency_code = gr.Dropdown(
                        label="Security Currency",
                        choices=_security_currencies(),
                        value="GBP",
                        allow_custom_value=True,
                    )

                with gr.Row():
                    quantity = gr.Textbox(label="Quantity", value="0")
                    price = gr.Textbox(label="Price", value="0")
                    fees = gr.Textbox(label="Fees", value="0")
                quantity.input(fn=format_quantity_input, inputs=[quantity], outputs=[quantity])
                price.input(fn=format_decimal_input, inputs=[price], outputs=[price])
                fees.input(fn=format_decimal_input, inputs=[fees], outputs=[fees])

                with gr.Row():
                    total_value = gr.Textbox(label="Total Value")
                    currency_exchange_rate = gr.Textbox(label="FX Rate", value="1")

                quantity.input(fn=_auto_total_value, inputs=[quantity, price, total_value], outputs=[total_value])
                price.input(fn=_auto_total_value, inputs=[quantity, price, total_value], outputs=[total_value])

                add_button = gr.Button("Add Transaction", variant="primary")

                csv_file = gr.File(label="CSV Import", file_types=[".csv"])
                import_button = gr.Button("Import CSV")

                ticker.change(
                    fn=_ticker_changed,
                    inputs=[ticker, security_name, security_currency_code],
                    outputs=[security_name, security_currency_code],
                )

                txns_table = gr.Dataframe(
                    value=lambda: transactions_table(LIVE_MODE),
                    headers=[
                        "ID", "Date", "Broker", "Account", "Portfolio", "Ticker",
                        "Type", "Description", "Quantity", "Price", "Fees", "Total Value", "FX Rate",
                    ],
                    datatype=[
                        "number", "date", "str", "str", "markdown", "markdown",
                        "str", "str", "str", "str", "str", "str",
                    ],
                    label="Transactions",
                    interactive=False,
                    show_fullscreen_button=True,
                )
                refresh_transactions_button = gr.Button("Refresh Transactions")

            with gr.Tab("Cash Transfer"):
                with gr.Row():
                    transfer_source_account = gr.Dropdown(
                        label="Transfer Source Account",
                        choices=account_choices(include_simulated=True, account_mode=LIVE_MODE),
                        value=selected_account,
                    )
                    transfer_target_account = gr.Dropdown(
                        label="Transfer Target Account",
                        choices=account_choices(include_simulated=True, account_mode=LIVE_MODE),
                        value=selected_account,
                    )

                with gr.Row():
                    transfer_amount = gr.Textbox(label="Transfer Amount")
                    transfer_description = gr.Textbox(label="Transfer Description")

                transfer_cash_button = gr.Button("Transfer Cash")

        refresh_transactions_button.click(
            fn=transactions_table,
            inputs=[mode_toggle],
            outputs=[txns_table],
        )
        account_choice.change(
            fn=_update_portfolios,
            inputs=[account_choice],
            outputs=[portfolio_choice],
        )
        add_button.click(
            fn=_add_manual_transaction,
            inputs=[
                portfolio_choice, date, transaction_type, transaction_description,
                ticker, security_name, security_currency_code,
                quantity, price, fees, total_value, currency_exchange_rate,
                mode_toggle,
            ],
            outputs=[status, txns_table],
        )
        transfer_cash_button.click(
            fn=_transfer_cash_between_accounts,
            inputs=[
                transfer_source_account, transfer_target_account,
                transfer_amount, date, transfer_description,
                mode_toggle,
            ],
            outputs=[status, txns_table],
        )
        import_button.click(
            fn=_import_csv_to_portfolio,
            inputs=[csv_file, portfolio_choice, mode_toggle],
            outputs=[status, txns_table],
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
