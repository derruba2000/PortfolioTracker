from __future__ import annotations

from datetime import date as date_type
from decimal import Decimal, InvalidOperation

import gradio as gr
import pandas as pd

from portfolio_management.config import load_settings
from portfolio_management.db.init_db import initialize_database
from portfolio_management.db.models import AssetClass, TransactionType
from portfolio_management.services.accounts import (
    account_description,
    account_choices,
    create_account,
    create_portfolio,
    default_account_choice,
    default_portfolio_choice,
    list_accounts,
    list_brokers,
    list_portfolios,
    portfolio_choices_for_account,
    update_account_description,
)
from portfolio_management.services.analytics import (
    LIVE_MODE,
    SANDBOX_MODE,
    allocation_by_asset_class,
    allocation_by_currency,
    current_positions,
    dashboard_summary,
    export_tax_prep_report_csv,
    realized_pnl_report,
    tax_prep_report,
    twr_curve,
)
from portfolio_management.services.benchmarks import (
    benchmark_choices,
    benchmark_overlay,
    default_benchmark_choice,
)
from portfolio_management.services.market_data import market_data_summary, update_market_data
from portfolio_management.services.rebalancing import (
    create_target_allocation,
    default_rebalance_account_choice,
    rebalance_report,
    target_allocations,
)
from portfolio_management.services.transactions import (
    add_manual_transaction,
    import_transactions_from_csv,
    list_transactions,
    transfer_cash,
)


def _parse_optional_date(raw_value: str) -> date_type | None:
    clean_value = (raw_value or "").strip()
    if not clean_value:
        return None
    return date_type.fromisoformat(clean_value)


def _as_date_table(dataframe: object, date_columns: list[str]) -> object:
    if not isinstance(dataframe, pd.DataFrame):
        return dataframe
    formatted = dataframe.copy()
    for column in date_columns:
        if column in formatted.columns:
            parsed = pd.to_datetime(formatted[column], errors="coerce")
            formatted[column] = parsed.dt.date.where(parsed.notna(), None)
    return formatted


def _transactions_table() -> object:
    return _as_date_table(list_transactions(), ["Date"])


def _market_data_table() -> object:
    return _as_date_table(market_data_summary(), ["Latest Date"])


def _tax_report_table(tax_year: str, account_mode: str) -> object:
    clean_year = (tax_year or "").strip()
    report = realized_pnl_report(
        tax_year=int(clean_year) if clean_year else None,
        account_mode=account_mode,
    )
    return _as_date_table(report, ["Date"])


def _tax_prep_table(tax_year: str, account_mode: str) -> object:
    clean_year = (tax_year or "").strip()
    report = tax_prep_report(
        tax_year=int(clean_year) if clean_year else None,
        account_mode=account_mode,
    )
    return _as_date_table(report, ["Date"])


def _update_market_data_callback(start_date: str, end_date: str) -> tuple[str, object]:
    try:
        result = update_market_data(
            start_date=_parse_optional_date(start_date),
            end_date=_parse_optional_date(end_date),
        )
        return result.message, _market_data_table()
    except Exception as exc:
        return f"Could not update market data: {exc}", _market_data_table()


def _mode_banner(account_mode: str) -> str:
    if account_mode == SANDBOX_MODE:
        return (
            "<div style='background:#fff3cd;border:1px solid #f1c40f;"
            "padding:12px;border-radius:6px;color:#664d03;'>"
            "<strong>Sandbox Mode</strong> showing simulated accounts only.</div>"
        )
    return (
        "<div style='background:#d1e7dd;border:1px solid #198754;"
        "padding:12px;border-radius:6px;color:#0f5132;'>"
        "<strong>Live Mode</strong> showing real accounts only.</div>"
    )


def _format_two_decimals(value: object) -> str:
    try:
        return f"{Decimal(str(value)):.2f}"
    except (InvalidOperation, ValueError, TypeError):
        return str(value)


def _dashboard_positions(account_mode: str) -> object:
    positions = current_positions(account_mode=account_mode).copy()
    for column in ["Quantity", "Market Value", "Unrealized P&L"]:
        if column in positions.columns:
            positions[column] = positions[column].map(_format_two_decimals)
    return positions


def _rebalance_positions(account_choice: str, account_mode: str) -> object:
    rebalance = rebalance_report(account_choice, account_mode=account_mode).copy()
    for column in ["Current Value", "Trade Value"]:
        if column in rebalance.columns:
            rebalance[column] = rebalance[column].map(_format_two_decimals)
    return rebalance


def _refresh_dashboard(account_mode: str) -> tuple[str, object, object, object, object]:
    return (
        _mode_banner(account_mode),
        dashboard_summary(account_mode=account_mode),
        _dashboard_positions(account_mode=account_mode),
        allocation_by_asset_class(account_mode=account_mode),
        allocation_by_currency(account_mode=account_mode),
    )


def _refresh_tax_report(tax_year: str, account_mode: str) -> object:
    return _tax_report_table(tax_year, account_mode)


def _refresh_performance(account_mode: str) -> object:
    return twr_curve(account_mode=account_mode)


def _refresh_benchmark_overlay(benchmark_choice: str, account_mode: str) -> object:
    return benchmark_overlay(benchmark_choice, account_mode=account_mode)


def _refresh_tax_prep_report(tax_year: str, account_mode: str) -> object:
    return _tax_prep_table(tax_year, account_mode)


def _export_tax_prep_report(tax_year: str, account_mode: str) -> str:
    clean_year = (tax_year or "").strip()
    return export_tax_prep_report_csv(
        tax_year=int(clean_year) if clean_year else None,
        account_mode=account_mode,
    )


def _set_target_allocation(
    account_choice: str,
    asset_class: str,
    target_weight_percent: str,
    account_mode: str,
) -> tuple[str, object, object]:
    try:
        status = create_target_allocation(
            account_choice=account_choice,
            asset_class=asset_class,
            target_weight_percent=target_weight_percent,
        )
    except Exception as exc:
        status = f"Could not set target allocation: {exc}"
    return (
        status,
        target_allocations(account_choice),
        _rebalance_positions(account_choice, account_mode=account_mode),
    )


def _refresh_rebalance(account_choice: str, account_mode: str) -> tuple[object, object]:
    return (
        target_allocations(account_choice),
        _rebalance_positions(account_choice, account_mode=account_mode),
    )


def _mode_changed(account_mode: str, tax_year: str) -> tuple[object, ...]:
    dashboard_values = _refresh_dashboard(account_mode)
    return (
        *dashboard_values,
        _refresh_performance(account_mode),
        _refresh_tax_report(tax_year, account_mode),
    )


def _create_account_callback(
    broker_name: str,
    account_name: str,
    currency_code: str,
    description: str,
    tax_wrapper_type: str,
    is_simulated: bool,
) -> tuple[str, object, object, object, object, object, object]:
    try:
        status = create_account(
            broker_name=broker_name,
            account_name=account_name,
            currency_code=currency_code,
            description=description,
            tax_wrapper_type=tax_wrapper_type,
            is_simulated=is_simulated,
        )
    except Exception as exc:
        return (
            f"Could not create account: {exc}",
            gr.update(),
            gr.update(),
            gr.update(),
            gr.update(),
            list_brokers(),
            list_accounts(),
        )

    accounts = account_choices(include_simulated=True)
    selected_account = next(
        (choice for choice in accounts if f"/ {account_name}" in choice),
        accounts[0] if accounts else None,
    )
    return (
        status,
        gr.update(choices=accounts, value=selected_account),
        gr.update(choices=accounts, value=selected_account),
        gr.update(choices=accounts, value=selected_account),
        gr.update(choices=[], value=None),
        list_brokers(),
        list_accounts(),
    )


def _load_account_description(account_choice: str) -> str:
    return account_description(account_choice)


def _update_account_description_callback(
    account_choice: str,
    description: str,
) -> tuple[str, object]:
    try:
        status = update_account_description(account_choice, description)
    except Exception as exc:
        status = f"Could not update account description: {exc}"
    return status, list_accounts()


def _create_portfolio_callback(
    account_choice: str,
    portfolio_name: str,
    description: str,
) -> tuple[str, object, object, object, object]:
    try:
        status = create_portfolio(
            account_choice=account_choice,
            portfolio_name=portfolio_name,
            description=description,
        )
    except Exception as exc:
        return (
            f"Could not create portfolio: {exc}",
            gr.update(),
            gr.update(),
            gr.update(),
            list_portfolios(),
        )

    accounts = account_choices(include_simulated=True)
    portfolios = portfolio_choices_for_account(account_choice)
    selected_portfolio = next(
        (choice for choice in portfolios if f"| {portfolio_name}" in choice),
        portfolios[0] if portfolios else None,
    )
    return (
        status,
        gr.update(choices=accounts, value=account_choice),
        gr.update(choices=accounts, value=account_choice),
        gr.update(choices=portfolios, value=selected_portfolio),
        list_portfolios(),
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
) -> tuple[str, object]:
    if not portfolio_choice:
        return "Choose a portfolio before adding a transaction.", _transactions_table()

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
        return status, _transactions_table()
    except Exception as exc:
        return f"Could not add transaction: {exc}", _transactions_table()


def _transfer_cash_between_accounts(
    source_account_choice: str,
    target_account_choice: str,
    amount: str,
    transfer_date: str,
    transfer_description: str,
) -> tuple[str, object]:
    try:
        status = transfer_cash(
            source_account_choice=source_account_choice,
            target_account_choice=target_account_choice,
            amount=amount,
            transfer_date=transfer_date,
            description=transfer_description,
        )
        return status, _transactions_table()
    except Exception as exc:
        return f"Could not transfer cash: {exc}", _transactions_table()


def _import_csv_to_portfolio(file: object, portfolio_choice: str) -> tuple[str, object]:
    if file is None:
        return "Choose a CSV file to import.", _transactions_table()

    try:
        file_path = getattr(file, "name", file)
        status = import_transactions_from_csv(file_path, portfolio_id=portfolio_choice)
        return status, _transactions_table()
    except Exception as exc:
        return f"Could not import CSV: {exc}", _transactions_table()


def build_app() -> gr.Blocks:
    settings = load_settings()
    selected_account = default_account_choice()
    selected_portfolio = default_portfolio_choice(selected_account)
    selected_rebalance_account = default_rebalance_account_choice()
    selected_benchmark = default_benchmark_choice()

    with gr.Blocks(title="Portfolio Management") as app:
        gr.Markdown("# Portfolio Management")
        mode_toggle = gr.Radio(
            label="Mode",
            choices=[LIVE_MODE, SANDBOX_MODE],
            value=LIVE_MODE,
        )
        mode_banner = gr.HTML(value=_mode_banner(LIVE_MODE))

        with gr.Tab("Dashboard"):
            summary_table = gr.Dataframe(
                value=lambda: dashboard_summary(account_mode=LIVE_MODE),
                headers=["Metric", "Value"],
                datatype=["str", "str"],
                label="Summary",
                interactive=False,
            )
            positions_table = gr.Dataframe(
                value=lambda: _dashboard_positions(account_mode=LIVE_MODE),
                headers=[
                    "Broker",
                    "Account",
                    "Portfolio",
                    "Ticker",
                    "Name",
                    "Asset Class",
                    "Currency",
                    "Quantity",
                    "Average Cost",
                    "Latest Price",
                    "Market Value",
                    "Unrealized P&L",
                ],
                datatype=[
                    "str",
                    "str",
                    "str",
                    "str",
                    "str",
                    "str",
                    "str",
                    "str",
                    "str",
                    "str",
                    "str",
                    "str",
                ],
                label="Current Positions",
                interactive=False,
            )
            with gr.Row():
                asset_allocation_plot = gr.BarPlot(
                    value=lambda: allocation_by_asset_class(account_mode=LIVE_MODE),
                    x="Asset Class",
                    y="Market Value",
                    title="Allocation by Asset Class",
                    y_title="Market Value",
                )
                currency_allocation_plot = gr.BarPlot(
                    value=lambda: allocation_by_currency(account_mode=LIVE_MODE),
                    x="Currency",
                    y="Market Value",
                    title="Allocation by Currency",
                    y_title="Market Value",
                )
            refresh_dashboard_button = gr.Button("Refresh Dashboard")
            refresh_dashboard_button.click(
                fn=_refresh_dashboard,
                inputs=[mode_toggle],
                outputs=[
                    mode_banner,
                    summary_table,
                    positions_table,
                    asset_allocation_plot,
                    currency_allocation_plot,
                ],
            )

        with gr.Tab("Rebalance"):
            rebalance_status = gr.Textbox(label="Status", interactive=False)
            with gr.Row():
                rebalance_account = gr.Dropdown(
                    label="Account",
                    choices=account_choices(include_simulated=True),
                    value=selected_rebalance_account,
                )
                rebalance_asset_class = gr.Dropdown(
                    label="Target Asset Class",
                    choices=[asset_class.value for asset_class in AssetClass],
                    value=AssetClass.EQUITY.value,
                )
                target_weight_percent = gr.Textbox(label="Target %", value="60")
            set_target_button = gr.Button("Set Target Allocation", variant="primary")
            target_allocations_table = gr.Dataframe(
                value=lambda: target_allocations(selected_rebalance_account),
                headers=["Asset Class", "Target %"],
                datatype=["str", "str"],
                label="Target Allocations",
                interactive=False,
            )
            rebalance_table = gr.Dataframe(
                value=lambda: _rebalance_positions(
                    selected_rebalance_account,
                    account_mode=LIVE_MODE,
                ),
                headers=[
                    "Asset Class",
                    "Current Value",
                    "Actual %",
                    "Target %",
                    "Drift %",
                    "Action",
                    "Trade Value",
                ],
                datatype=["str", "str", "str", "str", "str", "str", "str"],
                label="Rebalance Suggestions",
                interactive=False,
            )
            refresh_rebalance_button = gr.Button("Refresh Rebalance")
            set_target_button.click(
                fn=_set_target_allocation,
                inputs=[
                    rebalance_account,
                    rebalance_asset_class,
                    target_weight_percent,
                    mode_toggle,
                ],
                outputs=[rebalance_status, target_allocations_table, rebalance_table],
            )
            refresh_rebalance_button.click(
                fn=_refresh_rebalance,
                inputs=[rebalance_account, mode_toggle],
                outputs=[target_allocations_table, rebalance_table],
            )
            rebalance_account.change(
                fn=_refresh_rebalance,
                inputs=[rebalance_account, mode_toggle],
                outputs=[target_allocations_table, rebalance_table],
            )

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

        with gr.Tab("Accounts"):
            account_status = gr.Textbox(label="Status", interactive=False)

            with gr.Row():
                broker_name = gr.Textbox(label="Broker", value="Default Broker")
                account_name = gr.Textbox(label="Account", value="Default Account")
                account_currency_code = gr.Textbox(label="Account Currency", value="USD")
            new_account_description = gr.Textbox(label="Description", lines=3)
            with gr.Row():
                tax_wrapper_type = gr.Textbox(label="Tax Wrapper", placeholder="ISA, SIPP, Taxable")
                is_simulated = gr.Checkbox(label="Simulation / Paper Trading account")
            create_account_button = gr.Button("Create Account", variant="primary")
            edit_account_choice = gr.Dropdown(
                label="Edit Account",
                choices=account_choices(include_simulated=True),
                value=selected_account,
            )
            edit_account_description = gr.Textbox(
                label="Edit Description",
                value=account_description(selected_account),
                lines=3,
            )
            save_account_description_button = gr.Button("Save Description")
            accounts_table = gr.Dataframe(
                value=list_accounts,
                headers=[
                    "ID",
                    "Broker",
                    "Account",
                    "Description",
                    "Currency",
                    "Tax Wrapper",
                    "Simulated",
                ],
                datatype=["number", "str", "str", "str", "str", "str", "str"],
                label="Accounts",
                interactive=False,
            )
            refresh_accounts_button = gr.Button("Refresh Accounts")
            refresh_accounts_button.click(fn=list_accounts, outputs=[accounts_table])
            edit_account_choice.change(
                fn=_load_account_description,
                inputs=[edit_account_choice],
                outputs=[edit_account_description],
            )
            save_account_description_button.click(
                fn=_update_account_description_callback,
                inputs=[edit_account_choice, edit_account_description],
                outputs=[account_status, accounts_table],
            )

        with gr.Tab("Portfolios"):
            portfolio_status = gr.Textbox(label="Status", interactive=False)

            with gr.Row():
                portfolio_account_choice = gr.Dropdown(
                    label="Account",
                    choices=account_choices(include_simulated=True),
                    value=selected_account,
                )
                new_portfolio_name = gr.Textbox(label="Portfolio", value="Default Portfolio")
            new_portfolio_description = gr.Textbox(label="Description", lines=3)
            create_portfolio_button = gr.Button("Create Portfolio", variant="primary")
            portfolios_table = gr.Dataframe(
                value=list_portfolios,
                headers=[
                    "ID",
                    "Broker",
                    "Account",
                    "Portfolio",
                    "Description",
                    "Currency",
                    "Simulated Account",
                ],
                datatype=["number", "str", "str", "str", "str", "str", "str"],
                label="Portfolios",
                interactive=False,
            )
            refresh_portfolios_button = gr.Button("Refresh Portfolios")
            refresh_portfolios_button.click(fn=list_portfolios, outputs=[portfolios_table])

        with gr.Tab("Data Entry"):
            status = gr.Textbox(label="Status", interactive=False)

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
                    choices=[transaction_type.value for transaction_type in TransactionType],
                    value=TransactionType.BUY.value,
                )
                ticker = gr.Textbox(label="Ticker", placeholder="AAPL")
            transaction_description = gr.Textbox(label="Description", lines=2)

            with gr.Row():
                security_name = gr.Textbox(label="Security Name")
                asset_class = gr.Dropdown(
                    label="Asset Class",
                    choices=[asset_class.value for asset_class in AssetClass],
                    value=AssetClass.EQUITY.value,
                )
                security_currency_code = gr.Textbox(label="Security Currency", value="USD")

            with gr.Row():
                quantity = gr.Textbox(label="Quantity", value="0")
                price = gr.Textbox(label="Price", value="0")
                fees = gr.Textbox(label="Fees", value="0")

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

            transactions = gr.Dataframe(
                value=_transactions_table,
                headers=[
                    "ID",
                    "Date",
                    "Broker",
                    "Account",
                    "Portfolio",
                    "Ticker",
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
                    "date",
                    "str",
                    "str",
                    "str",
                    "str",
                    "str",
                    "str",
                    "str",
                    "str",
                    "str",
                    "str",
                ],
                label="Transactions",
                interactive=False,
                show_fullscreen_button=True,
            )

            create_account_button.click(
                fn=_create_account_callback,
                inputs=[
                    broker_name,
                    account_name,
                    account_currency_code,
                    new_account_description,
                    tax_wrapper_type,
                    is_simulated,
                ],
                outputs=[
                    account_status,
                    portfolio_account_choice,
                    account_choice,
                    edit_account_choice,
                    portfolio_choice,
                    brokers_table,
                    accounts_table,
                ],
            )
            create_portfolio_button.click(
                fn=_create_portfolio_callback,
                inputs=[
                    portfolio_account_choice,
                    new_portfolio_name,
                    new_portfolio_description,
                ],
                outputs=[
                    portfolio_status,
                    portfolio_account_choice,
                    account_choice,
                    portfolio_choice,
                    portfolios_table,
                ],
            )
            account_choice.change(
                fn=_update_portfolios,
                inputs=[account_choice],
                outputs=[portfolio_choice],
            )
            add_button.click(
                fn=_add_manual_transaction,
                inputs=[
                    portfolio_choice,
                    date,
                    transaction_type,
                    transaction_description,
                    ticker,
                    security_name,
                    asset_class,
                    security_currency_code,
                    quantity,
                    price,
                    fees,
                    total_value,
                    currency_exchange_rate,
                ],
                outputs=[status, transactions],
            )
            transfer_cash_button.click(
                fn=_transfer_cash_between_accounts,
                inputs=[
                    transfer_source_account,
                    transfer_target_account,
                    transfer_amount,
                    date,
                    transfer_description,
                ],
                outputs=[status, transactions],
            )
            import_button.click(
                fn=_import_csv_to_portfolio,
                inputs=[csv_file, portfolio_choice],
                outputs=[status, transactions],
            )

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

        with gr.Tab("Performance"):
            performance_plot = gr.LinePlot(
                value=lambda: twr_curve(account_mode=LIVE_MODE),
                x="Date",
                y="TWR",
                label="Time-Weighted Return",
            )
            refresh_performance_button = gr.Button("Refresh Performance")
            refresh_performance_button.click(
                fn=_refresh_performance,
                inputs=[mode_toggle],
                outputs=[performance_plot],
            )
            with gr.Row():
                benchmark_choice = gr.Dropdown(
                    label="Benchmark",
                    choices=benchmark_choices(),
                    value=selected_benchmark,
                )
                refresh_benchmark_button = gr.Button("Refresh Benchmark Overlay")
            benchmark_overlay_plot = gr.LinePlot(
                value=lambda: benchmark_overlay(None, account_mode=LIVE_MODE),
                x="Date",
                y="Index",
                color="Series",
                label="Portfolio vs Benchmark",
            )
            refresh_benchmark_button.click(
                fn=_refresh_benchmark_overlay,
                inputs=[benchmark_choice, mode_toggle],
                outputs=[benchmark_overlay_plot],
            )

        with gr.Tab("Tax"):
            tax_year = gr.Textbox(label="Tax Year", placeholder="YYYY")
            tax_report = gr.Dataframe(
                value=lambda: _tax_report_table("", LIVE_MODE),
                headers=[
                    "Date",
                    "Broker",
                    "Account",
                    "Portfolio",
                    "Ticker",
                    "Quantity Sold",
                    "Proceeds",
                    "Cost Basis",
                    "Realized P&L",
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
                    "Type",
                    "Date",
                    "Broker",
                    "Account",
                    "Portfolio",
                    "Ticker",
                    "Amount",
                    "Cost Basis",
                    "Realized P&L",
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

        with gr.Tab("Settings"):
            gr.Textbox(
                label="Database path",
                value=str(settings.database_path),
                interactive=False,
            )

        mode_toggle.change(
            fn=_mode_changed,
            inputs=[mode_toggle, tax_year],
            outputs=[
                mode_banner,
                summary_table,
                positions_table,
                asset_allocation_plot,
                currency_allocation_plot,
                performance_plot,
                tax_report,
            ],
        )

    return app


def main() -> None:
    initialize_database()
    build_app().launch()


if __name__ == "__main__":
    main()
