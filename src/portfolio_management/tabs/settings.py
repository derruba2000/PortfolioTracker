from __future__ import annotations

from typing import Any

import gradio as gr

from portfolio_management.config import load_settings


def build_settings_tab() -> dict[str, Any]:
    settings = load_settings()

    with gr.Tab("Settings"):
        gr.Textbox(
            label="Database path",
            value=str(settings.database_path),
            interactive=False,
        )

    return {}
