from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import gradio as gr
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from portfolio_management.services.analytics import (
    LIVE_MODE,
)
from portfolio_management.services.analysis_filters import (
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
    start_date, end_date = _default_window(values)
    scoped_values = _filter_frame_by_date(values, start_date, end_date)
    scoped_flows = _filter_frame_by_date(flows, start_date, end_date)
    return _returns_figure(
        calculate_twr(scoped_values, scoped_flows),
        calculate_mwr(scoped_values, scoped_flows),
    )


def refresh_performance_for_mode(
    account_mode: str,
    benchmark_choice: str | None,
    reporting_currency: str,
    risk_free_rate_percent: float,
) -> tuple[object, ...]:
    choices = portfolio_filter_choices(account_mode)
    start_date, end_date, *analysis = _performance_payload(
        benchmark_choice,
        account_mode,
        ALL_PORTFOLIOS,
        reporting_currency,
        risk_free_rate_percent,
        start_date_input=None,
        end_date_input=None,
    )
    return (
        gr.update(choices=choices, value=ALL_PORTFOLIOS),
        gr.update(value=start_date),
        gr.update(value=end_date),
        *analysis,
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
    start_date_input: str | None = None,
    end_date_input: str | None = None,
) -> tuple[object, ...]:
    start_date, end_date, *analysis = _performance_payload(
        benchmark_choice,
        account_mode,
        portfolio_choice,
        reporting_currency,
        risk_free_rate_percent,
        start_date_input=start_date_input,
        end_date_input=end_date_input,
    )
    return (gr.update(value=start_date), gr.update(value=end_date), *analysis)


def _performance_payload(
    benchmark_choice: str | None,
    account_mode: str,
    portfolio_choice: str | int | None,
    reporting_currency: str,
    risk_free_rate_percent: float,
    start_date_input: str | None,
    end_date_input: str | None,
) -> tuple[object, ...]:
    portfolio_id = parse_portfolio_filter(portfolio_choice)
    values, flows, prices = performance_dataset(
        account_mode,
        reporting_currency,
        portfolio_id=portfolio_id,
    )
    start_date, end_date = _resolve_date_window(values, start_date_input, end_date_input)
    scoped_values = _filter_frame_by_date(values, start_date, end_date)
    scoped_flows = _filter_frame_by_date(flows, start_date, end_date)
    scoped_prices = _filter_frame_by_date(prices, start_date, end_date)

    twr = calculate_twr(scoped_values, scoped_flows)
    mwr = calculate_mwr(scoped_values, scoped_flows)
    drawdown = drawdown_curve(scoped_values)
    overlay = benchmark_overlay(
        benchmark_choice,
        account_mode=account_mode,
        portfolio_id=portfolio_id,
    )
    overlay = _filter_frame_by_date(overlay, start_date, end_date)

    portfolio_returns = _portfolio_returns(scoped_values)
    benchmark_returns = _benchmark_returns(overlay)
    risk = risk_metrics(
        portfolio_returns,
        benchmark_returns,
        float(risk_free_rate_percent or 0) / 100.0,
    )
    comparison = benchmark_metrics(portfolio_returns, benchmark_returns)
    correlations = correlation_matrix(scoped_prices)
    stress = historical_stress_tests(scoped_values)

    return (
        start_date.isoformat() if start_date else None,
        end_date.isoformat() if end_date else None,
        _portfolio_value_figure(scoped_values, reporting_currency, portfolio_choice),
        _returns_figure(twr, mwr),
        _drawdown_figure(drawdown),
        _metric_table(risk),
        _benchmark_figure(overlay),
        _metric_table(comparison),
        _correlation_figure(correlations),
        _stress_figure(stress),
    )


def build_performance_tab(mode_toggle: gr.Radio) -> dict[str, Any]:
    selected_benchmark = default_benchmark_choice()
    initial_start_date, initial_end_date, *initial_analysis = _performance_payload(
        selected_benchmark,
        LIVE_MODE,
        ALL_PORTFOLIOS,
        "GBP",
        4.0,
        start_date_input=None,
        end_date_input=None,
    )

    with gr.Tab("Performance"):
        with gr.Row():
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
            start_date = gr.DateTime(
                label="Start Date",
                include_time=False,
                type="string",
                value=initial_start_date,
            )
            end_date = gr.DateTime(
                label="End Date",
                include_time=False,
                type="string",
                value=initial_end_date,
            )
            refresh_button = gr.Button("Refresh Performance", variant="primary")

        with gr.Tabs():
            with gr.Tab("Value Evolution"):
                portfolio_value_plot = gr.Plot(
                    value=initial_analysis[0],
                    label="Portfolio Value Evolution",
                )

            with gr.Tab("Returns & Risk"):
                performance_plot = gr.Plot(
                    value=initial_analysis[1],
                    label="TWR and MWR",
                )
                drawdown_plot = gr.Plot(
                    value=initial_analysis[2],
                    label="Underwater Chart",
                )
                risk_metrics_table = gr.Dataframe(
                    headers=["Metric", "Value"],
                    datatype=["str", "str"],
                    value=initial_analysis[3],
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
                    value=initial_analysis[4],
                    label="Portfolio vs Benchmark",
                )
                benchmark_metrics_table = gr.Dataframe(
                    headers=["Metric", "Value"],
                    datatype=["str", "str"],
                    value=initial_analysis[5],
                    label="Benchmark Metrics",
                    interactive=False,
                )

            with gr.Tab("Advanced Analytics"):
                correlation_plot = gr.Plot(
                    value=initial_analysis[6],
                    label="Correlation Matrix",
                )
                stress_plot = gr.Plot(
                    value=initial_analysis[7],
                    label="Historical Stress Tests",
                )

        refresh_button.click(
            fn=refresh_performance_analysis,
            inputs=[
                benchmark_choice,
                mode_toggle,
                portfolio_filter,
                reporting_currency,
                risk_free_rate,
                start_date,
                end_date,
            ],
            outputs=[
                start_date,
                end_date,
                portfolio_value_plot,
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
                mode_toggle,
                portfolio_filter,
                reporting_currency,
                risk_free_rate,
                start_date,
                end_date,
            ],
            outputs=[
                start_date,
                end_date,
                portfolio_value_plot,
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
                mode_toggle,
                portfolio_filter,
                reporting_currency,
                risk_free_rate,
                start_date,
                end_date,
            ],
            outputs=[
                start_date,
                end_date,
                portfolio_value_plot,
                performance_plot,
                drawdown_plot,
                risk_metrics_table,
                benchmark_plot,
                benchmark_metrics_table,
                correlation_plot,
                stress_plot,
            ],
        )
        reporting_currency.change(
            fn=refresh_performance_analysis,
            inputs=[
                benchmark_choice,
                mode_toggle,
                portfolio_filter,
                reporting_currency,
                risk_free_rate,
                start_date,
                end_date,
            ],
            outputs=[
                start_date,
                end_date,
                portfolio_value_plot,
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
        "benchmark_choice": benchmark_choice,
        "reporting_currency": reporting_currency,
        "risk_free_rate": risk_free_rate,
        "start_date": start_date,
        "end_date": end_date,
        "portfolio_filter": portfolio_filter,
        "portfolio_value_plot": portfolio_value_plot,
        "performance_plot": performance_plot,
        "drawdown_plot": drawdown_plot,
        "risk_metrics_table": risk_metrics_table,
        "benchmark_plot": benchmark_plot,
        "benchmark_metrics_table": benchmark_metrics_table,
        "correlation_plot": correlation_plot,
        "stress_plot": stress_plot,
    }


def _portfolio_value_figure(
    values: pd.DataFrame,
    reporting_currency: str,
    portfolio_choice: str | int | None = ALL_PORTFOLIOS,
) -> go.Figure:
    currency = str(reporting_currency or "GBP").upper()
    selected_portfolio = _portfolio_display_name(portfolio_choice)
    if values.empty:
        return _empty_figure(f"{selected_portfolio} Value Evolution")

    figure = go.Figure(
        go.Scatter(
            x=values["Date"],
            y=values["Portfolio Value"],
            mode="lines",
            name=selected_portfolio,
            line={"color": "#0ea5e9", "width": 2},
            hovertemplate=(
                "%{x|%d %b %Y}<br>"
                f"{currency} %{{y:,.2f}}"
                "<extra></extra>"
            ),
        )
    )
    figure.update_layout(
        title=f"{selected_portfolio} Value Evolution",
        xaxis_title="Date",
        yaxis_title=f"Value ({currency})",
        hovermode="x unified",
        separators=".,",
    )
    y_range = _padded_axis_range(values["Portfolio Value"])
    if y_range is not None:
        figure.update_yaxes(range=list(y_range))
    figure.update_yaxes(tickprefix=f"{currency} ", tickformat=",.2f")
    return figure


def _portfolio_display_name(portfolio_choice: str | int | None) -> str:
    if portfolio_choice in (None, "", ALL_PORTFOLIOS):
        return ALL_PORTFOLIOS
    choice = str(portfolio_choice)
    details = choice.split(" | ", 1)[-1]
    portfolio_path = details.rsplit(" [", 1)[0]
    return portfolio_path.rsplit(" / ", 1)[-1]


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
    y_values: list[float] = []
    if not twr.empty:
        y_values.extend((twr["TWR"] * 100).tolist())
    if not mwr.empty:
        y_values.extend((mwr["MWR"] * 100).tolist())
    y_range = _padded_axis_range(pd.Series(y_values, dtype=float))
    if y_range is not None:
        figure.update_yaxes(range=list(y_range))
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
    if not drawdown.empty:
        y_range = _padded_axis_range(drawdown["Drawdown"] * 100)
        if y_range is not None:
            figure.update_yaxes(range=list(y_range))
    return figure


def _benchmark_figure(overlay: pd.DataFrame) -> go.Figure:
    if overlay.empty:
        return _empty_figure("Portfolio vs Benchmark")
    figure = px.line(
        overlay,
        x="Date",
        y="Index",
        color="Series",
        title="Growth of 100: Portfolio vs Benchmark",
        labels={"Index": "Growth Index"},
    )
    y_range = _padded_axis_range(overlay["Index"])
    if y_range is not None:
        figure.update_yaxes(range=list(y_range))
    return figure


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


def _default_window(values: pd.DataFrame) -> tuple[date | None, date | None]:
    if values.empty or "Date" not in values.columns:
        return None, None
    parsed_dates = pd.to_datetime(values["Date"], errors="coerce").dropna()
    if parsed_dates.empty:
        return None, None
    end_date = parsed_dates.max().date()
    first_date = parsed_dates.min().date()
    start_date = max(first_date, end_date - timedelta(days=29))
    return start_date, end_date


def _parse_date_input(value: str | None) -> date | None:
    if value in (None, ""):
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()


def _resolve_date_window(
    values: pd.DataFrame,
    start_date_input: str | None,
    end_date_input: str | None,
) -> tuple[date | None, date | None]:
    default_start, default_end = _default_window(values)
    if values.empty:
        return _parse_date_input(start_date_input), _parse_date_input(end_date_input)

    parsed_dates = pd.to_datetime(values["Date"], errors="coerce").dropna()
    if parsed_dates.empty:
        return _parse_date_input(start_date_input), _parse_date_input(end_date_input)
    min_date = parsed_dates.min().date()
    max_date = parsed_dates.max().date()

    start_date = _parse_date_input(start_date_input) or default_start or min_date
    end_date = _parse_date_input(end_date_input) or default_end or max_date

    start_date = max(start_date, min_date)
    end_date = min(end_date, max_date)
    if start_date > end_date:
        start_date = end_date
    return start_date, end_date


def _filter_frame_by_date(
    frame: pd.DataFrame,
    start_date: date | None,
    end_date: date | None,
) -> pd.DataFrame:
    if frame.empty or "Date" not in frame.columns:
        return frame
    scoped = frame.copy()
    scoped["Date"] = pd.to_datetime(scoped["Date"], errors="coerce")
    scoped = scoped.dropna(subset=["Date"])
    if start_date is not None:
        scoped = scoped[scoped["Date"] >= pd.Timestamp(start_date)]
    if end_date is not None:
        scoped = scoped[scoped["Date"] <= pd.Timestamp(end_date)]
    if scoped.empty:
        return scoped
    scoped["Date"] = scoped["Date"].dt.date.astype(str)
    return scoped


def _padded_axis_range(series: pd.Series, pad_ratio: float = 0.05) -> tuple[float, float] | None:
    numeric = pd.to_numeric(series, errors="coerce").dropna()
    if numeric.empty:
        return None
    min_value = float(numeric.min())
    max_value = float(numeric.max())
    span = max_value - min_value
    padding = span * pad_ratio if span > 0 else max(abs(min_value), abs(max_value), 1.0) * pad_ratio
    return min_value - padding, max_value + padding
