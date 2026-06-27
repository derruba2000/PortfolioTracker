"""
Portfolio Tracker application entry point.

All tab UI and callbacks live in portfolio_management/tabs/.
This module wires cross-tab callbacks and launches the app.
"""
from __future__ import annotations

import base64
from pathlib import Path

import gradio as gr

from portfolio_management.config import load_settings
from portfolio_management.db.init_db import initialize_database
from portfolio_management.tabs.accounts import (
    account_edit_choices_for_mode,
    accounts_for_mode,
    broker_dropdown_choices,
    build_accounts_tab,
    create_account_callback,
)
from portfolio_management.tabs.alerts import build_alerts_tab
from portfolio_management.tabs.brokers import build_brokers_tab
from portfolio_management.tabs.dashboard import (
    build_dashboard_tab,
    dashboard_portfolio_scope_changed,
    dashboard_position_account_changed,
    dashboard_position_portfolio_changed,
    dashboard_positions,
    dashboard_scope_changed,
    refresh_dashboard,
)
from portfolio_management.tabs.data_entry import build_data_entry_tab, data_entry_mode_changed
from portfolio_management.tabs.export import build_export_tab, _export_scope_changed
from portfolio_management.tabs.performance import build_performance_tab, refresh_performance_for_mode
from portfolio_management.tabs.portfolios import (
    build_portfolios_tab,
    portfolios_mode_changed,
    save_portfolio_callback,
)
from portfolio_management.tabs.rebalance import build_rebalance_tab, _rebalance_mode_changed
from portfolio_management.tabs.settings import build_settings_tab
from portfolio_management.tabs.securities import build_securities_tab
from portfolio_management.tabs.tax import build_tax_tab, _refresh_tax_report
from portfolio_management.services.analysis_filters import APP_ACCOUNT_MODE_CHOICES
from portfolio_management.services.analytics import LIVE_MODE
from portfolio_management.services.accounts import (
    account_choices,
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

APP_FAVICON_PATH = Path(__file__).resolve().parent / "assets" / "Icon_Portfolio_Tracker.png"


def _build_icon_data_uri(icon_path: Path) -> str | None:
    if not icon_path.exists():
        return None
    encoded = base64.b64encode(icon_path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


APP_TITLE_ICON_DATA_URI = _build_icon_data_uri(APP_FAVICON_PATH)


def _build_theme(theme_name: str) -> gr.themes.Base:
    _ = theme_name
    # Keep a neutral base and drive theme color from CSS classes for instant switching.
    return gr.themes.Base(
        primary_hue=gr.themes.colors.slate,
        secondary_hue=gr.themes.colors.gray,
        neutral_hue=gr.themes.colors.gray,
    )


def _mode_changed(
    account_mode: str,
    reporting_currency: str,
    tax_year: str,
) -> tuple[object, ...]:
    return (
        *dashboard_scope_changed(account_mode, reporting_currency),
        _refresh_tax_report(tax_year, account_mode),
    )


def _accounts_mode_changed(account_mode: str) -> tuple[object, ...]:
    return account_edit_choices_for_mode(account_mode), accounts_for_mode(account_mode)


def _account_broker_dropdowns_changed() -> tuple[object, ...]:
    active_brokers = broker_dropdown_choices()
    all_brokers = broker_dropdown_choices(include_inactive=True)
    return (
        gr.update(
            choices=active_brokers,
            value=active_brokers[0] if active_brokers else None,
        ),
        gr.update(choices=all_brokers),
    )


def build_app() -> gr.Blocks:
    initialize_database()
    settings = load_settings()
    live_accounts = account_choices(account_mode=LIVE_MODE)
    selected_account = live_accounts[0] if live_accounts else default_account_choice()
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
                "})();</script>"
            )
        )
        with gr.Row():
            with gr.Column(scale=5):
                if APP_TITLE_ICON_DATA_URI:
                    gr.HTML(
                        (
                            "<div style='display:flex;align-items:center;gap:10px;margin:0 0 8px 0;'>"
                            f"<img src='{APP_TITLE_ICON_DATA_URI}' alt='Portfolio Tracker icon' "
                            "style='width:28px;height:28px;border-radius:6px;' />"
                            "<h1 style='margin:0;'>Portfolio Tracker</h1>"
                            "</div>"
                        )
                    )
                else:
                    gr.Markdown("# Portfolio Tracker")
            with gr.Column(scale=2):
                mode_toggle = gr.Radio(
                    label="Mode",
                    choices=APP_ACCOUNT_MODE_CHOICES,
                    value=LIVE_MODE,
                )

        # ── Build each tab ────────────────────────────────────────────────
        dashboard = build_dashboard_tab()
        reporting_currency = dashboard["reporting_currency"]
        dashboard_portfolio_filter = dashboard["portfolio_filter"]
        positions_account_filter = dashboard["positions_account_filter"]
        positions_portfolio_filter = dashboard["positions_portfolio_filter"]
        positions_asset_class_filter = dashboard["positions_asset_class_filter"]
        mode_banner_html = dashboard["mode_banner_html"]

        rebalance = build_rebalance_tab(mode_toggle)
        with gr.Tab("Master Data"):
            with gr.Tabs():
                brokers = build_brokers_tab()
                accounts = build_accounts_tab(selected_account, mode_toggle)
                portfolios = build_portfolios_tab(selected_account, mode_toggle)
                build_securities_tab()
        data_entry = build_data_entry_tab(selected_account, selected_portfolio, mode_toggle)
        performance = build_performance_tab(mode_toggle)
        tax = build_tax_tab(mode_toggle)
        build_alerts_tab()
        import_export = build_export_tab(mode_toggle)
        settings_tab = build_settings_tab()

        # Keep the Import / Export paths in sync when they are saved in Settings.
        settings_tab["save_market_data_paths_button"].click(
            fn=lambda prices_path, fx_path: (prices_path.strip(), fx_path.strip()),
            inputs=[
                settings_tab["market_prices_delta_path"],
                settings_tab["fx_rates_delta_path"],
            ],
            outputs=[
                import_export["prices_path"],
                import_export["fx_path"],
            ],
        )

        for broker_button in [
            brokers["create_broker_button"],
            brokers["update_broker_button"],
            brokers["delete_broker_button"],
            brokers["refresh_brokers_button"],
        ]:
            broker_button.click(
                fn=_account_broker_dropdowns_changed,
                outputs=[
                    accounts["broker_name_input"],
                    accounts["edit_broker_name"],
                ],
            )

        # ── Cross-tab: Dashboard refresh (needs top-level mode_banner_html) ──
        dashboard["refresh_dashboard_button"].click(
            fn=refresh_dashboard,
            inputs=[
                mode_toggle,
                reporting_currency,
                dashboard_portfolio_filter,
                positions_account_filter,
                positions_portfolio_filter,
                positions_asset_class_filter,
            ],
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
                mode_toggle,
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

        # ── Cross-tab: Save Portfolio (touches portfolios + data_entry) ─
        portfolios["create_portfolio_button"].click(
            fn=save_portfolio_callback,
            inputs=[
                portfolios["edit_portfolio_choice"],
                portfolios["portfolio_account_choice"],
                portfolios["new_portfolio_name"],
                portfolios["new_portfolio_description"],
                portfolios["new_portfolio_url"],
                portfolios["new_portfolio_goals"],
                portfolios["new_goal_type"],
                portfolios["new_goal_timeline"],
                portfolios["edit_portfolio_active"],
                mode_toggle,
                portfolios["portfolio_view_filter"],
            ],
            outputs=[
                portfolios["portfolio_status"],
                portfolios["portfolio_account_choice"],
                data_entry["account_choice"],
                data_entry["portfolio_choice"],
                portfolios["new_portfolio_name"],
                portfolios["edit_portfolio_choice"],
                portfolios["llm_questions"],
                portfolios["llm_timestamp_label"],
                portfolios["llm_answers"],
                portfolios["portfolio_view_filter"],
                portfolios["portfolios_table"],
                portfolios["portfolio_assets_table"],
            ],
        )

        # ── Cross-tab: Mode toggle (dashboard + performance + tax) ────────
        mode_toggle.change(
            fn=_mode_changed,
            inputs=[mode_toggle, reporting_currency, tax["tax_year"]],
            outputs=[
                dashboard_portfolio_filter,
                positions_account_filter,
                positions_portfolio_filter,
                positions_asset_class_filter,
                mode_banner_html,
                dashboard["summary_table"],
                dashboard["positions_table"],
                dashboard["asset_allocation_plot"],
                dashboard["currency_allocation_plot"],
                tax["tax_report"],
            ],
        )
        mode_toggle.change(
            fn=refresh_performance_for_mode,
            inputs=[
                mode_toggle,
                performance["benchmark_choice"],
                performance["reporting_currency"],
                performance["risk_free_rate"],
            ],
            outputs=[
                performance["portfolio_filter"],
                performance["portfolio_value_plot"],
                performance["performance_plot"],
                performance["drawdown_plot"],
                performance["risk_metrics_table"],
                performance["benchmark_plot"],
                performance["benchmark_metrics_table"],
                performance["correlation_plot"],
                performance["stress_plot"],
            ],
        )
        mode_toggle.change(
            fn=_rebalance_mode_changed,
            inputs=[mode_toggle],
            outputs=[
                rebalance["rebalance_account"],
                rebalance["saved_target"],
                rebalance["target_allocations_table"],
                rebalance["rebalance_table"],
            ],
        )
        mode_toggle.change(
            fn=_accounts_mode_changed,
            inputs=[mode_toggle],
            outputs=[accounts["edit_account_choice"], accounts["accounts_table"]],
        )
        mode_toggle.change(
            fn=portfolios_mode_changed,
            inputs=[mode_toggle],
            outputs=[
                portfolios["portfolio_account_choice"],
                portfolios["new_portfolio_name"],
                portfolios["edit_portfolio_choice"],
                portfolios["new_portfolio_description"],
                portfolios["new_portfolio_url"],
                portfolios["new_portfolio_goals"],
                portfolios["new_goal_type"],
                portfolios["new_goal_timeline"],
                portfolios["edit_rewritten_goals"],
                portfolios["edit_strategy_recommendation"],
                portfolios["edit_portfolio_active"],
                portfolios["llm_timestamp_label"],
                portfolios["llm_answers"],
                portfolios["llm_questions"],
                portfolios["chat_column"],
                portfolios["ai_chat"],
                portfolios["portfolio_view_filter"],
                portfolios["portfolios_table"],
                portfolios["portfolio_assets_table"],
            ],
        )
        mode_toggle.change(
            fn=data_entry_mode_changed,
            inputs=[mode_toggle],
            outputs=[
                data_entry["txns_table"],
                data_entry["account_choice"],
                data_entry["portfolio_choice"],
                data_entry["transfer_source_account"],
                data_entry["transfer_target_account"],
            ],
        )
        mode_toggle.change(
            fn=_export_scope_changed,
            inputs=[mode_toggle],
            outputs=[import_export["export_portfolio_filter"]],
        )
        reporting_currency.change(
            fn=refresh_dashboard,
            inputs=[
                mode_toggle,
                reporting_currency,
                dashboard_portfolio_filter,
                positions_account_filter,
                positions_portfolio_filter,
                positions_asset_class_filter,
            ],
            outputs=[
                mode_banner_html,
                dashboard["summary_table"],
                dashboard["positions_table"],
                dashboard["asset_allocation_plot"],
                dashboard["currency_allocation_plot"],
            ],
        )
        dashboard_portfolio_filter.change(
            fn=dashboard_portfolio_scope_changed,
            inputs=[mode_toggle, reporting_currency, dashboard_portfolio_filter],
            outputs=[
                positions_account_filter,
                positions_portfolio_filter,
                positions_asset_class_filter,
                mode_banner_html,
                dashboard["summary_table"],
                dashboard["positions_table"],
                dashboard["asset_allocation_plot"],
                dashboard["currency_allocation_plot"],
            ],
        )
        positions_account_filter.change(
            fn=dashboard_position_account_changed,
            inputs=[
                mode_toggle,
                reporting_currency,
                dashboard_portfolio_filter,
                positions_account_filter,
            ],
            outputs=[
                positions_portfolio_filter,
                positions_asset_class_filter,
                dashboard["positions_table"],
            ],
        )
        positions_portfolio_filter.change(
            fn=dashboard_position_portfolio_changed,
            inputs=[
                mode_toggle,
                reporting_currency,
                dashboard_portfolio_filter,
                positions_account_filter,
                positions_portfolio_filter,
            ],
            outputs=[
                positions_asset_class_filter,
                dashboard["positions_table"],
            ],
        )
        positions_asset_class_filter.change(
            fn=dashboard_positions,
            inputs=[
                mode_toggle,
                reporting_currency,
                dashboard_portfolio_filter,
                positions_account_filter,
                positions_portfolio_filter,
                positions_asset_class_filter,
            ],
            outputs=[dashboard["positions_table"]],
        )

    return app


def main() -> None:
    initialize_database()
    launch_kwargs: dict[str, str] = {}
    if APP_FAVICON_PATH.exists():
        launch_kwargs["favicon_path"] = str(APP_FAVICON_PATH)
    build_app().launch(**launch_kwargs)



if __name__ == "__main__":
    main()
