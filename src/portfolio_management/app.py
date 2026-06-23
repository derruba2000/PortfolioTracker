"""
Portfolio Management application entry point.

All tab UI and callbacks live in portfolio_management/tabs/.
This module wires cross-tab callbacks and launches the app.
"""
from __future__ import annotations

import gradio as gr

from portfolio_management.db.init_db import initialize_database
from portfolio_management.tabs.accounts import build_accounts_tab, create_account_callback
from portfolio_management.tabs.brokers import build_brokers_tab
from portfolio_management.tabs.dashboard import build_dashboard_tab, refresh_dashboard
from portfolio_management.tabs.data_entry import build_data_entry_tab
from portfolio_management.tabs.market_data import build_market_data_tab
from portfolio_management.tabs.performance import build_performance_tab, _refresh_performance
from portfolio_management.tabs.portfolios import build_portfolios_tab, create_portfolio_callback
from portfolio_management.tabs.rebalance import build_rebalance_tab
from portfolio_management.tabs.settings import build_settings_tab
from portfolio_management.tabs.tax import build_tax_tab, _refresh_tax_report
from portfolio_management.services.accounts import (
    default_account_choice,
    default_portfolio_choice,
)


def _mode_changed(account_mode: str, tax_year: str) -> tuple[object, ...]:
    dashboard_values = refresh_dashboard(account_mode)
    return (
        *dashboard_values,
        _refresh_performance(account_mode),
        _refresh_tax_report(tax_year, account_mode),
    )


def build_app() -> gr.Blocks:
    selected_account = default_account_choice()
    selected_portfolio = default_portfolio_choice(selected_account)

    with gr.Blocks(title="Portfolio Management") as app:
        gr.Markdown("# Portfolio Management")

        # ── Build each tab ────────────────────────────────────────────────
        # mode_toggle lives inside the Dashboard tab so it doesn't clutter other tabs
        dashboard = build_dashboard_tab()
        mode_toggle = dashboard["mode_toggle"]
        mode_banner_html = dashboard["mode_banner_html"]

        build_rebalance_tab(mode_toggle)
        brokers = build_brokers_tab()
        accounts = build_accounts_tab(selected_account)
        portfolios = build_portfolios_tab(selected_account)
        data_entry = build_data_entry_tab(selected_account, selected_portfolio)
        build_market_data_tab()
        performance = build_performance_tab(mode_toggle)
        tax = build_tax_tab(mode_toggle)
        build_settings_tab()

        # ── Cross-tab: Dashboard refresh (needs top-level mode_banner_html) ──
        dashboard["refresh_dashboard_button"].click(
            fn=refresh_dashboard,
            inputs=[mode_toggle],
            outputs=[
                mode_banner_html,
                dashboard["summary_table"],
                dashboard["positions_table"],
                dashboard["asset_allocation_plot"],
                dashboard["currency_allocation_plot"],
            ],
        )

        # ── Cross-tab: Create Account (touches accounts + portfolios + brokers + data_entry) ──
        accounts["create_account_button"].click(
            fn=create_account_callback,
            inputs=[
                accounts["broker_name_input"],
                accounts["account_name_input"],
                accounts["account_currency_code"],
                accounts["new_account_description"],
                accounts["tax_wrapper_type"],
                accounts["is_simulated"],
                accounts["accounts_filter"],
            ],
            outputs=[
                accounts["account_status"],
                portfolios["portfolio_account_choice"],
                data_entry["account_choice"],
                accounts["edit_account_choice"],
                data_entry["portfolio_choice"],
                brokers["brokers_table"],
                accounts["accounts_table"],
            ],
        )

        # ── Cross-tab: Create Portfolio (touches portfolios + data_entry) ─
        portfolios["create_portfolio_button"].click(
            fn=create_portfolio_callback,
            inputs=[
                portfolios["portfolio_account_choice"],
                portfolios["new_portfolio_name"],
                portfolios["new_portfolio_description"],
                portfolios["portfolios_filter"],
            ],
            outputs=[
                portfolios["portfolio_status"],
                portfolios["portfolio_account_choice"],
                data_entry["account_choice"],
                data_entry["portfolio_choice"],
                portfolios["portfolios_table"],
            ],
        )

        # ── Cross-tab: Mode toggle (dashboard + performance + tax) ────────
        mode_toggle.change(
            fn=_mode_changed,
            inputs=[mode_toggle, tax["tax_year"]],
            outputs=[
                mode_banner_html,
                dashboard["summary_table"],
                dashboard["positions_table"],
                dashboard["asset_allocation_plot"],
                dashboard["currency_allocation_plot"],
                performance["performance_plot"],
                tax["tax_report"],
            ],
        )

    return app


def main() -> None:
    initialize_database()
    build_app().launch()


if __name__ == "__main__":
    main()
