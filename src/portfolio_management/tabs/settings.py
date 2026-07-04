from __future__ import annotations

from typing import Any

import gradio as gr
import pandas as pd

from portfolio_management.config import DEFAULT_THEME_NAME, load_settings, save_settings
from portfolio_management.services.accounts import (
    delete_portfolios_with_transactions,
    list_portfolios_with_transactions,
)


THEME_CHOICES = ["Base", "Soft", "Monochrome", "Glass", "Ocean"]
API_PROVIDER_CHOICES = ["OLLAMA", "NVIDIA"]


def _save_theme(theme_name: str) -> str:
    updated = save_settings(theme_name=theme_name)
    return f"Saved theme '{updated.theme_name}'. Reloading now."


def _save_market_data_paths(prices_path: str, fx_path: str) -> str:
    updated = save_settings(
        market_prices_delta_path=prices_path.strip() or None,
        fx_rates_delta_path=fx_path.strip() or None,
    )
    prices = updated.market_prices_delta_path or "(not set)"
    fx_rates = updated.fx_rates_delta_path or "(not set)"
    return f"Saved market prices path: {prices}\nSaved FX rates path: {fx_rates}"


def _save_discord_webhook(webhook_url: str) -> str:
    try:
        updated = save_settings(discord_webhook_url=webhook_url.strip() or None)
    except ValueError as exc:
        return str(exc)
    if updated.discord_webhook_url:
        return "Saved Discord webhook securely."
    return "Cleared Discord webhook."


def _save_llm_provider(api_usage: str) -> str:
    updated = save_settings(api_usage=api_usage)
    return f"Saved AI provider: {updated.api_usage}."


def _save_ollama_settings(model: str, base_url: str, timeout_seconds: int | float | str) -> str:
    updated = save_settings(
        ollama_model=model,
        ollama_base_url=base_url,
        ollama_timeout_seconds=timeout_seconds,
    )
    return (
        f"Saved Ollama settings: {updated.ollama_model} at "
        f"{updated.ollama_base_url}."
    )


def _save_nvidia_settings(
    model: str,
    base_url: str,
    verify_ssl: bool,
    api_key: str,
) -> str:
    updated = save_settings(
        nvidia_api_model=model,
        nvidia_base_url=base_url,
        nvidia_verify_ssl=verify_ssl,
        nvidia_api_key=api_key.strip() or None,
    )
    key_status = "saved" if updated.nvidia_api_key else "cleared"
    return f"Saved NVIDIA NIM settings: {updated.nvidia_api_model}. API key {key_status}."


def _toggle_secret_visibility(visible: bool) -> tuple[bool, object, str]:
    next_visible = not visible
    field_type = "text" if next_visible else "password"
    label = "Hide" if next_visible else "Show"
    return next_visible, gr.update(type=field_type), label


def _preview_portfolios_to_delete() -> tuple[object, str, object]:
    df = list_portfolios_with_transactions()
    if df.empty:
        return (
            df,
            "No empty portfolios found — nothing to delete.",
            gr.update(visible=False),
        )
    count = len(df)
    return (
        df,
        f"Found {count} portfolio(s) with no transactions. Review the list below, then click Confirm Delete to permanently remove them.",
        gr.update(visible=True),
    )


def _confirm_delete_portfolios() -> tuple[object, str, object]:
    portfolios_deleted, _ = delete_portfolios_with_transactions()
    if portfolios_deleted == 0:
        msg = "No portfolios were deleted."
    else:
        msg = f"Deleted {portfolios_deleted} empty portfolio(s)."
    empty_df = pd.DataFrame(columns=["ID", "Broker", "Account", "Portfolio", "Active"])
    return empty_df, msg, gr.update(visible=False)


def build_settings_tab() -> dict[str, Any]:
    settings = load_settings()

    with gr.Tab("Settings"):
        with gr.Tabs():
            with gr.Tab("General"):
                gr.Textbox(
                    label="Database path",
                    value=str(settings.database_path),
                    interactive=False,
                )
                theme_status = gr.Textbox(label="Theme Status", interactive=False)
                theme_choice = gr.Dropdown(
                    label="Color Theme",
                    choices=THEME_CHOICES,
                    value=settings.theme_name
                    if settings.theme_name in THEME_CHOICES
                    else DEFAULT_THEME_NAME,
                    allow_custom_value=False,
                )
                save_theme_button = gr.Button("Save Theme", variant="primary")
                save_theme_button.click(
                    fn=_save_theme,
                    inputs=[theme_choice],
                    outputs=[theme_status],
                ).then(
                    fn=None,
                    inputs=[theme_choice],
                    js=(
                        "(theme) => {"
                        "const classes=['theme-base','theme-soft','theme-monochrome','theme-glass','theme-ocean'];"
                        "const key='portfolio_tracker_theme';"
                        "const normalized=String(theme || 'soft').toLowerCase();"
                        "localStorage.setItem(key, normalized);"
                        "document.documentElement.classList.remove(...classes);"
                        "const next='theme-' + normalized;"
                        "document.documentElement.classList.add(next);"
                        "window.setTimeout(() => window.location.reload(), 150);"
                        "}"
                    ),
                )

            with gr.Tab("Notifications"):
                discord_webhook_url = gr.Textbox(
                    label="Discord Webhook URL",
                    value=settings.discord_webhook_url or "",
                    type="password",
                    placeholder="https://discord.com/api/webhooks/...",
                )
                discord_visible = gr.State(False)
                with gr.Row():
                    toggle_discord_button = gr.Button("Show", variant="secondary")
                    copy_discord_button = gr.Button("Copy", variant="secondary")
                    save_discord_button = gr.Button("Save Discord Webhook", variant="primary")
                discord_status = gr.Textbox(label="Notification Status", interactive=False)
                toggle_discord_button.click(
                    fn=_toggle_secret_visibility,
                    inputs=[discord_visible],
                    outputs=[discord_visible, discord_webhook_url, toggle_discord_button],
                )
                copy_discord_button.click(
                    fn=None,
                    inputs=[discord_webhook_url],
                    js="(value) => navigator.clipboard.writeText(value || '')",
                )
                save_discord_button.click(
                    fn=_save_discord_webhook,
                    inputs=[discord_webhook_url],
                    outputs=[discord_status],
                )

            with gr.Tab("AI APIs"):
                llm_provider_status = gr.Textbox(label="Provider Status", interactive=False)
                api_usage = gr.Radio(
                    label="AI Provider",
                    choices=API_PROVIDER_CHOICES,
                    value=settings.api_usage,
                )
                save_llm_provider_button = gr.Button("Save AI Provider", variant="primary")
                save_llm_provider_button.click(
                    fn=_save_llm_provider,
                    inputs=[api_usage],
                    outputs=[llm_provider_status],
                )

                with gr.Tabs():
                    with gr.Tab("Ollama"):
                        ollama_model = gr.Textbox(
                            label="Ollama Model",
                            value=settings.ollama_model,
                        )
                        ollama_base_url = gr.Textbox(
                            label="Ollama Base URL",
                            value=settings.ollama_base_url,
                        )
                        ollama_timeout_seconds = gr.Number(
                            label="Timeout Seconds",
                            value=settings.ollama_timeout_seconds,
                            precision=0,
                        )
                        ollama_status = gr.Textbox(label="Ollama Status", interactive=False)
                        save_ollama_button = gr.Button("Save Ollama Settings", variant="primary")
                        save_ollama_button.click(
                            fn=_save_ollama_settings,
                            inputs=[ollama_model, ollama_base_url, ollama_timeout_seconds],
                            outputs=[ollama_status],
                        )

                    with gr.Tab("NVIDIA NIM"):
                        nvidia_api_model = gr.Textbox(
                            label="NVIDIA NIM Model",
                            value=settings.nvidia_api_model,
                        )
                        nvidia_base_url = gr.Textbox(
                            label="NVIDIA Base URL",
                            value=settings.nvidia_base_url,
                        )
                        nvidia_verify_ssl = gr.Checkbox(
                            label="Verify SSL",
                            value=settings.nvidia_verify_ssl,
                        )
                        nvidia_api_key = gr.Textbox(
                            label="NVIDIA API Key",
                            value=settings.nvidia_api_key or "",
                            type="password",
                        )
                        nvidia_visible = gr.State(False)
                        with gr.Row():
                            toggle_nvidia_button = gr.Button("Show", variant="secondary")
                            copy_nvidia_button = gr.Button("Copy", variant="secondary")
                            save_nvidia_button = gr.Button(
                                "Save NVIDIA Settings",
                                variant="primary",
                            )
                        nvidia_status = gr.Textbox(label="NVIDIA Status", interactive=False)
                        toggle_nvidia_button.click(
                            fn=_toggle_secret_visibility,
                            inputs=[nvidia_visible],
                            outputs=[nvidia_visible, nvidia_api_key, toggle_nvidia_button],
                        )
                        copy_nvidia_button.click(
                            fn=None,
                            inputs=[nvidia_api_key],
                            js="(value) => navigator.clipboard.writeText(value || '')",
                        )
                        save_nvidia_button.click(
                            fn=_save_nvidia_settings,
                            inputs=[
                                nvidia_api_model,
                                nvidia_base_url,
                                nvidia_verify_ssl,
                                nvidia_api_key,
                            ],
                            outputs=[nvidia_status],
                        )

            with gr.Tab("Market Data"):
                gr.Markdown(
                    "Paths may point to local Delta tables or supported object-storage Delta table URIs."
                )
                market_prices_delta_path = gr.Textbox(
                    label="Market Prices Delta Table Path",
                    value=str(settings.market_prices_delta_path or ""),
                    placeholder="/path/to/market_prices_delta",
                )
                fx_rates_delta_path = gr.Textbox(
                    label="FX Rates Delta Table Path",
                    value=str(settings.fx_rates_delta_path or ""),
                    placeholder="/path/to/fx_rates_delta",
                )
                market_data_paths_status = gr.Textbox(
                    label="Import Path Status",
                    interactive=False,
                )
                save_market_data_paths_button = gr.Button(
                    "Save Market Data Paths",
                    variant="primary",
                )
                save_market_data_paths_button.click(
                    fn=_save_market_data_paths,
                    inputs=[market_prices_delta_path, fx_rates_delta_path],
                    outputs=[market_data_paths_status],
                )

            with gr.Tab("Data Management"):
                delete_status = gr.Textbox(label="Status", interactive=False)
                preview_delete_button = gr.Button(
                    "List portfolios with no transactions",
                    variant="secondary",
                )
                portfolios_to_delete_table = gr.Dataframe(
                    headers=["ID", "Broker", "Account", "Portfolio", "Active"],
                    datatype=["number", "str", "str", "str", "str"],
                    label="Portfolios to be deleted",
                    interactive=False,
                    visible=True,
                    value=pd.DataFrame(
                        columns=["ID", "Broker", "Account", "Portfolio", "Active"]
                    ),
                )
                confirm_delete_button = gr.Button(
                    "Confirm Delete",
                    variant="stop",
                    visible=False,
                )

                preview_delete_button.click(
                    fn=_preview_portfolios_to_delete,
                    outputs=[portfolios_to_delete_table, delete_status, confirm_delete_button],
                )
                confirm_delete_button.click(
                    fn=_confirm_delete_portfolios,
                    outputs=[portfolios_to_delete_table, delete_status, confirm_delete_button],
                )

    return {
        "theme_choice": theme_choice,
        "theme_status": theme_status,
        "save_theme_button": save_theme_button,
        "market_prices_delta_path": market_prices_delta_path,
        "fx_rates_delta_path": fx_rates_delta_path,
        "market_data_paths_status": market_data_paths_status,
        "save_market_data_paths_button": save_market_data_paths_button,
    }
