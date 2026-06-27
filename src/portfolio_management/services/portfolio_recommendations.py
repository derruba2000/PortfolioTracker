from __future__ import annotations

import json
from typing import Any

import pandas as pd
import requests
from sqlalchemy import bindparam, inspect, select, text

from portfolio_management.config import load_settings
from portfolio_management.db.models import Portfolio, Security, Transaction
from portfolio_management.db.session import get_engine, get_session_factory
from portfolio_management.services.accounts import portfolio_details, store_portfolio_recommendation


YAHOO_CONTEXT_TABLES = {
    "analyst_targets": "yahoo_analyst_targets",
    "calendar_events": "yahoo_calendar_events",
    "financial_facts": "yahoo_financial_facts",
    "fund_asset_allocation": "yahoo_fund_asset_allocation",
    "fund_holdings": "yahoo_fund_holdings",
    "fund_metrics": "yahoo_fund_metrics",
    "fund_performance": "yahoo_fund_performance",
    "fund_profiles": "yahoo_fund_profiles",
    "fund_sector_weightings": "yahoo_fund_sector_weightings",
    "option_contracts": "yahoo_option_contracts",
    "security_info": "yahoo_security_info",
}


def start_portfolio_goal_conversation(portfolio_choice: str | int | None = None) -> str:
    name, description, _url, goals, goal_type, timeline, _rewritten, _recommendation, _profile, _ai_notes, _llm_ts, active = (
        portfolio_details(portfolio_choice)
    )
    if not name:
        return "Select or save a portfolio first. Optional notes can include risk tolerance, drawdown limits, sectors to avoid, or currency preferences."

    goals_text = ", ".join(goals) if goals else "None"
    active_text = "Yes" if active else "No"
    return f"""Saved portfolio profile:
Name: {name}
Active: {active_text}
Description: {description or "None"}
Goals: {goals_text}
Goal type: {goal_type or "None"}
Timeline: {timeline or "None"}

Optional notes:
Add anything not already captured above, such as risk tolerance, drawdown limits, sectors to avoid, or currency preferences. Otherwise click Get LLM Recommendation using the saved profile.
"""


def start_ai_conversation(portfolio_choice: str | int | None = None) -> str:
    name, description, _url, goals, goal_type, timeline, _rewritten, _recommendation, _profile, _ai_notes, _llm_ts, active = (
        portfolio_details(portfolio_choice)
    )
    if not name:
        return "Select or save a portfolio first before starting an AI conversation."

    symbols = _portfolio_symbols(portfolio_choice)

    context_parts = [f"Portfolio name: {name}", f"Active: {'Yes' if active else 'No'}"]
    if description:
        context_parts.append(f"Description: {description}")
    if goals:
        context_parts.append(f"Goals: {', '.join(goals)}")
    if goal_type:
        context_parts.append(f"Goal type: {goal_type}")
    if timeline:
        context_parts.append(f"Timeline: {timeline}")
    context_parts.append(
        f"Current holdings: {', '.join(symbols)}" if symbols else "Current holdings: None (new portfolio)"
    )

    context = "\n".join(context_parts)
    prompt = f"""You are an investment portfolio advisor reviewing a client profile. Based on the information below, identify 3-5 specific questions you need answered to make a personalised strategy recommendation. Only ask about information that is missing or unclear from the data below. Be direct and concise.

Client portfolio profile:
{context}

Return a numbered list of questions only, with no introduction or closing remarks."""

    try:
        return _call_ollama(prompt)
    except ValueError as exc:
        return f"Could not generate questions: {exc}"


def start_ai_chat(portfolio_choice: str | int | None = None) -> list[dict[str, str]]:
    """Begin a fresh AI advising chat. Returns the initial message list with the advisor's opening questions."""
    name, description, _url, goals, goal_type, timeline, rewritten, recommendation, _profile, _ai_notes, _llm_ts, active = (
        portfolio_details(portfolio_choice)
    )
    if not name:
        return [{"role": "assistant", "content": "Select or save a portfolio first before starting an AI conversation."}]

    symbols = _portfolio_symbols(portfolio_choice)

    context_parts = [f"Portfolio: {name}", f"Active: {'Yes' if active else 'No'}"]
    if description:
        context_parts.append(f"Description: {description}")
    if goals:
        context_parts.append(f"Goals: {', '.join(goals)}")
    if goal_type:
        context_parts.append(f"Goal type: {goal_type}")
    if timeline:
        context_parts.append(f"Timeline: {timeline}")
    context_parts.append(
        f"Current holdings: {', '.join(symbols)}" if symbols else "Current holdings: None (new portfolio)"
    )

    previous_ai_section = ""
    if recommendation:
        previous_ai_section = (
            f"\n\nThis portfolio already has AI analysis on file. The client may want to refine or update it:\n"
            f"Previous rewritten goals: {rewritten or 'None'}\n"
            f"Previous recommendation (excerpt): {recommendation[:400]}"
        )

    context = "\n".join(context_parts)
    prompt = (
        f"You are an investment portfolio advisor starting a conversation with a client. "
        f"Based on the portfolio profile below, ask 3 to 5 focused questions to gather the information needed "
        f"for a personalised strategy recommendation. Only ask about what is missing or unclear. "
        f"Be direct and conversational. Do not use markdown formatting, bullet symbols, or bold text.\n\n"
        f"Client portfolio profile:\n{context}{previous_ai_section}\n\n"
        f"Write a brief warm opening sentence, then list your numbered questions."
    )

    try:
        opening = _call_ollama(prompt)
        return [{"role": "assistant", "content": opening}]
    except ValueError as exc:
        return [{"role": "assistant", "content": f"Could not start AI conversation: {exc}"}]


def continue_ai_chat(
    portfolio_choice: str | int | None,
    history: list[dict[str, str]],
    user_message: str,
) -> list[dict[str, str]]:
    """Append the user message, call the LLM for a follow-up, and return the updated history."""
    updated: list[dict[str, str]] = list(history) + [{"role": "user", "content": user_message}]

    name, description, _url, goals, *_rest = portfolio_details(portfolio_choice)
    portfolio_label = name or "the selected portfolio"

    conversation_text = "\n\n".join(
        f"{'Client' if msg['role'] == 'user' else 'Advisor'}: {msg['content']}"
        for msg in updated
    )

    prompt = (
        f"You are an investment portfolio advisor in an ongoing conversation about {portfolio_label}.\n\n"
        f"Conversation so far:\n{conversation_text}\n\n"
        f"Continue the conversation. If you still need more information to make a good recommendation, "
        f"ask one or two focused follow-up questions. If you have enough context, acknowledge this and "
        f"let the client know they can click Get AI Recommendations. "
        f"Keep your response concise. Do not use markdown formatting, bullet symbols, or bold text."
    )

    try:
        response = _call_ollama(prompt)
    except ValueError as exc:
        response = f"Error getting response: {exc}"

    return updated + [{"role": "assistant", "content": response}]


def generate_and_store_portfolio_recommendation(
    portfolio_choice: str | int | None,
    chat_history: list[dict[str, str]],
    post: Any = requests.post,
) -> tuple[str, str, str, str]:
    chat_text = _chat_history_to_text(chat_history)
    if not chat_text:
        name, description, _url, goals, goal_type, timeline, *_rest = portfolio_details(
            portfolio_choice
        )
        if not any([description, goals, goal_type, timeline]):
            raise ValueError(
                "Add a portfolio description, goals, goal type, or timeline before requesting a recommendation."
            )
        chat_text = f"Use the saved portfolio profile for {name or 'this portfolio'}."

    prompt = _build_prompt(portfolio_choice, chat_text)
    recommendation = _call_ollama(prompt, post=post)
    rewritten_goals = _extract_section(recommendation, "Rewritten goals") or _fallback_rewritten_goals(
        portfolio_choice,
        chat_text,
    )
    profile = _extract_section(recommendation, "Portfolio profile") or start_portfolio_goal_conversation(portfolio_choice)
    status = store_portfolio_recommendation(
        portfolio_choice,
        rewritten_goals=rewritten_goals,
        strategy_recommendation=recommendation,
        portfolio_profile=profile,
        ai_notes=chat_text,
    )
    return status, rewritten_goals, recommendation, profile


def _call_ollama(prompt: str, post: Any = requests.post) -> str:
    settings = load_settings()
    url = f"{settings.ollama_base_url}/api/generate"
    payload = {
        "model": settings.ollama_model,
        "prompt": prompt,
        "stream": False,
    }
    try:
        response = post(url, json=payload, timeout=settings.ollama_timeout_seconds)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise ValueError(f"Ollama recommendation failed: {exc}") from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise ValueError("Ollama returned invalid JSON.") from exc

    recommendation = str(data.get("response", "")).strip()
    if not recommendation:
        raise ValueError("Ollama returned an empty recommendation.")
    return recommendation


def _build_prompt(portfolio_choice: str | int | None, chat_context: str) -> str:
    name, description, _url, goals, goal_type, timeline, rewritten, recommendation, _profile, _ai_notes, _llm_ts, active = (
        portfolio_details(portfolio_choice)
    )
    symbols = _portfolio_symbols(portfolio_choice)
    yahoo_context = _yahoo_context(symbols)
    analysis_mode = (
        "Existing holdings review. Consider current symbols and any local market/fund/security context."
        if symbols
        else (
            "New portfolio allocation design. There are no holdings yet, so recommend a target "
            "asset allocation from scratch using the selected goals, goal type, timeline, and "
            "user answers. Do not require tickers to be present before proposing the allocation."
        )
    )
    previous_ai_section = ""
    if recommendation:
        previous_ai_section = f"""
Previous AI analysis on file:
Rewritten goals: {rewritten or "None"}
Previous recommendation: {recommendation}
"""
    return f"""
You are an investment portfolio strategy assistant. This is analysis support, not financial advice.
Do not use markdown formatting, bullet symbols, asterisks, or bold text in your response. Write in plain prose.

Portfolio:
- Name: {name or "Unknown"}
- Active: {"Yes" if active else "No"}
- Description: {description or "None"}
- Selected goals: {", ".join(goals) if goals else "None"}
- Goal type: {goal_type or "None"}
- Timeline: {timeline or "None"}
- Current symbols: {", ".join(symbols) if symbols else "None"}
- Analysis mode: {analysis_mode}
{previous_ai_section}
Conversation with client:
{chat_context}

Available market/fund/security context from the local database:
{json.dumps(yahoo_context, indent=2, default=str)}

Write a plain-text response with each of these headings on its own line followed by the content:
Rewritten goals:
Portfolio profile:
Recommended strategy:
Suggested asset allocation:
Why:
Risks and caveats:
""".strip()


def _chat_history_to_text(history: list[dict[str, str]]) -> str:
    """Convert a Gradio-format chat history to a readable plain-text conversation string."""
    if not history:
        return ""
    lines = []
    for msg in history:
        role = "Client" if msg.get("role") == "user" else "AI Advisor"
        lines.append(f"{role}: {msg.get('content', '')}")
    return "\n\n".join(lines)


def _portfolio_symbols(portfolio_choice: str | int | None) -> list[str]:
    from portfolio_management.services.accounts import parse_choice_id

    portfolio_id = parse_choice_id(portfolio_choice)
    if portfolio_id is None:
        return []

    session_factory = get_session_factory()
    with session_factory() as session:
        rows = session.scalars(
            select(Security.ticker)
            .join(Transaction, Transaction.security_id == Security.id)
            .join(Portfolio, Portfolio.id == Transaction.portfolio_id)
            .where(Portfolio.id == portfolio_id)
            .order_by(Security.ticker)
            .distinct()
        ).all()
    return [str(row) for row in rows]


def _yahoo_context(symbols: list[str]) -> dict[str, list[dict[str, Any]]]:
    if not symbols:
        return {}
    engine = get_engine()
    existing_tables = set(inspect(engine).get_table_names())
    context: dict[str, list[dict[str, Any]]] = {}
    with engine.connect() as connection:
        for key, table in YAHOO_CONTEXT_TABLES.items():
            if table not in existing_tables:
                continue
            statement = text(
                f'SELECT * FROM "{table}" WHERE symbol IN :symbols LIMIT 20'
            ).bindparams(bindparam("symbols", expanding=True))
            dataframe = pd.read_sql_query(
                statement,
                connection,
                params={"symbols": tuple(symbols)},
            )
            if not dataframe.empty:
                context[key] = dataframe.fillna("").to_dict("records")
    return context


def _extract_section(text_value: str, heading: str) -> str:
    lines = text_value.splitlines()
    collecting = False
    collected: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.lower().rstrip(":") == heading.lower():
            collecting = True
            continue
        if collecting and stripped.endswith(":"):
            break
        if collecting:
            collected.append(line)
    return "\n".join(collected).strip()


def _fallback_rewritten_goals(portfolio_choice: str | int | None, chat_context: str) -> str:
    _name, _description, _url, goals, goal_type, timeline, _rewritten, _recommendation, _profile, _ai_notes, _llm_ts, _active = (
        portfolio_details(portfolio_choice)
    )
    parts = []
    if goals:
        parts.append(f"Selected goals: {', '.join(goals)}")
    if goal_type:
        parts.append(f"Goal type: {goal_type}")
    if timeline:
        parts.append(f"Timeline: {timeline}")
    parts.append(f"User objectives from conversation: {chat_context}")
    return "\n".join(parts)
