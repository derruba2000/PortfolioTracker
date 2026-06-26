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


OLLAMA_QUESTIONS = """Please answer these questions, then click Get LLM Recommendation:

1. What is the main objective for this portfolio?
2. When do you expect to use the money?
3. How would you describe your risk tolerance?
4. What drawdown would make you uncomfortable?
5. Do you prefer income, growth, capital preservation, or a mix?
6. Are there assets, sectors, currencies, or regions you want to avoid or prefer?
"""

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


def start_portfolio_goal_conversation() -> str:
    return OLLAMA_QUESTIONS


def generate_and_store_portfolio_recommendation(
    portfolio_choice: str | int | None,
    user_answers: str,
    post: Any = requests.post,
) -> tuple[str, str, str]:
    clean_answers = (user_answers or "").strip()
    if not clean_answers:
        raise ValueError("Answer the LLM questions before requesting a recommendation.")

    prompt = _build_prompt(portfolio_choice, clean_answers)
    recommendation = _call_ollama(prompt, post=post)
    rewritten_goals = _extract_section(recommendation, "Rewritten goals") or _fallback_rewritten_goals(
        portfolio_choice,
        clean_answers,
    )
    status = store_portfolio_recommendation(
        portfolio_choice,
        rewritten_goals=rewritten_goals,
        strategy_recommendation=recommendation,
    )
    return status, rewritten_goals, recommendation


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


def _build_prompt(portfolio_choice: str | int | None, user_answers: str) -> str:
    name, description, _url, goals, goal_type, timeline, _rewritten, _recommendation, active = (
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
    return f"""
You are an investment portfolio strategy assistant. This is analysis support, not financial advice.

Portfolio:
- Name: {name or "Unknown"}
- Active: {"Yes" if active else "No"}
- Description: {description or "None"}
- Selected goals: {", ".join(goals) if goals else "None"}
- Goal type: {goal_type or "None"}
- Timeline: {timeline or "None"}
- Current symbols: {", ".join(symbols) if symbols else "None"}
- Analysis mode: {analysis_mode}

User answers:
{user_answers}

Available market/fund/security context from the local database:
{json.dumps(yahoo_context, indent=2, default=str)}

Return a concise response with these headings:
Rewritten goals:
Recommended strategy:
Suggested asset allocation:
Why:
Risks and caveats:
""".strip()


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


def _fallback_rewritten_goals(portfolio_choice: str | int | None, user_answers: str) -> str:
    _name, _description, _url, goals, goal_type, timeline, _rewritten, _recommendation, _active = (
        portfolio_details(portfolio_choice)
    )
    parts = []
    if goals:
        parts.append(f"Selected goals: {', '.join(goals)}")
    if goal_type:
        parts.append(f"Goal type: {goal_type}")
    if timeline:
        parts.append(f"Timeline: {timeline}")
    parts.append(f"User objectives: {user_answers}")
    return "\n".join(parts)
