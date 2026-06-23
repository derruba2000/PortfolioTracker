"""
Portfolio Tracker application entry point.

All tab UI and callbacks live in portfolio_management/tabs/.
This module wires cross-tab callbacks and launches the app.
"""
from __future__ import annotations

import gradio as gr

from portfolio_management.config import load_settings
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
from portfolio_management.tabs.securities import build_securities_tab
from portfolio_management.tabs.tax import build_tax_tab, _refresh_tax_report
from portfolio_management.services.accounts import (
    default_account_choice,
    default_portfolio_choice,
)


APP_THEME_CSS = """
:root { --tracker-accent: #0ea5e9; --tracker-surface: #1f2937; --tracker-border: #4b5563; }
.theme-base { --tracker-accent: #2563eb; --tracker-surface: #1f2937; --tracker-border: #4b5563; }
.theme-soft { --tracker-accent: #10b981; --tracker-surface: #1f2937; --tracker-border: #4b5563; }
.theme-monochrome { --tracker-accent: #d1d5db; --tracker-surface: #1f2937; --tracker-border: #6b7280; }
.theme-glass { --tracker-accent: #8b5cf6; --tracker-surface: #1f2937; --tracker-border: #4b5563; }
.theme-ocean { --tracker-accent: #0891b2; --tracker-surface: #1f2937; --tracker-border: #4b5563; }

body, body .gradio-container { background: var(--tracker-surface) !important; }
body .gradio-container button.primary {
    background: var(--tracker-accent) !important;
    border-color: var(--tracker-accent) !important;
}
body .gradio-container .block,
body .gradio-container .panel,
body .gradio-container .gr-box,
body .gradio-container .form,
body .gradio-container .wrap {
    border-color: var(--tracker-border) !important;
}
"""

APP_FAVICON_DATA_URI = (
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E"
    "%3Cdefs%3E%3ClinearGradient id='g' x1='0' y1='0' x2='1' y2='1'%3E"
    "%3Cstop offset='0%25' stop-color='%2306b6d4'/%3E"
    "%3Cstop offset='100%25' stop-color='%232563eb'/%3E"
    "%3C/linearGradient%3E%3C/defs%3E"
    "%3Crect width='64' height='64' rx='14' fill='%23111827'/%3E"
    "%3Ccircle cx='32' cy='32' r='24' fill='url(%23g)'/%3E"
    "%3Cpath d='M20 20h18a8 8 0 1 1 0 16H28v8h-8V20zm8 8h10a2 2 0 1 0 0-4H28v4z' fill='white'/%3E"
    "%3Cpath d='M39 44V20h6v24h-6z' fill='white'/%3E"
    "%3C/svg%3E"
)


def _build_theme(theme_name: str) -> gr.themes.Base:
    _ = theme_name
    # Keep a neutral base and drive theme color from CSS classes for instant switching.
    return gr.themes.Base(
        primary_hue=gr.themes.colors.slate,
        secondary_hue=gr.themes.colors.gray,
        neutral_hue=gr.themes.colors.gray,
    )


def _mode_changed(account_mode: str, tax_year: str) -> tuple[object, ...]:
    dashboard_values = refresh_dashboard(account_mode)
    return (
        *dashboard_values,
        _refresh_performance(account_mode),
        _refresh_tax_report(tax_year, account_mode),
    )


def build_app() -> gr.Blocks:
    initialize_database()
    settings = load_settings()
    selected_account = default_account_choice()
    selected_portfolio = default_portfolio_choice(selected_account)

    with gr.Blocks(
        title="Portfolio Tracker",
        theme=_build_theme(settings.theme_name),
        css=APP_THEME_CSS,
    ) as app:
        default_theme = settings.theme_name.strip().lower()
        gr.HTML(
            (
                "<script>(() => {"
                "const key='portfolio_tracker_theme';"
                "const allowed=['base','soft','monochrome','glass','ocean'];"
                f"const fallback='{default_theme}';"
                "const saved=String(localStorage.getItem(key) || fallback).toLowerCase();"
                "const selected=allowed.includes(saved) ? saved : fallback;"
                "const classes=['theme-base','theme-soft','theme-monochrome','theme-glass','theme-ocean'];"
                "document.documentElement.classList.remove(...classes);"
                "document.documentElement.classList.add('theme-' + selected);"
                "localStorage.setItem(key, selected);"
                f"const iconHref='{APP_FAVICON_DATA_URI}';"
                "let icon=document.querySelector(\"link[rel='icon']\");"
                "if(!icon){icon=document.createElement('link');icon.rel='icon';document.head.appendChild(icon);}"
                "icon.type='image/svg+xml';"
                "icon.href=iconHref;"
                "})();</script>"
            )
        )
        gr.Markdown("# Portfolio Tracker")

        # ── Build each tab ────────────────────────────────────────────────
        # mode_toggle lives inside the Dashboard tab so it doesn't clutter other tabs
        dashboard = build_dashboard_tab()
        mode_toggle = dashboard["mode_toggle"]
        mode_banner_html = dashboard["mode_banner_html"]

        build_rebalance_tab(mode_toggle)
        with gr.Tab("Master Data"):
            with gr.Tabs():
                brokers = build_brokers_tab()
                accounts = build_accounts_tab(selected_account)
                portfolios = build_portfolios_tab(selected_account)
                build_securities_tab()
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
                portfolios["new_portfolio_url"],
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
