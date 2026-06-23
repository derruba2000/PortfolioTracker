from __future__ import annotations

from typing import Any

import gradio as gr

from portfolio_management.services.analytics import LIVE_MODE, twr_curve
from portfolio_management.services.benchmarks import (
    benchmark_choices,
    benchmark_overlay,
    default_benchmark_choice,
)


def _refresh_performance(account_mode: str) -> object:
    return twr_curve(account_mode=account_mode)


def _refresh_benchmark_overlay(benchmark_choice: str, account_mode: str) -> object:
    return benchmark_overlay(benchmark_choice, account_mode=account_mode)


def build_performance_tab(mode_toggle: gr.Radio) -> dict[str, Any]:
    selected_benchmark = default_benchmark_choice()

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

    return {"performance_plot": performance_plot}
