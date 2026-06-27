from __future__ import annotations

from typing import Any

import gradio as gr
import pandas as pd

from portfolio_management.services.accounts import (
    account_choices,
    create_portfolio,
    list_portfolios,
    parse_choice_id,
    portfolio_goal_choices,
    portfolio_goal_type_choices,
    portfolio_choices_for_account,
    portfolio_details,
    portfolio_timeline_choices,
    update_portfolio,
)
from portfolio_management.services.analysis_filters import account_mode_to_table_filter
from portfolio_management.services.analytics import ALL_ACCOUNTS_MODE, LIVE_MODE, current_positions
from portfolio_management.services.portfolio_recommendations import (
    generate_and_store_portfolio_recommendation,
    start_portfolio_goal_conversation,
)
from portfolio_management.tabs._shared import (
    format_integer_with_commas,
    format_two_decimals,
    portfolio_link,
    ticker_link,
)


ALL_MASTER_PORTFOLIOS = "All Portfolios"


def create_portfolio_callback(
    account_choice: str,
    portfolio_name: str,
    description: str,
    portfolio_url: str,
    portfolio_goals: list[str] | None,
    goal_type: str,
    goal_timeline: str,
    account_mode: str = LIVE_MODE,
    portfolio_view_choice: str | int | None = None,
) -> tuple[Any, ...]:
    portfolios_filter = account_mode_to_table_filter(account_mode)
    try:
        status = create_portfolio(
            account_choice=account_choice,
            portfolio_name=portfolio_name,
            description=description,
            portfolio_url=portfolio_url,
            portfolio_goals=portfolio_goals,
            goal_type=goal_type,
            goal_timeline=goal_timeline,
        )
    except Exception as exc:
        choices = portfolio_view_choices_for_mode(account_mode)
        return (
            f"Could not create portfolio: {exc}",
            gr.update(),
            gr.update(),
            gr.update(),
            gr.update(choices=choices, value=portfolio_view_choice),
            portfolios_table_data(account_mode, portfolio_view_choice),
            portfolio_assets_table_data(portfolio_view_choice),
        )

    accounts = account_choices(include_simulated=True, account_mode=account_mode)
    portfolios = portfolio_choices_for_account(account_choice)
    selected_portfolio = next(
        (choice for choice in portfolios if f"| {portfolio_name}" in choice),
        portfolios[0] if portfolios else None,
    )
    choices = portfolio_view_choices_for_mode(account_mode)
    selected_view = _portfolio_view_choice_for_id(
        choices,
        parse_choice_id(selected_portfolio),
    )
    return (
        status,
        gr.update(choices=accounts, value=account_choice),
        gr.update(choices=accounts, value=account_choice),
        gr.update(choices=portfolios, value=selected_portfolio),
        gr.update(choices=choices, value=selected_view),
        portfolios_table_data(account_mode, selected_view),
        portfolio_assets_table_data(selected_view),
    )


def _portfolio_name_from_choice(portfolio_choice: str | int | None) -> str:
    if portfolio_choice in (None, "", ALL_MASTER_PORTFOLIOS):
        return ""
    raw_name = str(portfolio_choice).split("|", maxsplit=1)[-1].strip()
    return raw_name.removesuffix(" [DISABLED]").strip()


def _portfolio_name_choices_for_account(account_choice: str | int | None) -> list[str]:
    return [
        _portfolio_name_from_choice(choice)
        for choice in portfolio_choices_for_account(account_choice, include_inactive=True)
    ]


def _portfolio_choice_for_name(
    account_choice: str | int | None,
    portfolio_name: str | None,
) -> str | None:
    clean_name = (portfolio_name or "").strip()
    if not clean_name:
        return None
    for choice in portfolio_choices_for_account(account_choice, include_inactive=True):
        if _portfolio_name_from_choice(choice) == clean_name:
            return choice
    return None


def _portfolio_form_details(portfolio_choice: str | int | None) -> tuple[Any, ...]:
    name, description, url, goals, goal_type, timeline, rewritten, recommendation, active = (
        portfolio_details(portfolio_choice)
    )
    return (
        gr.update(value=name),
        portfolio_choice,
        description,
        url,
        goals,
        goal_type,
        timeline,
        rewritten,
        recommendation,
        active,
    )


def _blank_portfolio_form() -> tuple[Any, ...]:
    return (
        gr.update(),
        None,
        gr.update(),
        gr.update(),
        gr.update(),
        gr.update(),
        gr.update(),
        gr.update(value=""),
        gr.update(value=""),
        True,
    )


def _portfolio_account_changed(account_choice: str | int | None) -> tuple[Any, ...]:
    names = _portfolio_name_choices_for_account(account_choice)
    selected_name = names[0] if names else None
    selected_choice = _portfolio_choice_for_name(account_choice, selected_name)
    details = (
        _portfolio_form_details(selected_choice)
        if selected_choice
        else _blank_portfolio_form()
    )
    return (
        gr.update(choices=names, value=selected_name),
        *details[1:],
        start_portfolio_goal_conversation(selected_choice),
    )


def _portfolio_name_changed(
    account_choice: str | int | None,
    portfolio_name: str,
) -> tuple[Any, ...]:
    portfolio_choice = _portfolio_choice_for_name(account_choice, portfolio_name)
    if portfolio_choice is None:
        return (*_blank_portfolio_form()[1:], "Select or save a portfolio first.")
    return (
        *_portfolio_form_details(portfolio_choice)[1:],
        start_portfolio_goal_conversation(portfolio_choice),
    )


def save_portfolio_callback(
    portfolio_choice: str | int | None,
    account_choice: str,
    portfolio_name: str,
    description: str,
    portfolio_url: str,
    portfolio_goals: list[str] | None,
    goal_type: str,
    goal_timeline: str,
    is_active: bool,
    account_mode: str = LIVE_MODE,
    portfolio_view_choice: str | int | None = None,
) -> tuple[Any, ...]:
    portfolio_id = parse_choice_id(portfolio_choice)
    try:
        if portfolio_id is None:
            status = create_portfolio(
                account_choice=account_choice,
                portfolio_name=portfolio_name,
                description=description,
                portfolio_url=portfolio_url,
                portfolio_goals=portfolio_goals,
                goal_type=goal_type,
                goal_timeline=goal_timeline,
            )
        else:
            status = update_portfolio(
                portfolio_choice=portfolio_choice,
                portfolio_name=portfolio_name,
                description=description,
                portfolio_url=portfolio_url,
                portfolio_goals=portfolio_goals,
                goal_type=goal_type,
                goal_timeline=goal_timeline,
                is_active=is_active,
            )
    except Exception as exc:
        status = f"Could not save portfolio: {exc}"

    names = _portfolio_name_choices_for_account(account_choice)
    selected_choice = _portfolio_choice_for_name(account_choice, portfolio_name)
    choices = portfolio_view_choices_for_mode(account_mode)
    selected_view = _portfolio_view_choice_for_id(
        choices,
        parse_choice_id(selected_choice) or _parse_portfolio_view_id(portfolio_view_choice),
    )
    account_options = account_choices(include_simulated=True, account_mode=account_mode)
    account_update = gr.update(choices=account_options, value=account_choice)
    account_portfolios = portfolio_choices_for_account(account_choice)
    selected_portfolio = selected_choice if selected_choice in account_portfolios else (
        account_portfolios[0] if account_portfolios else None
    )
    return (
        status,
        account_update,
        account_update,
        gr.update(choices=account_portfolios, value=selected_portfolio),
        gr.update(choices=names, value=portfolio_name),
        selected_choice,
        start_portfolio_goal_conversation(selected_choice),
        gr.update(choices=choices, value=selected_view),
        portfolios_table_data(account_mode, selected_view),
        portfolio_assets_table_data(selected_view),
    )


def portfolio_view_choices_for_mode(account_mode: str = LIVE_MODE) -> list[str]:
    portfolios_filter = account_mode_to_table_filter(account_mode)
    portfolios = list_portfolios(portfolios_filter)
    choices = [ALL_MASTER_PORTFOLIOS]
    if not isinstance(portfolios, pd.DataFrame):
        return choices
    for _, row in portfolios.iterrows():
        choices.append(
            f"{row['ID']} | {row['Broker']} / {row['Account']} / {row['Portfolio']}"
        )
    return choices


def portfolio_view_choices(account_filter: str = "Real") -> list[str]:
    portfolios = list_portfolios(account_filter)
    choices = [ALL_MASTER_PORTFOLIOS]
    if not isinstance(portfolios, pd.DataFrame):
        return choices
    for _, row in portfolios.iterrows():
        choices.append(
            f"{row['ID']} | {row['Broker']} / {row['Account']} / {row['Portfolio']}"
        )
    return choices


def portfolios_table_data(
    account_mode: str = LIVE_MODE,
    portfolio_view_choice: str | int | None = None,
) -> object:
    portfolios_filter = account_mode_to_table_filter(account_mode)
    portfolios = list_portfolios(portfolios_filter)
    portfolio_id = _parse_portfolio_view_id(portfolio_view_choice)
    if (
        portfolio_id is not None
        and isinstance(portfolios, pd.DataFrame)
        and "ID" in portfolios.columns
    ):
        portfolios = portfolios[portfolios["ID"] == portfolio_id].copy()
    if isinstance(portfolios, pd.DataFrame) and "Portfolio" in portfolios.columns:
        if "Portfolio URL" in portfolios.columns:
            portfolios["Portfolio"] = portfolios.apply(
                lambda row: portfolio_link(row["Portfolio"], row["Portfolio URL"]),
                axis=1,
            )
        portfolios = portfolios.drop(columns=["Portfolio URL"], errors="ignore")
    return portfolios


def portfolio_assets_table_data(
    portfolio_view_choice: str | int | None = None,
) -> object:
    columns = [
        "Ticker",
        "Asset",
        "Asset Class",
        "Volume",
        "Price",
        "Value",
        "Currency",
        "Portfolio Description",
    ]
    portfolio_id = _parse_portfolio_view_id(portfolio_view_choice)
    if portfolio_id is None:
        return pd.DataFrame(columns=columns)

    positions = current_positions(
        account_mode=ALL_ACCOUNTS_MODE,
        portfolio_id=portfolio_id,
    ).copy()
    if positions.empty:
        return pd.DataFrame(columns=columns)

    _, description, *_rest = portfolio_details(portfolio_id)
    assets = positions.rename(
        columns={
            "Name": "Asset",
            "Quantity": "Volume",
            "Latest Price": "Price",
            "Market Value": "Value",
        }
    )
    assets["Portfolio Description"] = description
    assets["Ticker"] = assets["Ticker"].map(ticker_link)
    assets["Volume"] = assets["Volume"].map(format_integer_with_commas)
    for column in ["Price", "Value"]:
        assets[column] = assets[column].map(format_two_decimals)
    return assets[columns]


def _parse_portfolio_view_id(
    portfolio_view_choice: str | int | None,
) -> int | None:
    if portfolio_view_choice in (None, "", ALL_MASTER_PORTFOLIOS):
        return None
    return parse_choice_id(portfolio_view_choice)


def _portfolio_view_choice_for_id(
    choices: list[str],
    portfolio_id: int | None,
) -> str:
    if portfolio_id is None:
        return ALL_MASTER_PORTFOLIOS
    prefix = f"{portfolio_id} |"
    return next(
        (choice for choice in choices if choice.startswith(prefix)),
        ALL_MASTER_PORTFOLIOS,
    )


def _portfolio_scope_changed(account_mode: str) -> tuple[Any, ...]:
    choices = portfolio_view_choices_for_mode(account_mode)
    return (
        gr.update(choices=choices, value=ALL_MASTER_PORTFOLIOS),
        portfolios_table_data(account_mode, ALL_MASTER_PORTFOLIOS),
        portfolio_assets_table_data(ALL_MASTER_PORTFOLIOS),
    )


def portfolios_mode_changed(account_mode: str) -> tuple[Any, ...]:
    accounts = account_choices(include_simulated=True, account_mode=account_mode)
    selected_account = accounts[0] if accounts else None
    portfolio_names = _portfolio_name_choices_for_account(selected_account)
    selected_name = portfolio_names[0] if portfolio_names else None
    selected_choice = _portfolio_choice_for_name(selected_account, selected_name)
    details = (
        _portfolio_form_details(selected_choice)
        if selected_choice
        else _blank_portfolio_form()
    )
    choices = portfolio_view_choices_for_mode(account_mode)
    return (
        gr.update(choices=accounts, value=selected_account),
        gr.update(choices=portfolio_names, value=selected_name),
        *details[1:],
        start_portfolio_goal_conversation(selected_choice),
        gr.update(choices=choices, value=ALL_MASTER_PORTFOLIOS),
        portfolios_table_data(account_mode, ALL_MASTER_PORTFOLIOS),
        portfolio_assets_table_data(ALL_MASTER_PORTFOLIOS),
    )


def _portfolio_view_changed(
    account_mode: str,
    portfolio_view_choice: str | int | None,
) -> tuple[Any, ...]:
    return (
        portfolios_table_data(account_mode, portfolio_view_choice),
        portfolio_assets_table_data(portfolio_view_choice),
    )


def _refresh_portfolio_view(
    account_mode: str,
    portfolio_view_choice: str | int | None,
) -> tuple[Any, ...]:
    choices = portfolio_view_choices_for_mode(account_mode)
    selected_view = _portfolio_view_choice_for_id(
        choices,
        _parse_portfolio_view_id(portfolio_view_choice),
    )
    return (
        gr.update(choices=choices, value=selected_view),
        portfolios_table_data(account_mode, selected_view),
        portfolio_assets_table_data(selected_view),
    )


def _get_llm_recommendation(
    portfolio_choice: str | int | None,
    user_answers: str,
    account_mode: str,
    portfolio_view_choice: str | int | None,
) -> tuple[Any, ...]:
    try:
        status, rewritten_goals, recommendation = generate_and_store_portfolio_recommendation(
            portfolio_choice,
            user_answers,
        )
    except Exception as exc:
        status = f"Could not get LLM recommendation: {exc}"
        rewritten_goals = ""
        recommendation = ""
    return (
        status,
        rewritten_goals,
        recommendation,
        portfolios_table_data(account_mode, portfolio_view_choice),
    )


def build_portfolios_tab(selected_account: str | None, mode_toggle: gr.Radio) -> dict[str, Any]:
    with gr.Tab("Portfolios"):
        portfolio_status = gr.Textbox(label="Status", interactive=False)
        initial_portfolio_names = _portfolio_name_choices_for_account(selected_account)
        initial_portfolio_name = initial_portfolio_names[0] if initial_portfolio_names else ""
        initial_portfolio_choice = _portfolio_choice_for_name(
            selected_account,
            initial_portfolio_name,
        )
        (
            _name_update,
            _state_value,
            initial_description,
            initial_url,
            initial_goals,
            initial_goal_type,
            initial_timeline,
            initial_rewritten_goals,
            initial_strategy_recommendation,
            initial_active,
        ) = _portfolio_form_details(initial_portfolio_choice)
        selected_portfolio_state = gr.State(initial_portfolio_choice)

        with gr.Row():
            portfolio_account_choice = gr.Dropdown(
                label="Account",
                choices=account_choices(include_simulated=True, account_mode=LIVE_MODE),
                value=selected_account,
            )
            new_portfolio_name = gr.Dropdown(
                label="Portfolio",
                choices=initial_portfolio_names,
                value=initial_portfolio_name,
                allow_custom_value=True,
                filterable=True,
            )
            new_portfolio_url = gr.Textbox(
                label="Portfolio URL",
                value=initial_url,
                placeholder="https://",
            )
        new_portfolio_description = gr.Textbox(
            label="Description",
            value=initial_description,
            lines=3,
        )
        with gr.Row():
            new_portfolio_goals = gr.CheckboxGroup(
                label="Portfolio Goals",
                choices=portfolio_goal_choices(),
                value=initial_goals,
            )
            new_goal_type = gr.Dropdown(
                label="Goal Type",
                choices=portfolio_goal_type_choices(),
                value=initial_goal_type or None,
            )
            new_goal_timeline = gr.Dropdown(
                label="Timeline",
                choices=portfolio_timeline_choices(),
                value=initial_timeline or None,
            )
            edit_portfolio_active = gr.Checkbox(label="Active", value=initial_active)
        create_portfolio_button = gr.Button("Save Portfolio", variant="primary")

        edit_rewritten_goals = gr.Textbox(
            label="LLM Rewritten Goals",
            value=initial_rewritten_goals,
            lines=4,
            interactive=False,
        )
        edit_strategy_recommendation = gr.Textbox(
            label="LLM Strategy Recommendation",
            value=initial_strategy_recommendation,
            lines=6,
            interactive=False,
        )

        llm_questions = gr.Textbox(
            label="LLM Portfolio Profile",
            value=start_portfolio_goal_conversation(initial_portfolio_choice),
            lines=8,
            interactive=False,
        )
        llm_answers = gr.Textbox(label="Optional LLM Notes", lines=4)
        with gr.Row():
            start_llm_button = gr.Button("Start LLM Conversation")
            get_llm_recommendation_button = gr.Button("Get LLM Recommendation")

        with gr.Row():
            portfolio_view_filter = gr.Dropdown(
                label="Portfolio",
                choices=portfolio_view_choices_for_mode(LIVE_MODE),
                value=ALL_MASTER_PORTFOLIOS,
                allow_custom_value=False,
                filterable=True,
            )
        portfolios_table = gr.Dataframe(
            value=lambda: portfolios_table_data(LIVE_MODE),
            headers=[
                "ID",
                "Broker",
                "Account",
                "Portfolio",
                "Description",
                "Goals",
                "Goal Type",
                "Timeline",
                "Rewritten Goals",
                "Strategy Recommendation",
                "Currency",
                "Simulated Account",
                "Active",
            ],
            datatype=[
                "number",
                "str",
                "str",
                "markdown",
                "str",
                "str",
                "str",
                "str",
                "str",
                "str",
                "str",
                "str",
                "str",
            ],
            label="Portfolios",
            interactive=False,
        )
        portfolio_assets_table = gr.Dataframe(
            value=portfolio_assets_table_data,
            headers=[
                "Ticker",
                "Asset",
                "Asset Class",
                "Volume",
                "Price",
                "Value",
                "Currency",
                "Portfolio Description",
            ],
            datatype=[
                "markdown",
                "str",
                "str",
                "str",
                "str",
                "str",
                "str",
                "str",
            ],
            label="Portfolio Assets",
            interactive=False,
        )
        refresh_portfolios_button = gr.Button("Refresh Portfolios")

        portfolio_account_choice.change(
            fn=_portfolio_account_changed,
            inputs=[portfolio_account_choice],
            outputs=[
                new_portfolio_name,
                selected_portfolio_state,
                new_portfolio_description,
                new_portfolio_url,
                new_portfolio_goals,
                new_goal_type,
                new_goal_timeline,
                edit_rewritten_goals,
                edit_strategy_recommendation,
                edit_portfolio_active,
                llm_questions,
            ],
        )
        new_portfolio_name.change(
            fn=_portfolio_name_changed,
            inputs=[portfolio_account_choice, new_portfolio_name],
            outputs=[
                selected_portfolio_state,
                new_portfolio_description,
                new_portfolio_url,
                new_portfolio_goals,
                new_goal_type,
                new_goal_timeline,
                edit_rewritten_goals,
                edit_strategy_recommendation,
                edit_portfolio_active,
                llm_questions,
            ],
        )
        start_llm_button.click(
            fn=start_portfolio_goal_conversation,
            inputs=[selected_portfolio_state],
            outputs=[llm_questions],
        )
        get_llm_recommendation_button.click(
            fn=_get_llm_recommendation,
            inputs=[
                selected_portfolio_state,
                llm_answers,
                mode_toggle,
                portfolio_view_filter,
            ],
            outputs=[
                portfolio_status,
                edit_rewritten_goals,
                edit_strategy_recommendation,
                portfolios_table,
            ],
        )
        refresh_portfolios_button.click(
            fn=_refresh_portfolio_view,
            inputs=[mode_toggle, portfolio_view_filter],
            outputs=[
                portfolio_view_filter,
                portfolios_table,
                portfolio_assets_table,
            ],
        )
        portfolio_view_filter.change(
            fn=_portfolio_view_changed,
            inputs=[mode_toggle, portfolio_view_filter],
            outputs=[portfolios_table, portfolio_assets_table],
        )

    return {
        "portfolio_status": portfolio_status,
        "portfolio_account_choice": portfolio_account_choice,
        "new_portfolio_name": new_portfolio_name,
        "new_portfolio_url": new_portfolio_url,
        "new_portfolio_description": new_portfolio_description,
        "new_portfolio_goals": new_portfolio_goals,
        "new_goal_type": new_goal_type,
        "new_goal_timeline": new_goal_timeline,
        "edit_portfolio_choice": selected_portfolio_state,
        "edit_portfolio_active": edit_portfolio_active,
        "edit_rewritten_goals": edit_rewritten_goals,
        "edit_strategy_recommendation": edit_strategy_recommendation,
        "llm_questions": llm_questions,
        "create_portfolio_button": create_portfolio_button,
        "portfolio_view_filter": portfolio_view_filter,
        "portfolios_table": portfolios_table,
        "portfolio_assets_table": portfolio_assets_table,
        "refresh_portfolios_button": refresh_portfolios_button,
    }
