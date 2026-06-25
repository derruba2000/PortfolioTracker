from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from portfolio_management.config import (
    DiscordWebhookConfigurationWarning,
    load_settings,
)
from portfolio_management.db.base import Base
from portfolio_management.db.models import PortfolioAlert


def test_missing_discord_webhook_warns_without_crashing(monkeypatch) -> None:
    monkeypatch.setattr("portfolio_management.config.load_dotenv", lambda: None)
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)

    with pytest.warns(
        DiscordWebhookConfigurationWarning,
        match="Discord notifications are disabled",
    ):
        settings = load_settings()

    assert settings.discord_webhook_url is None


def test_discord_webhook_requires_an_absolute_https_url(monkeypatch) -> None:
    monkeypatch.setattr("portfolio_management.config.load_dotenv", lambda: None)
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "http://discord.com/api/webhooks/1/token")

    with pytest.warns(
        DiscordWebhookConfigurationWarning,
        match="absolute HTTPS URL",
    ):
        settings = load_settings()

    assert settings.discord_webhook_url is None


def test_valid_discord_webhook_is_loaded(monkeypatch) -> None:
    webhook_url = "https://discord.com/api/webhooks/1/token"
    monkeypatch.setattr("portfolio_management.config.load_dotenv", lambda: None)
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", webhook_url)

    settings = load_settings()

    assert settings.discord_webhook_url == webhook_url


def test_portfolio_alert_schema_defaults_and_unique_hash() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)

    columns = {column["name"]: column for column in inspect(engine).get_columns("portfolio_alerts")}
    assert set(columns) == {
        "id",
        "alert_hash",
        "timestamp",
        "alert_type",
        "message",
        "is_acknowledged",
    }
    assert columns["is_acknowledged"]["default"] == "0"

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO portfolio_alerts (alert_hash, alert_type, message)
                VALUES ('event-hash', 'PRICE_DROP', 'Price dropped')
                """
            )
        )

    with Session(engine) as session:
        alert = session.scalar(select(PortfolioAlert))

    assert alert is not None
    assert isinstance(alert.timestamp, datetime)
    assert alert.is_acknowledged is False

    with pytest.raises(IntegrityError):
        with Session(engine) as session:
            session.add(
                PortfolioAlert(
                    alert_hash="event-hash",
                    alert_type="DRIFT",
                    message="Allocation drifted",
                )
            )
            session.commit()
