from __future__ import annotations

from datetime import date as date_type
from typing import Any

import gradio as gr

from portfolio_management.db.models import AssetClass, TransactionType
from portfolio_management.services.accounts import account_choices, portfolio_choices_for_account
from portfolio_management.services.transactions import (
    add_manual_transaction,
    import_transactions_from_csv,
    list_transactions,
    transfer_cash,
)
from portfolio_management.tabs._shared import (
    _POPULAR_CURRENCIES,
    as_date_table,
    format_decimal_input,
    format_decimal_with_commas,
    format_integer_with_commas,
    format_quantity_input,
    ticker_link,
)


def transactions_table(transactions_filter: str = "All") -> object:
    txns = as_date_table(list_transactions(transactions_filter), ["Date"])
    import pandas as pd
    if isinstance(txns, pd.DataFrame):
        if "Ticker" in txns.columns:
            txns["Ticker"] = txns["Ticker"].map(ticker_link)
        if "Quantity" in txns.columns:
            txns["Quantity"] = txns["Quantity"].map(format_integer_with_commas)
        for column in ["Price", "Fees"]:
            if column in txns.columns:
                txns[column] = txns[column].map(format_decimal_with_commas)
    return txns


def _account_choices_for_filter(transactions_filter: str) -> list[str]:
    accounts = account_choices(include_simulated=True)
    if transactions_filter == "Real":
        return [c for c in accounts if "[TEST]" not in c]
    if transactions_filter == "Test":
        return [c for c in accounts if "[TEST]" in c]
    return accounts


def _filter_changed(transactions_filter: str) -> tuple[Any, ...]:
    accounts = _account_choices_for_filter(transactions_filter)
    selected_account = accounts[0] if accounts else None
    portfolios = portfolio_choices_for_account(selected_account)
    selected_portfolio = portfolios[0] if portfolios else None
    return (
        transactions_table(transactions_filter),
        gr.update(choices=accounts, value=selected_account),
        gr.update(choices=portfolios, value=selected_portfolio),
        gr.update(choices=accounts, value=selected_account),
        gr.update(choices=accounts, value=selected_account),
    )


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
    asset_class: str,
    security_currency_code: str,
    quantity: str,
    price: str,
    fees: str,
    total_value: str,
    currency_exchange_rate: str,
    transactions_filter: str = "All",
) -> tuple[Any, ...]:
    if not portfolio_choice:
        return (
            "Choose a portfolio before adding a transaction.",
            transactions_table(transactions_filter),
        )
    try:
        status = add_manual_transaction(
            portfolio_id=portfolio_choice,
            date=date,
            transaction_type=transaction_type,
            description=description,
            ticker=ticker,
            security_name=security_name,
            asset_class=asset_class,
            security_currency_code=security_currency_code,
            quantity=quantity,
            price=price,
            fees=fees,
            total_value=total_value,
            currency_exchange_rate=currency_exchange_rate,
        )
        return status, transactions_table(transactions_filter)
    except Exception as exc:
        return f"Could not add transaction: {exc}", transactions_table(transactions_filter)


def _transfer_cash_between_accounts(
    source_account_choice: str,
    target_account_choice: str,
    amount: str,
    transfer_date: str,
    transfer_description: str,
    transactions_filter: str = "All",
) -> tuple[Any, ...]:
    try:
        status = transfer_cash(
            source_account_choice=source_account_choice,
            target_account_choice=target_account_choice,
            amount=amount,
            transfer_date=transfer_date,
            description=transfer_description,
        )
        return status, transactions_table(transactions_filter)
    except Exception as exc:
        return f"Could not transfer cash: {exc}", transactions_table(transactions_filter)


def _import_csv_to_portfolio(
    file: object,
    portfolio_choice: str,
    transactions_filter: str = "All",
) -> tuple[Any, ...]:
    if file is None:
        return "Choose a CSV file to import.", transactions_table(transactions_filter)
    try:
        file_path = getattr(file, "name", file)
        status = import_transactions_from_csv(file_path, portfolio_id=portfolio_choice)
        return status, transactions_table(transactions_filter)
    except Exception as exc:
        return f"Could not import CSV: {exc}", transactions_table(transactions_filter)


def build_data_entry_tab(
    selected_account: str | None,
    selected_portfolio: str | None,
) -> dict[str, Any]:
    with gr.Tab("Data Entry"):
        status = gr.Textbox(label="Status", interactive=False)
        transactions_filter = gr.Radio(
            label="Show",
            choices=["All", "Real", "Test"],
            value="All",
        )

        with gr.Row():
            account_choice = gr.Dropdown(
                label="Account",
                choices=account_choices(include_simulated=True),
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
            ticker = gr.Textbox(label="Ticker", placeholder="AAPL")
        transaction_description = gr.Textbox(label="Description", lines=2)

        with gr.Row():
            security_name = gr.Textbox(label="Security Name")
            asset_class = gr.Dropdown(
                label="Asset Class",
                choices=[ac.value for ac in AssetClass],
                value=AssetClass.EQUITY.value,
            )
            security_currency_code = gr.Dropdown(
                label="Security Currency",
                choices=_POPULAR_CURRENCIES,
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

        add_button = gr.Button("Add Transaction", variant="primary")

        csv_file = gr.File(label="CSV Import", file_types=[".csv"])
        import_button = gr.Button("Import CSV")

        with gr.Row():
            transfer_source_account = gr.Dropdown(
                label="Transfer Source Account",
                choices=account_choices(include_simulated=True),
                value=selected_account,
            )
            transfer_target_account = gr.Dropdown(
                label="Transfer Target Account",
                choices=account_choices(include_simulated=True),
                value=selected_account,
            )

        with gr.Row():
            transfer_amount = gr.Textbox(label="Transfer Amount")
            transfer_description = gr.Textbox(label="Transfer Description")

        transfer_cash_button = gr.Button("Transfer Cash")

        txns_table = gr.Dataframe(
            value=transactions_table,
            headers=[
                "ID", "Date", "Broker", "Account", "Portfolio", "Ticker",
                "Type", "Description", "Quantity", "Price", "Fees", "Total Value", "FX Rate",
            ],
            datatype=[
                "number", "date", "str", "str", "str", "markdown",
                "str", "str", "str", "str", "str", "str",
            ],
            label="Transactions",
            interactive=False,
            show_fullscreen_button=True,
        )
        refresh_transactions_button = gr.Button("Refresh Transactions")

        refresh_transactions_button.click(
            fn=transactions_table,
            inputs=[transactions_filter],
            outputs=[txns_table],
        )
        transactions_filter.change(
            fn=_filter_changed,
            inputs=[transactions_filter],
            outputs=[txns_table, account_choice, portfolio_choice, transfer_source_account, transfer_target_account],
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
                ticker, security_name, asset_class, security_currency_code,
                quantity, price, fees, total_value, currency_exchange_rate,
                transactions_filter,
            ],
            outputs=[status, txns_table],
        )
        transfer_cash_button.click(
            fn=_transfer_cash_between_accounts,
            inputs=[
                transfer_source_account, transfer_target_account,
                transfer_amount, date, transfer_description,
                transactions_filter,
            ],
            outputs=[status, txns_table],
        )
        import_button.click(
            fn=_import_csv_to_portfolio,
            inputs=[csv_file, portfolio_choice, transactions_filter],
            outputs=[status, txns_table],
        )

    return {
        "status": status,
        "account_choice": account_choice,
        "portfolio_choice": portfolio_choice,
        "transactions_filter": transactions_filter,
        "transfer_source_account": transfer_source_account,
        "transfer_target_account": transfer_target_account,
        "txns_table": txns_table,
    }
