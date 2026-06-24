from __future__ import annotations

from typing import Any

import gradio as gr
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from portfolio_management.services.analytics import LIVE_MODE
from portfolio_management.services.analysis_filters import (
    ACCOUNT_SCOPE_CHOICES,
    ALL_PORTFOLIOS,
    parse_portfolio_filter,
    portfolio_filter_choices,
)
from portfolio_management.services.benchmarks import (
    benchmark_choices,
    benchmark_overlay,
    default_benchmark_choice,
)
from portfolio_management.services.performance import (
    benchmark_metrics,
    calculate_mwr,
    calculate_twr,
    correlation_matrix,
    drawdown_curve,
    historical_stress_tests,
    performance_dataset,
    risk_metrics,
)

REPORTING_CURRENCIES = ["GBP", "EUR", "USD"]


def _refresh_performance(account_mode: str) -> object:
    values, flows, _ = performance_dataset(account_mode, "GBP")
    return _returns_figure(calculate_twr(values, flows), calculate_mwr(values, flows))


def refresh_performance_for_mode(account_mode: str) -> tuple[object, ...]:
    choices = portfolio_filter_choices(account_mode)
    return (
        gr.update(choices=choices, value=ALL_PORTFOLIOS),
        *refresh_performance_analysis(
            default_benchmark_choice(),
            account_mode,
            ALL_PORTFOLIOS,
            "GBP",
            4.0,
        ),
    )


def _refresh_benchmark_overlay(benchmark_choice: str, account_mode: str) -> object:
    overlay = benchmark_overlay(benchmark_choice, account_mode=account_mode)
    return _benchmark_figure(overlay)


def refresh_performance_analysis(
    benchmark_choice: str | None,
    account_mode: str,
    portfolio_choice: str | int | None,
    reporting_currency: str,
    risk_free_rate_percent: float,
) -> tuple[object, ...]:
    portfolio_id = parse_portfolio_filter(portfolio_choice)
    values, flows, prices = performance_dataset(
        account_mode,
        reporting_currency,
        portfolio_id=portfolio_id,
    )
    twr = calculate_twr(values, flows)
    mwr = calculate_mwr(values, flows)
    drawdown = drawdown_curve(values)
    overlay = benchmark_overlay(
        benchmark_choice,
        account_mode=account_mode,
        portfolio_id=portfolio_id,
    )

    portfolio_returns = _portfolio_returns(values)
    benchmark_returns = _benchmark_returns(overlay)
    risk = risk_metrics(
        portfolio_returns,
        benchmark_returns,
        float(risk_free_rate_percent or 0) / 100.0,
    )
    comparison = benchmark_metrics(portfolio_returns, benchmark_returns)
    correlations = correlation_matrix(prices)
    stress = historical_stress_tests(values)

    return (
        _returns_figure(twr, mwr),
        _drawdown_figure(drawdown),
        _metric_table(risk),
        _benchmark_figure(overlay),
        _metric_table(comparison),
        _correlation_figure(correlations),
        _stress_figure(stress),
    )


def build_performance_tab(_mode_toggle: gr.Radio) -> dict[str, Any]:
    selected_benchmark = default_benchmark_choice()

    with gr.Tab("Performance"):
        with gr.Row():
            account_scope = gr.Radio(
                label="Account Scope",
                choices=ACCOUNT_SCOPE_CHOICES,
                value=LIVE_MODE,
            )
            portfolio_filter = gr.Dropdown(
                label="Portfolio",
                choices=portfolio_filter_choices(LIVE_MODE),
                value=ALL_PORTFOLIOS,
                allow_custom_value=False,
            )
            reporting_currency = gr.Dropdown(
                label="Reporting Currency",
                choices=REPORTING_CURRENCIES,
                value="GBP",
                allow_custom_value=False,
            )
            risk_free_rate = gr.Number(
                label="Annual Risk-Free Rate (%)",
                value=4.0,
                minimum=0,
            )
            refresh_button = gr.Button("Refresh Performance", variant="primary")

        with gr.Tabs():
            with gr.Tab("Returns & Risk"):
                performance_plot = gr.Plot(
                    value=lambda: _refresh_performance(LIVE_MODE),
                    label="TWR and MWR",
                )
                drawdown_plot = gr.Plot(
                    value=lambda: _empty_figure("Portfolio Drawdown"),
                    label="Underwater Chart",
                )
                risk_metrics_table = gr.Dataframe(
                    headers=["Metric", "Value"],
                    datatype=["str", "str"],
                    value=lambda: _metric_table({}),
                    label="Risk Metrics",
                    interactive=False,
                )

            with gr.Tab("Benchmarking"):
                benchmark_choice = gr.Dropdown(
                    label="Benchmark",
                    choices=benchmark_choices(),
                    value=selected_benchmark,
                )
                benchmark_plot = gr.Plot(
                    value=lambda: _benchmark_figure(
                        benchmark_overlay(selected_benchmark, account_mode=LIVE_MODE)
                    ),
                    label="Portfolio vs Benchmark",
                )
                benchmark_metrics_table = gr.Dataframe(
                    headers=["Metric", "Value"],
                    datatype=["str", "str"],
                    value=lambda: _metric_table({}),
                    label="Benchmark Metrics",
                    interactive=False,
                )

            with gr.Tab("Advanced Analytics"):
                correlation_plot = gr.Plot(
                    value=lambda: _empty_figure("Asset Return Correlations"),
                    label="Correlation Matrix",
                )
                stress_plot = gr.Plot(
                    value=lambda: _empty_figure("Historical Stress Tests"),
                    label="Historical Stress Tests",
                )

        refresh_button.click(
            fn=refresh_performance_analysis,
            inputs=[
                benchmark_choice,
                account_scope,
                portfolio_filter,
                reporting_currency,
                risk_free_rate,
            ],
            outputs=[
                performance_plot,
                drawdown_plot,
                risk_metrics_table,
                benchmark_plot,
                benchmark_metrics_table,
                correlation_plot,
                stress_plot,
            ],
        )
        benchmark_choice.change(
            fn=refresh_performance_analysis,
            inputs=[
                benchmark_choice,
                account_scope,
                portfolio_filter,
                reporting_currency,
                risk_free_rate,
            ],
            outputs=[
                performance_plot,
                drawdown_plot,
                risk_metrics_table,
                benchmark_plot,
                benchmark_metrics_table,
                correlation_plot,
                stress_plot,
            ],
        )
        portfolio_filter.change(
            fn=refresh_performance_analysis,
            inputs=[
                benchmark_choice,
                account_scope,
                portfolio_filter,
                reporting_currency,
                risk_free_rate,
            ],
            outputs=[
                performance_plot,
                drawdown_plot,
                risk_metrics_table,
                benchmark_plot,
                benchmark_metrics_table,
                correlation_plot,
                stress_plot,
            ],
        )
        account_scope.change(
            fn=refresh_performance_for_mode,
            inputs=[account_scope],
            outputs=[
                portfolio_filter,
                performance_plot,
                drawdown_plot,
                risk_metrics_table,
                benchmark_plot,
                benchmark_metrics_table,
                correlation_plot,
                stress_plot,
            ],
        )

    return {
        "account_scope": account_scope,
        "portfolio_filter": portfolio_filter,
        "performance_plot": performance_plot,
        "drawdown_plot": drawdown_plot,
        "risk_metrics_table": risk_metrics_table,
        "benchmark_plot": benchmark_plot,
        "benchmark_metrics_table": benchmark_metrics_table,
        "correlation_plot": correlation_plot,
        "stress_plot": stress_plot,
    }


def _returns_figure(twr: pd.DataFrame, mwr: pd.DataFrame) -> go.Figure:
    figure = go.Figure()
    if not twr.empty:
        figure.add_trace(
            go.Scatter(
                x=twr["Date"],
                y=twr["TWR"] * 100,
                mode="lines",
                name="TWR",
            )
        )
    if not mwr.empty:
        figure.add_trace(
            go.Scatter(
                x=mwr["Date"],
                y=mwr["MWR"] * 100,
                mode="lines",
                name="MWR (annualized)",
                connectgaps=False,
            )
        )
    figure.update_layout(
        title="Time-Weighted vs Money-Weighted Return",
        xaxis_title="Date",
        yaxis_title="Return (%)",
        hovermode="x unified",
    )
    return figure


def _drawdown_figure(drawdown: pd.DataFrame) -> go.Figure:
    figure = go.Figure()
    if not drawdown.empty:
        figure.add_trace(
            go.Scatter(
                x=drawdown["Date"],
                y=drawdown["Drawdown"] * 100,
                fill="tozeroy",
                mode="lines",
                name="Drawdown",
                line={"color": "#ef4444"},
            )
        )
    figure.update_layout(
        title="Portfolio Underwater Chart",
        xaxis_title="Date",
        yaxis_title="Drawdown (%)",
        hovermode="x unified",
    )
    return figure


def _benchmark_figure(overlay: pd.DataFrame) -> go.Figure:
    if overlay.empty:
        return _empty_figure("Portfolio vs Benchmark")
    return px.line(
        overlay,
        x="Date",
        y="Index",
        color="Series",
        title="Growth of 100: Portfolio vs Benchmark",
        labels={"Index": "Growth Index"},
    )


def _correlation_figure(correlations: pd.DataFrame) -> go.Figure:
    if correlations.empty:
        return _empty_figure("Asset Return Correlations")
    return go.Figure(
        data=go.Heatmap(
            z=correlations.values,
            x=correlations.columns,
            y=correlations.index,
            zmin=-1,
            zmax=1,
            colorscale="RdBu",
            reversescale=True,
            text=np.round(correlations.values, 2),
            texttemplate="%{text}",
        ),
        layout=go.Layout(title="Asset Return Correlation Matrix"),
    )


def _stress_figure(stress: pd.DataFrame) -> go.Figure:
    available = stress.dropna(subset=["Return"]).copy()
    if available.empty:
        return _empty_figure("Historical Stress Tests — no overlapping price history")
    available["Return"] *= 100
    return px.bar(
        available,
        x="Period",
        y="Return",
        title="Portfolio Performance During Historical Stress Periods",
        labels={"Return": "Return (%)"},
        color="Return",
        color_continuous_scale="RdYlGn",
    )


def _metric_table(metrics: dict[str, float]) -> pd.DataFrame:
    records = []
    for name, value in metrics.items():
        display = "N/A" if value is None or np.isnan(value) else f"{value:.4f}"
        records.append({"Metric": name, "Value": display})
    return pd.DataFrame(records, columns=["Metric", "Value"])


def _portfolio_returns(values: pd.DataFrame) -> pd.Series:
    if values.empty:
        return pd.Series(dtype=float)
    frame = values.copy()
    frame["Date"] = pd.to_datetime(frame["Date"])
    return frame.set_index("Date")["Portfolio Value"].pct_change(fill_method=None).dropna()


def _benchmark_returns(overlay: pd.DataFrame) -> pd.Series:
    if overlay.empty:
        return pd.Series(dtype=float)
    benchmark = overlay[overlay["Series"] == "Benchmark"].copy()
    if benchmark.empty:
        return pd.Series(dtype=float)
    benchmark["Date"] = pd.to_datetime(benchmark["Date"])
    return benchmark.set_index("Date")["Index"].pct_change(fill_method=None).dropna()


def _empty_figure(title: str) -> go.Figure:
    figure = go.Figure()
    figure.update_layout(title=title)
    return figure
