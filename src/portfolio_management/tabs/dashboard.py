from __future__ import annotations

from datetime import date, timedelta
from html import escape
from typing import Any

import gradio as gr
import numpy as np
import pandas as pd
from sqlalchemy import select

from portfolio_management.db.models import PriceHistory, Security
from portfolio_management.db.session import get_session_factory
from portfolio_management.services.analytics import (
    allocation_by_asset_class,
    allocation_by_currency,
    current_positions,
    dashboard_summary,
)
from portfolio_management.services.analysis_filters import (
    ALL_PORTFOLIOS,
    parse_portfolio_filter,
    portfolio_filter_choices,
)
from portfolio_management.services.analytics import LIVE_MODE
from portfolio_management.tabs._shared import (
    format_integer_with_commas,
    format_two_decimals,
    mode_banner,
    portfolio_link,
    ticker_link,
)


REPORTING_CURRENCIES = ["GBP", "EUR", "USD"]
ALL_POSITION_ACCOUNTS = "All Accounts"
ALL_POSITION_PORTFOLIOS = "All Portfolios"
ALL_ASSET_CLASSES = "All Asset Classes"
DEFAULT_MARKET_LOOKBACK_DAYS = 30
DEFAULT_MARKET_TILE_COLUMNS = 4
DEFAULT_MARKET_TILE_HEIGHT = 380
MARKET_TILE_COLUMN_MIN = 1
MARKET_TILE_COLUMN_MAX = 8
MARKET_TILE_HEIGHT_MIN = 260
MARKET_TILE_HEIGHT_MAX = 700


def dashboard_summary_table(
    account_mode: str,
    reporting_currency: str,
    portfolio_choice: str | int | None = None,
) -> object:
    summary = dashboard_summary(
        account_mode=account_mode,
        reporting_currency=reporting_currency,
        portfolio_id=parse_portfolio_filter(portfolio_choice),
    ).copy()
    if "Value" in summary.columns:
        summary["Value"] = summary["Value"].map(format_two_decimals)
    return summary


def dashboard_positions(
    account_mode: str,
    reporting_currency: str,
    portfolio_choice: str | int | None = None,
    account_filter: str | None = None,
    position_portfolio_filter: str | None = None,
    asset_class_filter: str | None = None,
) -> object:
    positions = current_positions(
        account_mode=account_mode,
        reporting_currency=reporting_currency,
        portfolio_id=parse_portfolio_filter(portfolio_choice),
    ).copy()
    positions = _filter_dashboard_positions(
        positions,
        account_filter=account_filter,
        portfolio_filter=position_portfolio_filter,
        asset_class_filter=asset_class_filter,
    )
    if "Portfolio" in positions.columns and "Portfolio URL" in positions.columns:
        positions["Portfolio"] = positions.apply(
            lambda row: portfolio_link(row["Portfolio"], row["Portfolio URL"]),
            axis=1,
        )
        positions = positions.drop(columns=["Portfolio URL"])
    if "Ticker" in positions.columns:
        positions["Ticker"] = positions["Ticker"].map(ticker_link)
    if "Quantity" in positions.columns:
        positions["Quantity"] = positions["Quantity"].map(format_integer_with_commas)
    for column in ["Average Cost", "Latest Price", "Market Value", "Unrealized P&L"]:
        if column in positions.columns:
            positions[column] = positions[column].map(format_two_decimals)
    return positions


def dashboard_position_filter_choices(
    account_mode: str,
    reporting_currency: str,
    portfolio_choice: str | int | None = None,
    account_filter: str | None = None,
    position_portfolio_filter: str | None = None,
) -> tuple[list[str], list[str], list[str]]:
    positions = current_positions(
        account_mode=account_mode,
        reporting_currency=reporting_currency,
        portfolio_id=parse_portfolio_filter(portfolio_choice),
    )
    portfolio_positions = _filter_dashboard_positions(
        positions,
        account_filter=account_filter,
        portfolio_filter=None,
        asset_class_filter=None,
    )
    asset_class_positions = _filter_dashboard_positions(
        portfolio_positions,
        account_filter=None,
        portfolio_filter=position_portfolio_filter,
        asset_class_filter=None,
    )
    return (
        [ALL_POSITION_ACCOUNTS, *_column_choices(positions, "Account")],
        [
            ALL_POSITION_PORTFOLIOS,
            *_column_choices(portfolio_positions, "Portfolio"),
        ],
        [
            ALL_ASSET_CLASSES,
            *_column_choices(asset_class_positions, "Asset Class"),
        ],
    )


def _column_choices(positions: object, column: str) -> list[str]:
    if not hasattr(positions, "columns") or column not in positions.columns:
        return []
    return sorted(
        {
            str(value).strip()
            for value in positions[column].dropna()
            if str(value).strip()
        }
    )


def _filter_dashboard_positions(
    positions: object,
    account_filter: str | None,
    portfolio_filter: str | None,
    asset_class_filter: str | None,
) -> object:
    filters = (
        ("Account", account_filter, ALL_POSITION_ACCOUNTS),
        ("Portfolio", portfolio_filter, ALL_POSITION_PORTFOLIOS),
        ("Asset Class", asset_class_filter, ALL_ASSET_CLASSES),
    )
    for column, selected_value, all_value in filters:
        if selected_value not in (None, "", all_value) and column in positions.columns:
            normalized_selection = str(selected_value).strip()
            normalized_values = positions[column].astype(str).str.strip()
            positions = positions[normalized_values == normalized_selection]
    return positions.copy()


def refresh_dashboard(
    account_mode: str,
    reporting_currency: str,
    portfolio_choice: str | int | None = None,
    account_filter: str | None = None,
    position_portfolio_filter: str | None = None,
    asset_class_filter: str | None = None,
) -> tuple[Any, ...]:
    """Returns (mode_banner_html, summary, positions, asset_alloc, currency_alloc)."""
    positions = current_positions(
        account_mode=account_mode,
        reporting_currency=reporting_currency,
        portfolio_id=parse_portfolio_filter(portfolio_choice),
    ).copy()
    filtered_positions = _filter_dashboard_positions(
        positions,
        account_filter=account_filter,
        portfolio_filter=position_portfolio_filter,
        asset_class_filter=asset_class_filter,
    )
    return (
        mode_banner(account_mode),
        dashboard_summary_table(account_mode, reporting_currency, portfolio_choice),
        _format_dashboard_positions_table(filtered_positions),
        _allocation_from_positions(
            filtered_positions,
            group_column="Asset Class",
            output_column="Asset Class",
        ),
        _allocation_from_positions(
            filtered_positions,
            group_column="Currency",
            output_column="Currency",
        ),
    )


def dashboard_positions_and_charts(
    account_mode: str,
    reporting_currency: str,
    portfolio_choice: str | int | None = None,
    account_filter: str | None = None,
    position_portfolio_filter: str | None = None,
    asset_class_filter: str | None = None,
) -> tuple[object, object, object]:
    positions = current_positions(
        account_mode=account_mode,
        reporting_currency=reporting_currency,
        portfolio_id=parse_portfolio_filter(portfolio_choice),
    ).copy()
    filtered_positions = _filter_dashboard_positions(
        positions,
        account_filter=account_filter,
        portfolio_filter=position_portfolio_filter,
        asset_class_filter=asset_class_filter,
    )
    return (
        _format_dashboard_positions_table(filtered_positions),
        _allocation_from_positions(
            filtered_positions,
            group_column="Asset Class",
            output_column="Asset Class",
        ),
        _allocation_from_positions(
            filtered_positions,
            group_column="Currency",
            output_column="Currency",
        ),
    )


def _format_dashboard_positions_table(positions: object) -> object:
    positions = positions.copy()
    if "Portfolio" in positions.columns and "Portfolio URL" in positions.columns:
        positions["Portfolio"] = positions.apply(
            lambda row: portfolio_link(row["Portfolio"], row["Portfolio URL"]),
            axis=1,
        )
        positions = positions.drop(columns=["Portfolio URL"])
    if "Ticker" in positions.columns:
        positions["Ticker"] = positions["Ticker"].map(ticker_link)
    if "Quantity" in positions.columns:
        positions["Quantity"] = positions["Quantity"].map(format_integer_with_commas)
    for column in ["Average Cost", "Latest Price", "Market Value", "Unrealized P&L"]:
        if column in positions.columns:
            positions[column] = positions[column].map(format_two_decimals)
    return positions


def _allocation_from_positions(
    positions: object,
    group_column: str,
    output_column: str,
) -> object:
    if (
        not hasattr(positions, "columns")
        or group_column not in positions.columns
        or "Market Value" not in positions.columns
    ):
        return pd.DataFrame(columns=[output_column, "Market Value"])

    allocation = positions[[group_column, "Market Value"]].copy()
    allocation[group_column] = allocation[group_column].astype(str).str.strip()
    allocation = allocation[allocation[group_column] != ""]
    allocation["Market Value"] = pd.to_numeric(
        allocation["Market Value"],
        errors="coerce",
    )
    allocation = allocation.dropna(subset=["Market Value"])
    if allocation.empty:
        return pd.DataFrame(columns=[output_column, "Market Value"])

    return (
        allocation
        .groupby(group_column, as_index=False)["Market Value"]
        .sum()
        .sort_values(group_column)
        .rename(columns={group_column: output_column})
    )


def dashboard_scope_changed(
    account_mode: str,
    reporting_currency: str,
    active_only: bool = True,
) -> tuple[Any, ...]:
    choices = portfolio_filter_choices(account_mode, active_only=active_only)
    account_choices, position_portfolio_choices, asset_class_choices = (
        dashboard_position_filter_choices(
            account_mode,
            reporting_currency,
            ALL_PORTFOLIOS,
        )
    )
    return (
        gr.update(choices=choices, value=ALL_PORTFOLIOS),
        gr.update(choices=account_choices, value=ALL_POSITION_ACCOUNTS),
        gr.update(
            choices=position_portfolio_choices,
            value=ALL_POSITION_PORTFOLIOS,
        ),
        gr.update(choices=asset_class_choices, value=ALL_ASSET_CLASSES),
        *refresh_dashboard(account_mode, reporting_currency, ALL_PORTFOLIOS),
    )


def dashboard_portfolio_scope_changed(
    account_mode: str,
    reporting_currency: str,
    portfolio_choice: str | int | None,
) -> tuple[Any, ...]:
    account_choices, position_portfolio_choices, asset_class_choices = (
        dashboard_position_filter_choices(
            account_mode,
            reporting_currency,
            portfolio_choice,
        )
    )
    return (
        gr.update(choices=account_choices, value=ALL_POSITION_ACCOUNTS),
        gr.update(
            choices=position_portfolio_choices,
            value=ALL_POSITION_PORTFOLIOS,
        ),
        gr.update(choices=asset_class_choices, value=ALL_ASSET_CLASSES),
        *refresh_dashboard(account_mode, reporting_currency, portfolio_choice),
    )


def dashboard_position_account_changed(
    account_mode: str,
    reporting_currency: str,
    portfolio_choice: str | int | None,
    account_filter: str | None,
) -> tuple[Any, ...]:
    _, portfolio_choices, asset_class_choices = dashboard_position_filter_choices(
        account_mode,
        reporting_currency,
        portfolio_choice,
        account_filter=account_filter,
    )
    return (
        gr.update(choices=portfolio_choices, value=ALL_POSITION_PORTFOLIOS),
        gr.update(choices=asset_class_choices, value=ALL_ASSET_CLASSES),
        *dashboard_positions_and_charts(
            account_mode,
            reporting_currency,
            portfolio_choice,
            account_filter,
            ALL_POSITION_PORTFOLIOS,
            ALL_ASSET_CLASSES,
        ),
    )


def dashboard_position_portfolio_changed(
    account_mode: str,
    reporting_currency: str,
    portfolio_choice: str | int | None,
    account_filter: str | None,
    position_portfolio_filter: str | None,
) -> tuple[Any, ...]:
    _, _, asset_class_choices = dashboard_position_filter_choices(
        account_mode,
        reporting_currency,
        portfolio_choice,
        account_filter=account_filter,
        position_portfolio_filter=position_portfolio_filter,
    )
    return (
        gr.update(choices=asset_class_choices, value=ALL_ASSET_CLASSES),
        *dashboard_positions_and_charts(
            account_mode,
            reporting_currency,
            portfolio_choice,
            account_filter,
            position_portfolio_filter,
            ALL_ASSET_CLASSES,
        ),
    )


def market_data_asset_type_choices() -> list[str]:
    session_factory = get_session_factory()
    with session_factory() as session:
        values = session.scalars(
            select(Security.asset_class)
            .join(PriceHistory, PriceHistory.security_id == Security.id)
            .distinct()
            .order_by(Security.asset_class)
        ).all()
    return [str(value.value if hasattr(value, "value") else value) for value in values]


def market_data_ticker_choices(asset_type_filter: list[str] | str | None = None) -> list[str]:
    asset_types = _normalize_market_filter(asset_type_filter)
    session_factory = get_session_factory()
    with session_factory() as session:
        stmt = (
            select(Security.ticker)
            .join(PriceHistory, PriceHistory.security_id == Security.id)
            .distinct()
            .order_by(Security.ticker)
        )
        if asset_types:
            stmt = stmt.where(Security.asset_class.in_(asset_types))
        return [str(ticker) for ticker in session.scalars(stmt).all()]


def market_data_asset_type_changed(
    asset_type_filter: list[str] | str | None,
) -> Any:
    return gr.update(choices=market_data_ticker_choices(asset_type_filter), value=[])


def market_data_default_window() -> tuple[str, str]:
    end_date = date.today()
    start_date = end_date - timedelta(days=DEFAULT_MARKET_LOOKBACK_DAYS - 1)
    return start_date.isoformat(), end_date.isoformat()


def refresh_market_data_tiles(
    asset_type_filter: list[str] | str | None = None,
    ticker_filter: list[str] | str | None = None,
    start_date_input: str | None = None,
    end_date_input: str | None = None,
    columns_per_row: int | float | None = DEFAULT_MARKET_TILE_COLUMNS,
    tile_height: int | float | None = DEFAULT_MARKET_TILE_HEIGHT,
) -> object:
    start_date, end_date = _resolve_market_date_window(start_date_input, end_date_input)
    prices = _market_price_frame(
        asset_type_filter=asset_type_filter,
        ticker_filter=ticker_filter,
        start_date=start_date,
        end_date=end_date,
    )
    return _market_tiles_html(
        prices,
        int(columns_per_row or DEFAULT_MARKET_TILE_COLUMNS),
        int(tile_height or DEFAULT_MARKET_TILE_HEIGHT),
    )


def _normalize_market_filter(value: list[str] | str | None) -> list[str]:
    if value in (None, ""):
        return []
    raw_values = value if isinstance(value, list) else [value]
    return sorted({str(item).strip() for item in raw_values if str(item).strip()})


def _resolve_market_date_window(
    start_date_input: str | None,
    end_date_input: str | None,
) -> tuple[date, date]:
    default_start, default_end = market_data_default_window()
    start_date = _parse_market_date(start_date_input) or date.fromisoformat(default_start)
    end_date = _parse_market_date(end_date_input) or date.fromisoformat(default_end)
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    return start_date, end_date


def _parse_market_date(value: str | None) -> date | None:
    if value in (None, ""):
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()


def _market_price_frame(
    asset_type_filter: list[str] | str | None,
    ticker_filter: list[str] | str | None,
    start_date: date,
    end_date: date,
) -> pd.DataFrame:
    asset_types = _normalize_market_filter(asset_type_filter)
    tickers = _normalize_market_filter(ticker_filter)
    session_factory = get_session_factory()
    with session_factory() as session:
        stmt = (
            select(
                Security.ticker,
                Security.name,
                Security.asset_class,
                Security.currency_code,
                PriceHistory.date,
                PriceHistory.close,
                PriceHistory.volume,
            )
            .join(PriceHistory, PriceHistory.security_id == Security.id)
            .where(PriceHistory.date >= start_date, PriceHistory.date <= end_date)
            .order_by(Security.ticker, PriceHistory.date)
        )
        if asset_types:
            stmt = stmt.where(Security.asset_class.in_(asset_types))
        if tickers:
            stmt = stmt.where(Security.ticker.in_(tickers))
        rows = session.execute(stmt).all()

    records = []
    for ticker, name, asset_class, currency_code, price_date, close, volume in rows:
        records.append(
            {
                "Ticker": str(ticker),
                "Name": str(name or ""),
                "Asset Type": str(asset_class.value if hasattr(asset_class, "value") else asset_class),
                "Currency": str(currency_code or ""),
                "Date": price_date,
                "Price": float(close),
                "Volume": float(volume) if volume is not None else np.nan,
            }
        )
    return pd.DataFrame(
        records,
        columns=["Ticker", "Name", "Asset Type", "Currency", "Date", "Price", "Volume"],
    )


def _market_tiles_html(
    prices: pd.DataFrame,
    columns_per_row: int,
    tile_height: int,
) -> str:
    columns_per_row = max(
        MARKET_TILE_COLUMN_MIN,
        min(MARKET_TILE_COLUMN_MAX, int(columns_per_row or DEFAULT_MARKET_TILE_COLUMNS)),
    )
    tile_height = max(
        MARKET_TILE_HEIGHT_MIN,
        min(MARKET_TILE_HEIGHT_MAX, int(tile_height or DEFAULT_MARKET_TILE_HEIGHT)),
    )
    if prices.empty:
        return _empty_market_html()

    tiles = []
    for ticker, group in prices.groupby("Ticker", sort=True):
        group = group.sort_values("Date").reset_index(drop=True)
        volatility = _price_volatility(group["Price"])
        alpha, beta = _linear_regression_alpha_beta(group["Price"])
        tiles.append(_market_tile_html(str(ticker), group, volatility, alpha, beta, tile_height))

    return (
        "<style>"
        ".market-tile-grid{display:grid;gap:14px;"
        f"grid-template-columns:repeat({columns_per_row},minmax(280px,1fr));"
        "max-height:calc(100vh - 260px);overflow-y:auto;padding:2px 4px 12px 2px;}"
        ".market-tile{border:1px solid rgba(148,163,184,.45);border-radius:8px;"
        "background:rgba(15,23,42,.18);padding:12px;min-width:0;overflow:hidden;}"
        ".market-tile-title{display:flex;align-items:flex-start;justify-content:space-between;"
        "gap:10px;margin-bottom:8px;font-size:14px;line-height:1.25;}"
        ".market-tile-title a{font-weight:700;color:#38bdf8;text-decoration:none;}"
        ".market-tile-metrics{color:#cbd5e1;text-align:right;white-space:nowrap;font-size:12px;}"
        ".market-tile svg{display:block;width:100%;height:auto;overflow:hidden;}"
        "</style>"
        f"<div class='market-tile-grid'>{''.join(tiles)}</div>"
    )


def _market_tile_html(
    ticker: str,
    prices: pd.DataFrame,
    volatility: float,
    alpha: float,
    beta: float,
    tile_height: int,
) -> str:
    chart = _market_tile_svg(ticker, prices, alpha, beta, tile_height)
    return (
        "<div class='market-tile'>"
        "<div class='market-tile-title'>"
        f"<div>{ticker_link(ticker)}</div>"
        f"<div class='market-tile-metrics'>Vol {volatility:.3f}%<br>Reg. slope {beta:.3f}</div>"
        "</div>"
        f"{chart}"
        "</div>"
    )


def _market_tile_svg(
    ticker: str,
    prices: pd.DataFrame,
    alpha: float,
    beta: float,
    tile_height: int,
) -> str:
    width = 980
    height = tile_height
    plot_left = 96
    plot_top = 24
    plot_width = 660
    plot_height = max(120, height - 78)
    plot_right = plot_left + plot_width
    legend_x = 818
    axis_bottom = plot_top + plot_height
    clip_id = "clip-" + "".join(char if char.isalnum() else "-" for char in ticker)

    prices = prices.sort_values("Date").reset_index(drop=True)
    price_values = pd.to_numeric(prices["Price"], errors="coerce").to_numpy(dtype=float)
    volume_values = pd.to_numeric(prices.get("Volume"), errors="coerce").to_numpy(dtype=float)
    dates = pd.to_datetime(prices["Date"], errors="coerce")
    x_values = np.arange(len(price_values), dtype=float)
    trend_values = alpha + beta * x_values
    all_values = np.concatenate([price_values, trend_values])
    y_min = float(np.nanmin(all_values))
    y_max = float(np.nanmax(all_values))
    if y_min == y_max:
        padding = abs(y_min) * 0.05 or 1.0
        y_min -= padding
        y_max += padding
    else:
        padding = (y_max - y_min) * 0.08
        y_min -= padding
        y_max += padding

    def x_coord(index: int) -> float:
        if len(price_values) <= 1:
            return plot_left + plot_width / 2
        return plot_left + (index / (len(price_values) - 1)) * plot_width

    def y_coord(value: float) -> float:
        return plot_top + ((y_max - value) / (y_max - y_min)) * plot_height

    volume_max = float(np.nanmax(volume_values)) if np.isfinite(volume_values).any() else 0.0
    bar_slot_width = plot_width / max(len(volume_values), 1)
    bar_width = max(3.0, min(22.0, bar_slot_width * 0.58))
    volume_bars = "".join(
        _volume_bar_svg(
            x_coord(index),
            bar_width,
            plot_top,
            axis_bottom,
            plot_height,
            value,
            volume_max,
        )
        for index, value in enumerate(volume_values)
        if np.isfinite(value) and value > 0 and volume_max > 0
    )
    price_points = " ".join(
        f"{x_coord(index):.2f},{y_coord(value):.2f}"
        for index, value in enumerate(price_values)
        if not np.isnan(value)
    )
    trend_points = " ".join(
        f"{x_coord(index):.2f},{y_coord(value):.2f}"
        for index, value in enumerate(trend_values)
        if not np.isnan(value)
    )
    start_label = dates.iloc[0].strftime("%d %b") if not dates.empty else ""
    end_label = dates.iloc[-1].strftime("%d %b") if not dates.empty else ""

    return (
        f"<svg viewBox='0 0 {width} {height}' role='img' aria-label='{escape(ticker)} price chart'>"
        f"<defs><clipPath id='{escape(clip_id)}'>"
        f"<rect x='{plot_left}' y='{plot_top}' width='{plot_width}' height='{plot_height}' />"
        "</clipPath></defs>"
        f"<rect x='{plot_left}' y='{plot_top}' width='{plot_width}' height='{plot_height}' "
        "fill='rgba(15,23,42,.20)' stroke='rgba(148,163,184,.35)' />"
        f"<line x1='{plot_left}' y1='{axis_bottom}' x2='{plot_left + plot_width}' y2='{axis_bottom}' "
        "stroke='rgba(203,213,225,.55)' />"
        f"<line x1='{plot_left}' y1='{plot_top}' x2='{plot_left}' y2='{axis_bottom}' "
        "stroke='rgba(203,213,225,.55)' />"
        f"<line x1='{plot_right}' y1='{plot_top}' x2='{plot_right}' y2='{axis_bottom}' "
        "stroke='rgba(203,213,225,.35)' />"
        f"<text x='{plot_left - 8}' y='{plot_top + 5}' text-anchor='end' fill='#cbd5e1' "
        f"font-size='24'>{y_max:.3f}</text>"
        f"<text x='{plot_left - 8}' y='{axis_bottom}' text-anchor='end' fill='#cbd5e1' "
        f"font-size='24'>{y_min:.3f}</text>"
        f"<text x='{plot_right + 8}' y='{plot_top + 5}' fill='#94a3b8' "
        f"font-size='22'>{_format_compact_number(volume_max)}</text>"
        f"<text x='{plot_right + 8}' y='{axis_bottom}' fill='#94a3b8' font-size='22'>0</text>"
        f"<text x='{plot_left}' y='{axis_bottom + 32}' fill='#cbd5e1' font-size='24'>{escape(start_label)}</text>"
        f"<text x='{plot_right}' y='{axis_bottom + 32}' text-anchor='end' "
        f"fill='#cbd5e1' font-size='24'>{escape(end_label)}</text>"
        f"<g clip-path='url(#{escape(clip_id)})'>"
        f"{volume_bars}"
        f"<polyline points='{price_points}' fill='none' stroke='#0ea5e9' stroke-width='4' "
        "stroke-linecap='round' stroke-linejoin='round' />"
        f"<polyline points='{trend_points}' fill='none' stroke='#f97316' stroke-width='4' "
        "stroke-linecap='round' stroke-linejoin='round' stroke-dasharray='12 9' />"
        "</g>"
        f"<line x1='{legend_x}' y1='{plot_top + 20}' x2='{legend_x + 44}' y2='{plot_top + 20}' "
        "stroke='#0ea5e9' stroke-width='5' />"
        f"<text x='{legend_x + 56}' y='{plot_top + 28}' fill='#e5e7eb' font-size='24'>Price</text>"
        f"<line x1='{legend_x}' y1='{plot_top + 58}' x2='{legend_x + 44}' y2='{plot_top + 58}' "
        "stroke='#f97316' stroke-width='5' stroke-dasharray='12 9' />"
        f"<text x='{legend_x + 56}' y='{plot_top + 66}' fill='#e5e7eb' font-size='24'>Regression</text>"
        f"<rect x='{legend_x}' y='{plot_top + 84}' width='44' height='18' fill='#64748b' opacity='.38' />"
        f"<text x='{legend_x + 56}' y='{plot_top + 104}' fill='#e5e7eb' font-size='24'>Volume</text>"
        "</svg>"
    )


def _volume_bar_svg(
    x_center: float,
    width: float,
    plot_top: float,
    axis_bottom: float,
    plot_height: float,
    value: float,
    volume_max: float,
) -> str:
    if volume_max <= 0:
        return ""
    height = max(1.0, (value / volume_max) * plot_height)
    y = max(plot_top, axis_bottom - height)
    return (
        f"<rect x='{x_center - width / 2:.2f}' y='{y:.2f}' "
        f"width='{width:.2f}' height='{axis_bottom - y:.2f}' "
        "fill='#64748b' opacity='.38' />"
    )


def _format_compact_number(value: float) -> str:
    if not np.isfinite(value) or value <= 0:
        return "0"
    for suffix, divisor in (("B", 1_000_000_000), ("M", 1_000_000), ("K", 1_000)):
        if abs(value) >= divisor:
            return f"{value / divisor:.1f}{suffix}"
    return f"{value:.0f}"


def _price_volatility(prices: pd.Series) -> float:
    returns = pd.to_numeric(prices, errors="coerce").pct_change(fill_method=None).dropna()
    if returns.empty:
        return 0.0
    return float(returns.std(ddof=0) * 100)


def _linear_regression_alpha_beta(prices: pd.Series) -> tuple[float, float]:
    numeric_prices = pd.to_numeric(prices, errors="coerce").dropna().to_numpy(dtype=float)
    if len(numeric_prices) == 0:
        return 0.0, 0.0
    if len(numeric_prices) == 1:
        return float(numeric_prices[0]), 0.0
    x_values = np.arange(len(numeric_prices), dtype=float)
    beta, alpha = np.polyfit(x_values, numeric_prices, 1)
    return float(alpha), float(beta)


def _empty_market_html() -> str:
    return (
        "<div style='border:1px solid rgba(148,163,184,.45);border-radius:8px;"
        "padding:18px;color:#cbd5e1;'>No stored market data matches the selected filters.</div>"
    )


def build_dashboard_tab() -> dict[str, Any]:
    account_choices, position_portfolio_choices, asset_class_choices = (
        dashboard_position_filter_choices(LIVE_MODE, "GBP")
    )
    market_start_date, market_end_date = market_data_default_window()
    market_asset_type_choices = market_data_asset_type_choices()
    market_ticker_choices = market_data_ticker_choices()
    with gr.Tab("Dashboard"):
        with gr.Tabs():
            with gr.Tab("Overview"):
                with gr.Row():
                    portfolio_filter = gr.Dropdown(
                        label="Dashboard Portfolio Scope",
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
                mode_banner_html = gr.HTML(value=mode_banner(LIVE_MODE))
                summary_table = gr.Dataframe(
                    value=lambda: dashboard_summary_table(LIVE_MODE, "GBP"),
                    headers=["Metric", "Value"],
                    datatype=["str", "str"],
                    label="Summary",
                    interactive=False,
                )
                with gr.Row():
                    positions_account_filter = gr.Dropdown(
                        label="Account",
                        choices=account_choices,
                        value=ALL_POSITION_ACCOUNTS,
                        allow_custom_value=False,
                        filterable=True,
                    )
                    positions_portfolio_filter = gr.Dropdown(
                        label="Portfolio",
                        choices=position_portfolio_choices,
                        value=ALL_POSITION_PORTFOLIOS,
                        allow_custom_value=False,
                        filterable=True,
                    )
                    positions_asset_class_filter = gr.Dropdown(
                        label="Asset Class",
                        choices=asset_class_choices,
                        value=ALL_ASSET_CLASSES,
                        allow_custom_value=False,
                        filterable=True,
                    )
                positions_table = gr.Dataframe(
                    value=lambda: dashboard_positions(LIVE_MODE, "GBP"),
                    headers=[
                        "Broker", "Account", "Portfolio", "Ticker", "Name",
                        "Asset Class", "Currency", "Reporting Currency", "Quantity", "Average Cost",
                        "Latest Price", "Market Value", "Unrealized P&L",
                    ],
                    datatype=[
                        "str", "str", "markdown", "markdown", "str",
                        "str", "str", "str", "str", "str",
                        "str", "str", "str",
                    ],
                    label="Current Positions",
                    interactive=False,
                )
                with gr.Row():
                    asset_allocation_plot = gr.BarPlot(
                        value=lambda: allocation_by_asset_class(
                            account_mode=LIVE_MODE,
                            reporting_currency="GBP",
                        ),
                        x="Asset Class",
                        y="Market Value",
                        title="Allocation by Asset Class (Reporting Currency)",
                        y_title="Market Value in Selected Currency",
                    )
                    currency_allocation_plot = gr.BarPlot(
                        value=lambda: allocation_by_currency(
                            account_mode=LIVE_MODE,
                            reporting_currency="GBP",
                        ),
                        x="Currency",
                        y="Market Value",
                        title="Allocation by Source Currency (Reporting Currency)",
                        y_title="Market Value in Selected Currency",
                    )
                refresh_dashboard_button = gr.Button("Refresh Dashboard")

            with gr.Tab("Market Data"):
                with gr.Row():
                    market_asset_type_filter = gr.Dropdown(
                        label="Asset Type",
                        choices=market_asset_type_choices,
                        value=[],
                        multiselect=True,
                        allow_custom_value=False,
                        filterable=True,
                    )
                    market_ticker_filter = gr.Dropdown(
                        label="Ticker",
                        choices=market_ticker_choices,
                        value=[],
                        multiselect=True,
                        allow_custom_value=False,
                        filterable=True,
                    )
                    market_columns_per_row = gr.Slider(
                        label="Columns per Row",
                        minimum=MARKET_TILE_COLUMN_MIN,
                        maximum=MARKET_TILE_COLUMN_MAX,
                        step=1,
                        value=DEFAULT_MARKET_TILE_COLUMNS,
                    )
                    market_tile_height = gr.Slider(
                        label="Tile Height",
                        minimum=MARKET_TILE_HEIGHT_MIN,
                        maximum=MARKET_TILE_HEIGHT_MAX,
                        step=20,
                        value=DEFAULT_MARKET_TILE_HEIGHT,
                    )
                with gr.Row():
                    market_start_date_input = gr.DateTime(
                        label="Start Date",
                        include_time=False,
                        type="string",
                        value=market_start_date,
                    )
                    market_end_date_input = gr.DateTime(
                        label="End Date",
                        include_time=False,
                        type="string",
                        value=market_end_date,
                    )
                    refresh_market_data_button = gr.Button("Refresh Market Data", variant="primary")
                market_data_plot = gr.HTML(
                    value=lambda: refresh_market_data_tiles(
                        start_date_input=market_start_date,
                        end_date_input=market_end_date,
                        columns_per_row=DEFAULT_MARKET_TILE_COLUMNS,
                        tile_height=DEFAULT_MARKET_TILE_HEIGHT,
                    ),
                    label="Market Data",
                )

    return {
        "reporting_currency": reporting_currency,
        "portfolio_filter": portfolio_filter,
        "positions_account_filter": positions_account_filter,
        "positions_portfolio_filter": positions_portfolio_filter,
        "positions_asset_class_filter": positions_asset_class_filter,
        "mode_banner_html": mode_banner_html,
        "summary_table": summary_table,
        "positions_table": positions_table,
        "asset_allocation_plot": asset_allocation_plot,
        "currency_allocation_plot": currency_allocation_plot,
        "refresh_dashboard_button": refresh_dashboard_button,
        "market_asset_type_filter": market_asset_type_filter,
        "market_ticker_filter": market_ticker_filter,
        "market_start_date": market_start_date_input,
        "market_end_date": market_end_date_input,
        "market_columns_per_row": market_columns_per_row,
        "market_tile_height": market_tile_height,
        "market_data_plot": market_data_plot,
        "refresh_market_data_button": refresh_market_data_button,
    }
