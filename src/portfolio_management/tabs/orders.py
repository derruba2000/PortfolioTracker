from __future__ import annotations

from datetime import date as date_type
from datetime import timedelta
from typing import Any

import gradio as gr
import pandas as pd

from portfolio_management.services.analysis_filters import account_mode_to_table_filter
from portfolio_management.services.analytics import LIVE_MODE
from portfolio_management.services.orders import (
    buy_order_price_defaults,
    cancel_order,
    create_order,
    list_order_portfolio_choices,
    list_orders,
    list_pending_order_choices,
    mark_order_completed,
    order_execution_defaults,
    order_execution_preview,
    portfolio_account_currency,
)
from portfolio_management.services.reference_data import list_currency_codes
from portfolio_management.services.securities import list_security_tickers
from portfolio_management.tabs._shared import (
    format_decimal_input,
    format_decimal_with_commas,
    format_integer_with_commas,
    portfolio_link,
    ticker_link,
)


ORDER_TYPE_CHOICES = ["BUY", "SELL", "DEPOSIT", "WITHDRAW"]
ORDER_STATUS_FILTER_CHOICES = ["All", "PENDING", "EXECUTED", "CANCELLED"]
ALL_PORTFOLIOS = "All Portfolios"


def orders_table(
    account_mode: str = LIVE_MODE,
    status_filter: str = "All",
    portfolio_filter: str | None = None,
    start_date: str | date_type | None = None,
    end_date: str | date_type | None = None,
) -> object:
    orders_filter = account_mode_to_table_filter(account_mode)
    selected_portfolio = None if portfolio_filter == ALL_PORTFOLIOS else portfolio_filter
    orders = list_orders(
        account_filter=orders_filter,
        status_filter=status_filter,
        portfolio_filter=selected_portfolio,
        start_date=start_date,
        end_date=end_date,
    )
    if isinstance(orders, pd.DataFrame):
        if "Portfolio" in orders.columns and "Portfolio URL" in orders.columns:
            orders["Portfolio"] = orders.apply(
                lambda row: portfolio_link(row["Portfolio"], row["Portfolio URL"]),
                axis=1,
            )
            orders = orders.drop(columns=["Portfolio URL"])
        if "Asset/Ticker" in orders.columns:
            orders["Asset/Ticker"] = orders["Asset/Ticker"].map(_asset_ticker_link)
        if "Quantity" in orders.columns:
            orders["Quantity"] = orders["Quantity"].map(format_integer_with_commas)
        if "Price" in orders.columns:
            orders["Price"] = orders["Price"].map(format_decimal_with_commas)
    return orders


def refresh_orders_for_mode(account_mode: str) -> object:
    return orders_table(account_mode)


def build_orders_tab(mode_toggle: gr.Radio) -> dict[str, Any]:
    default_end_date = date_type.today()
    default_start_date = default_end_date - timedelta(days=29)
    initial_portfolios = _portfolio_choices_for_mode(LIVE_MODE)

    with gr.Tab("Orders"):
        status = gr.Textbox(label="Status", interactive=False)

        with gr.Row():
            portfolio_choice = gr.Dropdown(
                label="Portfolio",
                choices=initial_portfolios,
            )
            order_type = gr.Dropdown(
                label="Action Type",
                choices=ORDER_TYPE_CHOICES,
                value="BUY",
            )

        with gr.Row():
            security_ticker = gr.Dropdown(
                label="Security",
                choices=list_security_tickers(),
                allow_custom_value=True,
                visible=True,
            )
            target_quantity = gr.Textbox(label="Target Quantity", visible=True)
            target_limit_price = gr.Textbox(label="Target Limit Price", visible=True)
            currency_code = gr.Dropdown(
                label="Currency",
                choices=list_currency_codes(),
                value=_default_currency_for_portfolio_choice(
                    initial_portfolios[0] if initial_portfolios else None
                ),
                allow_custom_value=True,
            )
            target_cash_amount = gr.Textbox(label="Target Cash Amount", visible=False)
            security_current_price = gr.Markdown(value="", visible=True)

        create_order_button = gr.Button("Create Order", variant="primary")

        with gr.Row():
            cancel_order_choice = gr.Dropdown(
                label="Pending Order",
                choices=_pending_order_choices_for_mode(LIVE_MODE),
            )
            cancel_order_button = gr.Button("Cancel Pending Order", variant="secondary")

        with gr.Row():
            execute_order_choice = gr.Dropdown(
                label="Pending Order To Execute",
                choices=_pending_order_choices_for_mode(LIVE_MODE),
            )
            actual_quantity = gr.Textbox(label="Actual Execution Quantity", value="1")
            actual_price = gr.Textbox(label="Actual Execution Price", value="0")
            actual_fees = gr.Textbox(label="Actual Broker Fees", value="0")
            mark_completed_button = gr.Button("Mark as Completed", variant="primary")
        execution_fee_preview = gr.Textbox(
            label="Execution Preview",
            value="Select a pending order to preview execution quantities, volume, and fees.",
            interactive=False,
            lines=16,
        )

        with gr.Row():
            status_filter = gr.Dropdown(
                label="Status Filter",
                choices=ORDER_STATUS_FILTER_CHOICES,
                value="All",
            )
            portfolio_filter = gr.Dropdown(
                label="Portfolio Filter",
                choices=_portfolio_filter_choices_for_mode(LIVE_MODE),
                value=ALL_PORTFOLIOS,
            )
            start_date_filter = gr.DateTime(
                label="Start Date",
                include_time=False,
                type="string",
                value=default_start_date.isoformat(),
            )
            end_date_filter = gr.DateTime(
                label="End Date",
                include_time=False,
                type="string",
                value=default_end_date.isoformat(),
            )

        orders_table_component = gr.Dataframe(
            value=lambda: orders_table(
                LIVE_MODE,
                status_filter="All",
                portfolio_filter=ALL_PORTFOLIOS,
                start_date=default_start_date.isoformat(),
                end_date=default_end_date.isoformat(),
            ),
            headers=[
                "ID",
                "Date",
                "Portfolio",
                "Type",
                "Asset/Ticker",
                "Quantity",
                "Price",
                "Currency",
                "Status",
                "Market vs Target",
            ],
            datatype=[
                "number",
                "date",
                "markdown",
                "str",
                "markdown",
                "str",
                "str",
                "str",
                "str",
                "markdown",
            ],
            label="Orders",
            interactive=False,
            show_fullscreen_button=True,
        )
        refresh_orders_button = gr.Button("Refresh Orders")

        target_quantity.input(fn=format_decimal_input, inputs=[target_quantity], outputs=[target_quantity])
        target_limit_price.input(
            fn=format_decimal_input,
            inputs=[target_limit_price],
            outputs=[target_limit_price],
        )
        target_cash_amount.input(
            fn=format_decimal_input,
            inputs=[target_cash_amount],
            outputs=[target_cash_amount],
        )
        actual_quantity.input(fn=format_decimal_input, inputs=[actual_quantity], outputs=[actual_quantity])
        actual_price.input(fn=format_decimal_input, inputs=[actual_price], outputs=[actual_price])
        actual_fees.input(fn=format_decimal_input, inputs=[actual_fees], outputs=[actual_fees])

        mode_toggle.change(
            fn=_orders_mode_changed,
            inputs=[mode_toggle],
            outputs=[
                portfolio_choice,
                security_ticker,
                currency_code,
                portfolio_filter,
                cancel_order_choice,
                execute_order_choice,
            ],
        )
        portfolio_choice.change(
            fn=_portfolio_choice_changed,
            inputs=[portfolio_choice],
            outputs=[currency_code],
        )
        order_type.change(
            fn=_order_type_changed,
            inputs=[order_type, security_ticker],
            outputs=[
                security_ticker,
                target_quantity,
                target_limit_price,
                target_cash_amount,
                security_current_price,
            ],
        )
        security_ticker.change(
            fn=_security_ticker_changed,
            inputs=[order_type, security_ticker],
            outputs=[target_limit_price, security_current_price],
        )
        create_order_button.click(
            fn=_create_order_callback,
            inputs=[
                portfolio_choice,
                order_type,
                security_ticker,
                target_quantity,
                target_limit_price,
                currency_code,
                target_cash_amount,
                mode_toggle,
                status_filter,
                portfolio_filter,
                start_date_filter,
                end_date_filter,
            ],
            outputs=[status, orders_table_component, cancel_order_choice, execute_order_choice],
        )
        execute_order_choice.change(
            fn=_execute_order_choice_changed,
            inputs=[execute_order_choice],
            outputs=[actual_quantity, actual_price, actual_fees, execution_fee_preview],
        )
        actual_quantity.change(
            fn=_execution_preview_changed,
            inputs=[execute_order_choice, actual_quantity, actual_price, actual_fees],
            outputs=[execution_fee_preview],
        )
        actual_price.change(
            fn=_execution_preview_changed,
            inputs=[execute_order_choice, actual_quantity, actual_price, actual_fees],
            outputs=[execution_fee_preview],
        )
        actual_fees.change(
            fn=_execution_preview_changed,
            inputs=[execute_order_choice, actual_quantity, actual_price, actual_fees],
            outputs=[execution_fee_preview],
        )
        cancel_order_button.click(
            fn=_cancel_order_callback,
            inputs=[
                cancel_order_choice,
                mode_toggle,
                status_filter,
                portfolio_filter,
                start_date_filter,
                end_date_filter,
            ],
            outputs=[status, orders_table_component, cancel_order_choice, execute_order_choice],
        )
        mark_completed_button.click(
            fn=_mark_completed_callback,
            inputs=[
                execute_order_choice,
                actual_quantity,
                actual_price,
                actual_fees,
                mode_toggle,
                status_filter,
                portfolio_filter,
                start_date_filter,
                end_date_filter,
            ],
            outputs=[status, orders_table_component, cancel_order_choice, execute_order_choice],
        )
        status_filter.change(
            fn=_orders_filtered_table,
            inputs=[mode_toggle, status_filter, portfolio_filter, start_date_filter, end_date_filter],
            outputs=[orders_table_component],
        )
        portfolio_filter.change(
            fn=_orders_filtered_table,
            inputs=[mode_toggle, status_filter, portfolio_filter, start_date_filter, end_date_filter],
            outputs=[orders_table_component],
        )
        start_date_filter.change(
            fn=_orders_filtered_table,
            inputs=[mode_toggle, status_filter, portfolio_filter, start_date_filter, end_date_filter],
            outputs=[orders_table_component],
        )
        end_date_filter.change(
            fn=_orders_filtered_table,
            inputs=[mode_toggle, status_filter, portfolio_filter, start_date_filter, end_date_filter],
            outputs=[orders_table_component],
        )
        refresh_orders_button.click(
            fn=_orders_filtered_table,
            inputs=[mode_toggle, status_filter, portfolio_filter, start_date_filter, end_date_filter],
            outputs=[orders_table_component],
        )

    return {
        "status": status,
        "portfolio_choice": portfolio_choice,
        "order_type": order_type,
        "security_ticker": security_ticker,
        "target_quantity": target_quantity,
        "target_limit_price": target_limit_price,
        "currency_code": currency_code,
        "target_cash_amount": target_cash_amount,
        "security_current_price": security_current_price,
        "create_order_button": create_order_button,
        "cancel_order_choice": cancel_order_choice,
        "cancel_order_button": cancel_order_button,
        "execute_order_choice": execute_order_choice,
        "actual_quantity": actual_quantity,
        "actual_price": actual_price,
        "actual_fees": actual_fees,
        "execution_fee_preview": execution_fee_preview,
        "mark_completed_button": mark_completed_button,
        "status_filter": status_filter,
        "portfolio_filter": portfolio_filter,
        "start_date_filter": start_date_filter,
        "end_date_filter": end_date_filter,
        "orders_table": orders_table_component,
        "refresh_orders_button": refresh_orders_button,
    }


def _asset_ticker_link(asset_ticker: object) -> str:
    clean = str(asset_ticker or "").strip()
    if not clean or clean == "CASH":
        return clean
    return ticker_link(clean)


def _portfolio_choices_for_mode(account_mode: str) -> list[str]:
    orders_filter = account_mode_to_table_filter(account_mode)
    return list_order_portfolio_choices(orders_filter)


def _orders_mode_changed(account_mode: str) -> tuple[object, object, object, object, object, object]:
    portfolios = _portfolio_choices_for_mode(account_mode)
    selected = portfolios[0] if portfolios else None
    filter_portfolios = _portfolio_filter_choices_for_mode(account_mode)
    pending_orders = _pending_order_choices_for_mode(account_mode)
    currencies = list_currency_codes()
    selected_currency = _default_currency_for_portfolio_choice(selected)
    return (
        gr.update(choices=portfolios, value=selected),
        gr.update(choices=list_security_tickers()),
        gr.update(choices=currencies, value=selected_currency),
        gr.update(choices=filter_portfolios, value=ALL_PORTFOLIOS),
        gr.update(choices=pending_orders, value=pending_orders[0] if pending_orders else None),
        gr.update(choices=pending_orders, value=pending_orders[0] if pending_orders else None),
    )


def _portfolio_choice_changed(portfolio_choice: str | None) -> object:
    return gr.update(value=_default_currency_for_portfolio_choice(portfolio_choice))


def _order_type_changed(
    selected_order_type: str,
    security_ticker: str | None,
) -> tuple[object, object, object, object, object]:
    buy_or_sell = selected_order_type in {"BUY", "SELL"}
    price, target_price, trend = (
        buy_order_price_defaults(security_ticker)
        if selected_order_type == "BUY"
        else ("", "", "none")
    )
    return (
        gr.update(visible=buy_or_sell, value=None),
        gr.update(visible=buy_or_sell, value=""),
        gr.update(visible=buy_or_sell, value=target_price),
        gr.update(visible=not buy_or_sell, value=""),
        gr.update(
            visible=selected_order_type == "BUY" and bool(price),
            value=_current_price_badge(price, trend),
        ),
    )


def _security_ticker_changed(order_type: str, security_ticker: str | None) -> tuple[object, object]:
    if order_type != "BUY":
        return gr.update(), gr.update(value="", visible=False)

    price, target_price, trend = buy_order_price_defaults(security_ticker)
    return (
        gr.update(value=target_price),
        gr.update(value=_current_price_badge(price, trend), visible=bool(price)),
    )


def _create_order_callback(
    portfolio_choice: str,
    order_type: str,
    security_ticker: str,
    target_quantity: str,
    target_limit_price: str,
    currency_code: str,
    target_cash_amount: str,
    account_mode: str,
    status_filter: str,
    portfolio_filter: str,
    start_date: str,
    end_date: str,
) -> tuple[object, object, object]:
    try:
        status = create_order(
            portfolio_choice=portfolio_choice,
            order_type=order_type,
            security_ticker=security_ticker,
            target_quantity=target_quantity,
            target_price=target_limit_price,
            target_cash_amount=target_cash_amount,
            currency_code=currency_code,
        )
    except Exception as exc:
        return (
            f"Error: {exc}",
            _orders_filtered_table(
                account_mode,
                status_filter,
                portfolio_filter,
                start_date,
                end_date,
            ),
            gr.update(),
            gr.update(),
        )
    pending_orders = _pending_order_choices_for_mode(account_mode)
    return (
        status,
        _orders_filtered_table(
            account_mode,
            status_filter,
            portfolio_filter,
            start_date,
            end_date,
        ),
        gr.update(choices=pending_orders, value=pending_orders[0] if pending_orders else None),
        gr.update(choices=pending_orders, value=pending_orders[0] if pending_orders else None),
    )


def _portfolio_filter_choices_for_mode(account_mode: str) -> list[str]:
    return [ALL_PORTFOLIOS, *_portfolio_choices_for_mode(account_mode)]


def _pending_order_choices_for_mode(account_mode: str) -> list[str]:
    orders_filter = account_mode_to_table_filter(account_mode)
    return list_pending_order_choices(orders_filter)


def _execute_order_choice_changed(order_choice: str | None) -> tuple[object, object, object, str]:
    quantity, price, fees = order_execution_defaults(order_choice)
    preview = order_execution_preview(order_choice, quantity, price, fees)
    return gr.update(value=quantity), gr.update(value=price), gr.update(value=fees), preview


def _execution_preview_changed(
    order_choice: str | None,
    quantity: str,
    price: str,
    fees: str,
) -> str:
    return order_execution_preview(order_choice, quantity, price, fees)


def _default_currency_for_portfolio_choice(portfolio_choice: str | None) -> str | None:
    currency = portfolio_account_currency(portfolio_choice)
    return currency or None


def _current_price_badge(price: str, trend: str) -> str:
    if not price:
        return ""
    color_by_trend = {
        "up": "#16a34a",
        "down": "#dc2626",
        "flat": "#6b7280",
    }
    arrow_by_trend = {
        "up": "▲",
        "down": "▼",
        "flat": "=",
    }
    color = color_by_trend.get(trend, "#6b7280")
    arrow = arrow_by_trend.get(trend, "=")
    style = (
        f"background:{color};color:white;padding:3px 8px;"
        "border-radius:4px;font-weight:600;font-size:0.9em;"
    )
    return f'<span style="{style}">{arrow} Current {price}</span>'


def _orders_filtered_table(
    account_mode: str,
    status_filter: str,
    portfolio_filter: str,
    start_date: str,
    end_date: str,
) -> object:
    return orders_table(
        account_mode=account_mode,
        status_filter=status_filter,
        portfolio_filter=portfolio_filter,
        start_date=start_date,
        end_date=end_date,
    )


def _cancel_order_callback(
    order_choice: str,
    account_mode: str,
    status_filter: str,
    portfolio_filter: str,
    start_date: str,
    end_date: str,
) -> tuple[object, object, object]:
    try:
        status = cancel_order(order_choice)
    except Exception as exc:
        return (
            f"Error: {exc}",
            _orders_filtered_table(
                account_mode,
                status_filter,
                portfolio_filter,
                start_date,
                end_date,
            ),
            gr.update(),
            gr.update(),
        )

    pending_orders = _pending_order_choices_for_mode(account_mode)
    return (
        status,
        _orders_filtered_table(
            account_mode,
            status_filter,
            portfolio_filter,
            start_date,
            end_date,
        ),
        gr.update(choices=pending_orders, value=pending_orders[0] if pending_orders else None),
        gr.update(choices=pending_orders, value=pending_orders[0] if pending_orders else None),
    )


def _mark_completed_callback(
    order_choice: str,
    actual_quantity: str,
    actual_price: str,
    actual_fees: str,
    account_mode: str,
    status_filter: str,
    portfolio_filter: str,
    start_date: str,
    end_date: str,
) -> tuple[object, object, object, object]:
    try:
        status = mark_order_completed(
            order_choice=order_choice,
            actual_quantity=actual_quantity,
            actual_price=actual_price,
            actual_fees=actual_fees,
        )
    except Exception as exc:
        return (
            f"Error: {exc}",
            _orders_filtered_table(
                account_mode,
                status_filter,
                portfolio_filter,
                start_date,
                end_date,
            ),
            gr.update(),
            gr.update(),
        )

    pending_orders = _pending_order_choices_for_mode(account_mode)
    return (
        status,
        _orders_filtered_table(
            account_mode,
            status_filter,
            portfolio_filter,
            start_date,
            end_date,
        ),
        gr.update(choices=pending_orders, value=pending_orders[0] if pending_orders else None),
        gr.update(choices=pending_orders, value=pending_orders[0] if pending_orders else None),
    )
