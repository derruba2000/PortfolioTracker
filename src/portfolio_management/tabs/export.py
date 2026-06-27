from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import gradio as gr

from portfolio_management.config import load_settings, save_settings
from portfolio_management.services.analysis_filters import (
    ALL_PORTFOLIOS,
    parse_portfolio_filter,
    portfolio_filter_choices,
)
from portfolio_management.services.analytics import LIVE_MODE
from portfolio_management.services.csv_exports import (
    export_portfolio_correlations_csv,
    export_portfolio_kpis_csv,
    export_portfolio_time_series_csv,
    export_positions_csv,
    export_transactions_csv,
)
from portfolio_management.services.import_errors import log_import_error
from portfolio_management.services.market_data import import_market_data_from_delta
from portfolio_management.services.securities import list_securities


def _save_symbols_csv_path(csv_path: str) -> str:
    clean = csv_path.strip()
    if not clean:
        return "CSV file path cannot be empty."
    resolved = Path(clean).expanduser()
    if resolved.suffix.lower() != ".csv":
        return "Path must end with .csv"
    try:
        resolved.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return f"Could not create parent directory: {exc}"
    save_settings(export_symbols_csv_path=resolved)
    return f"Saved symbols CSV path: {resolved}"


def _export_symbols_csv(csv_path: str) -> str:
    clean = csv_path.strip()
    if not clean:
        return "Set a CSV file path first."
    resolved = Path(clean).expanduser()
    if resolved.suffix.lower() != ".csv":
        return "Path must end with .csv"
    try:
        resolved.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return f"Could not create parent directory: {exc}"

    securities = list_securities()
    tickers = (
        securities.loc[securities["Asset Class"] != "CASH", "Ticker"]
        .dropna()
        .sort_values()
        .tolist()
    )
    if not tickers:
        return "No securities to export (excluding CASH)."

    with resolved.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["symbol"])
        for ticker in tickers:
            writer.writerow([ticker])

    return f"Exported {len(tickers)} symbol(s) to {resolved}"


def _load_market_data_paths() -> tuple[str, str, str]:
    settings = load_settings()
    prices_path = str(settings.market_prices_delta_path or "")
    fx_path = str(settings.fx_rates_delta_path or "")
    return prices_path, fx_path, "Reloaded Delta table paths from Settings."


def _save_market_data_paths(prices_path: str, fx_path: str) -> tuple[str, str, str]:
    prices_clean = prices_path.strip()
    fx_clean = fx_path.strip()
    updated = save_settings(
        market_prices_delta_path=prices_clean or None,
        fx_rates_delta_path=fx_clean or None,
    )
    saved_prices = str(updated.market_prices_delta_path or "")
    saved_fx = str(updated.fx_rates_delta_path or "")
    return saved_prices, saved_fx, "Saved both Delta table paths."


def _import_market_data(prices_path: str, fx_path: str) -> tuple[str, str, str]:
    prices_clean = prices_path.strip()
    fx_clean = fx_path.strip()
    if not prices_clean or not fx_clean:
        message = "Both the market prices and FX rates Delta table paths are required."
        log_import_error(
            pipeline_name="delta_market_data",
            error_message=message,
        )
        return (
            prices_clean,
            fx_clean,
            message,
        )

    try:
        updated = save_settings(
            market_prices_delta_path=prices_clean,
            fx_rates_delta_path=fx_clean,
        )
    except Exception as exc:
        message = f"Could not save Delta table paths: {exc}"
        log_import_error(
            pipeline_name="delta_market_data",
            error_message=message,
        )
        return prices_clean, fx_clean, message

    try:
        result = import_market_data_from_delta(
            market_prices_path=updated.market_prices_delta_path,
            fx_rates_path=updated.fx_rates_delta_path,
        )
        return (
            str(updated.market_prices_delta_path or ""),
            str(updated.fx_rates_delta_path or ""),
            f"Merge completed. {result.message}",
        )
    except Exception as exc:
        return prices_clean, fx_clean, f"Could not merge market data: {exc}"


def _export_scope_changed(account_mode: str) -> object:
    return gr.update(
        choices=portfolio_filter_choices(account_mode),
        value=ALL_PORTFOLIOS,
    )


def _export_positions(
    account_mode: str,
    portfolio_choice: str | int | None,
    reporting_currency: str,
) -> str:
    return export_positions_csv(
        account_mode=account_mode,
        reporting_currency=reporting_currency,
        portfolio_id=parse_portfolio_filter(portfolio_choice),
    )


def _export_transactions(
    account_mode: str,
    portfolio_choice: str | int | None,
) -> str:
    return export_transactions_csv(
        account_mode=account_mode,
        portfolio_id=parse_portfolio_filter(portfolio_choice),
    )


def _export_portfolio_kpis(
    account_mode: str,
    portfolio_choice: str | int | None,
    reporting_currency: str,
    risk_free_rate_percent: float,
) -> str:
    return export_portfolio_kpis_csv(
        account_mode=account_mode,
        reporting_currency=reporting_currency,
        portfolio_id=parse_portfolio_filter(portfolio_choice),
        risk_free_rate=float(risk_free_rate_percent or 0) / 100,
    )


def _export_portfolio_correlations(
    account_mode: str,
    portfolio_choice: str | int | None,
) -> str:
    return export_portfolio_correlations_csv(
        account_mode=account_mode,
        portfolio_id=parse_portfolio_filter(portfolio_choice),
    )


def _export_portfolio_time_series(
    account_mode: str,
    portfolio_choice: str | int | None,
    reporting_currency: str,
) -> str:
    return export_portfolio_time_series_csv(
        account_mode=account_mode,
        reporting_currency=reporting_currency,
        portfolio_id=parse_portfolio_filter(portfolio_choice),
    )


def build_export_tab(mode_toggle: gr.Radio) -> dict[str, Any]:
    settings = load_settings()
    default_path = str(settings.export_symbols_csv_path) if settings.export_symbols_csv_path else ""

    with gr.Tab("Import / Export"):
        with gr.Tabs():
            with gr.Tab("Export Symbols"):
                gr.Markdown(
                    "Export all tracked securities (excluding **CASH**) to a CSV file. "
                    "The CSV has a `symbol` header column followed by one ticker per row."
                )
                csv_path_input = gr.Textbox(
                    label="Symbols CSV Path",
                    value=default_path,
                    placeholder="/path/to/symbols.csv",
                )
                with gr.Row():
                    save_path_button = gr.Button("Save Path")
                    export_button = gr.Button("Export Symbols CSV", variant="primary")
                export_status = gr.Textbox(label="Status", interactive=False)

                save_path_button.click(
                    fn=_save_symbols_csv_path,
                    inputs=[csv_path_input],
                    outputs=[export_status],
                )
                export_button.click(
                    fn=_export_symbols_csv,
                    inputs=[csv_path_input],
                    outputs=[export_status],
                )
            with gr.Tab("Export Portfolio Data"):
                gr.Markdown(
                    "Export raw positions, transactions, or one-row-per-portfolio KPI "
                    "data using the same account-scope and portfolio filters. KPI exports "
                    "include separate comparison columns for every configured benchmark. "
                    "CSV values are not formatted as dashboard links or display strings."
                )
                with gr.Row():
                    export_portfolio_filter = gr.Dropdown(
                        label="Portfolio",
                        choices=portfolio_filter_choices(LIVE_MODE),
                        value=ALL_PORTFOLIOS,
                        allow_custom_value=False,
                    )
                    export_reporting_currency = gr.Dropdown(
                        label="Reporting Currency",
                        choices=["GBP", "EUR", "USD"],
                        value="GBP",
                        allow_custom_value=False,
                    )
                    export_risk_free_rate = gr.Number(
                        label="Annual Risk-Free Rate (%)",
                        value=4.0,
                        minimum=0,
                    )
                with gr.Row():
                    export_positions_button = gr.Button(
                        "Create Positions CSV",
                        variant="primary",
                    )
                    export_transactions_button = gr.Button(
                        "Create Transactions CSV",
                        variant="primary",
                    )
                    export_kpis_button = gr.Button(
                        "Create Portfolio KPIs CSV",
                        variant="primary",
                    )
                    export_correlations_button = gr.Button(
                        "Create Correlation Matrix CSV",
                        variant="primary",
                    )
                    export_time_series_button = gr.Button(
                        "Create Performance Time Series CSV",
                        variant="primary",
                    )
                with gr.Row():
                    positions_csv_file = gr.File(
                        label="Positions CSV",
                        interactive=False,
                    )
                    transactions_csv_file = gr.File(
                        label="Transactions CSV",
                        interactive=False,
                    )
                    portfolio_kpis_csv_file = gr.File(
                        label="Portfolio KPIs CSV",
                        interactive=False,
                    )
                    correlations_csv_file = gr.File(
                        label="Correlation Matrix CSV",
                        interactive=False,
                    )
                    time_series_csv_file = gr.File(
                        label="Performance Time Series CSV",
                        interactive=False,
                    )

                export_positions_button.click(
                    fn=_export_positions,
                    inputs=[
                        mode_toggle,
                        export_portfolio_filter,
                        export_reporting_currency,
                    ],
                    outputs=[positions_csv_file],
                )
                export_transactions_button.click(
                    fn=_export_transactions,
                    inputs=[mode_toggle, export_portfolio_filter],
                    outputs=[transactions_csv_file],
                )
                export_kpis_button.click(
                    fn=_export_portfolio_kpis,
                    inputs=[
                        mode_toggle,
                        export_portfolio_filter,
                        export_reporting_currency,
                        export_risk_free_rate,
                    ],
                    outputs=[portfolio_kpis_csv_file],
                )
                export_correlations_button.click(
                    fn=_export_portfolio_correlations,
                    inputs=[mode_toggle, export_portfolio_filter],
                    outputs=[correlations_csv_file],
                )
                export_time_series_button.click(
                    fn=_export_portfolio_time_series,
                    inputs=[
                        mode_toggle,
                        export_portfolio_filter,
                        export_reporting_currency,
                    ],
                    outputs=[time_series_csv_file],
                )
            with gr.Tab("Import Market Data"):
                gr.Markdown(
                    "Merge market prices and FX rates from Delta tables into the database. "
                    "Existing rows with the same symbol/date are updated; new rows are inserted. "
                    "Both tables must contain: `symbol, date, open, high, low, close, volume`."
                )
                prices_path = gr.Textbox(
                    label="Market Prices Delta Table Path",
                    value=str(settings.market_prices_delta_path or ""),
                    placeholder="/path/to/market_prices_delta",
                )
                fx_path = gr.Textbox(
                    label="FX Rates Delta Table Path",
                    value=str(settings.fx_rates_delta_path or ""),
                    placeholder="/path/to/fx_rates_delta",
                )
                with gr.Row():
                    refresh_paths_button = gr.Button("Refresh Paths from Settings")
                    save_paths_button = gr.Button("Save Paths")
                    import_button = gr.Button("Import Market Data — Merge", variant="primary")
                import_status = gr.Textbox(label="Import Status", interactive=False)
                refresh_paths_button.click(
                    fn=_load_market_data_paths,
                    outputs=[prices_path, fx_path, import_status],
                )
                save_paths_button.click(
                    fn=_save_market_data_paths,
                    inputs=[prices_path, fx_path],
                    outputs=[prices_path, fx_path, import_status],
                )
                import_button.click(
                    fn=_import_market_data,
                    inputs=[prices_path, fx_path],
                    outputs=[prices_path, fx_path, import_status],
                )

    return {
        "csv_path_input": csv_path_input,
        "export_status": export_status,
        "export_portfolio_filter": export_portfolio_filter,
        "positions_csv_file": positions_csv_file,
        "transactions_csv_file": transactions_csv_file,
        "portfolio_kpis_csv_file": portfolio_kpis_csv_file,
        "correlations_csv_file": correlations_csv_file,
        "time_series_csv_file": time_series_csv_file,
        "prices_path": prices_path,
        "fx_path": fx_path,
        "import_status": import_status,
        "refresh_paths_button": refresh_paths_button,
        "save_paths_button": save_paths_button,
        "import_button": import_button,
    }
