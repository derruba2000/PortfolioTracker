from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from portfolio_management.db.base import Base
from portfolio_management.services.accounts import (
    create_portfolio,
    get_or_create_account,
    get_or_create_broker,
    portfolio_details,
)
from portfolio_management.config import Settings
from portfolio_management.services.portfolio_recommendations import (
    _build_prompt,
    _call_llm,
    generate_and_store_portfolio_recommendation,
    start_portfolio_goal_conversation,
)


class _Response:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, str]:
        return {
            "response": (
                "Rewritten goals:\n"
                "Retirement growth with controlled drawdowns.\n"
                "Recommended strategy:\n"
                "Use a balanced growth allocation."
            )
        }


class _NvidiaResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, list[dict[str, dict[str, str]]]]:
        return {"choices": [{"message": {"content": "NVIDIA recommendation"}}]}


def test_generate_and_store_portfolio_recommendation(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    monkeypatch.setattr(
        "portfolio_management.services.accounts.get_session_factory",
        lambda: factory,
    )
    monkeypatch.setattr(
        "portfolio_management.services.portfolio_recommendations.get_session_factory",
        lambda: factory,
    )
    monkeypatch.setattr(
        "portfolio_management.services.portfolio_recommendations.get_engine",
        lambda: engine,
    )

    with Session(engine) as session:
        broker = get_or_create_broker(session, "Broker")
        account = get_or_create_account(
            session=session,
            broker=broker,
            name="ISA",
            currency_code="GBP",
        )
        session.commit()
        account_choice = f"{account.id} | Broker / ISA"

    create_portfolio(
        account_choice=account_choice,
        portfolio_name="Retirement",
        portfolio_goals=["Retirement"],
        goal_type="Balanced",
        goal_timeline="10+ years",
    )

    status, rewritten_goals, recommendation, profile = generate_and_store_portfolio_recommendation(
        "1 | Broker / ISA / Retirement",
        [
            {"role": "assistant", "content": "What is your risk tolerance?"},
            {"role": "user", "content": "I want long-term growth and can tolerate moderate risk."},
        ],
        post=lambda *args, **kwargs: _Response(),
    )
    details = portfolio_details("1 | Broker / ISA / Retirement")

    assert "Stored AI insights" in status
    assert rewritten_goals == "Retirement growth with controlled drawdowns."
    assert "balanced growth allocation" in recommendation
    assert details[6] == rewritten_goals
    assert details[7] == recommendation
    assert details[8] == profile.strip()
    assert "long-term growth" in details[9]  # ai_notes contains serialised chat
    assert details[10] is not None  # llm_updated_at timestamp was set
    assert "risk tolerance" in start_portfolio_goal_conversation().lower()


def test_call_llm_uses_nvidia_nim_when_selected(monkeypatch) -> None:
    settings = Settings(
        database_path="/tmp/test.sqlite3",
        api_usage="NVIDIA",
        nvidia_api_key="nvapi-test-secret",
        nvidia_api_model="meta/llama-3.3-70b-instruct",
        nvidia_base_url="https://integrate.api.nvidia.com/v1",
        nvidia_verify_ssl=False,
    )
    monkeypatch.setattr(
        "portfolio_management.services.portfolio_recommendations.load_settings",
        lambda: settings,
    )
    calls = []

    def post(*args, **kwargs):
        calls.append((args, kwargs))
        return _NvidiaResponse()

    result = _call_llm("Assess this portfolio.", post=post)

    assert result == "NVIDIA recommendation"
    assert calls[0][0] == ("https://integrate.api.nvidia.com/v1/chat/completions",)
    assert calls[0][1]["headers"]["Authorization"] == "Bearer nvapi-test-secret"
    assert calls[0][1]["json"]["model"] == "meta/llama-3.3-70b-instruct"
    assert calls[0][1]["verify"] is False


def test_empty_portfolio_prompt_requests_target_asset_allocation(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    monkeypatch.setattr(
        "portfolio_management.services.accounts.get_session_factory",
        lambda: factory,
    )
    monkeypatch.setattr(
        "portfolio_management.services.portfolio_recommendations.get_session_factory",
        lambda: factory,
    )
    monkeypatch.setattr(
        "portfolio_management.services.portfolio_recommendations.get_engine",
        lambda: engine,
    )

    with Session(engine) as session:
        broker = get_or_create_broker(session, "Broker")
        account = get_or_create_account(
            session=session,
            broker=broker,
            name="ISA",
            currency_code="GBP",
        )
        session.commit()
        account_choice = f"{account.id} | Broker / ISA"

    create_portfolio(
        account_choice=account_choice,
        portfolio_name="Empty",
        portfolio_goals=["Capital Growth"],
        goal_type="Growth",
        goal_timeline="5-10 years",
    )

    prompt = _build_prompt(
        "1 | Broker / ISA / Empty",
        "Client: I want growth but no single-stock concentration.",
    )

    assert "Current symbols: None" in prompt
    assert "New portfolio allocation design" in prompt
    assert "recommend a target asset allocation from scratch" in prompt
    assert "Do not require tickers" in prompt
