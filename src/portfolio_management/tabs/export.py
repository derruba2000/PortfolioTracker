from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import gradio as gr

from portfolio_management.config import load_settings, save_settings
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


def build_export_tab() -> dict[str, Any]:
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
        "prices_path": prices_path,
        "fx_path": fx_path,
        "import_status": import_status,
        "refresh_paths_button": refresh_paths_button,
        "save_paths_button": save_paths_button,
        "import_button": import_button,
    }
