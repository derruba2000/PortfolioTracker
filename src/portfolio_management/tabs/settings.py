from __future__ import annotations

from typing import Any

import gradio as gr

from portfolio_management.config import DEFAULT_THEME_NAME, load_settings, save_settings


THEME_CHOICES = ["Base", "Soft", "Monochrome", "Glass", "Ocean"]


def _save_theme(theme_name: str) -> str:
    updated = save_settings(theme_name=theme_name)
    return f"Saved theme '{updated.theme_name}'. Reloading now."


def build_settings_tab() -> dict[str, Any]:
    settings = load_settings()

    with gr.Tab("Settings"):
        gr.Textbox(label="Database path", value=str(settings.database_path), interactive=False)
        theme_status = gr.Textbox(label="Theme Status", interactive=False)
        theme_choice = gr.Dropdown(
            label="Color Theme",
            choices=THEME_CHOICES,
            value=settings.theme_name if settings.theme_name in THEME_CHOICES else DEFAULT_THEME_NAME,
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

    return {
        "theme_choice": theme_choice,
        "theme_status": theme_status,
        "save_theme_button": save_theme_button,
    }
