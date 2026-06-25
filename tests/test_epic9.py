from __future__ import annotations

from datetime import UTC, datetime

import pytest
import requests

from portfolio_management.db.models import PortfolioAlert
from portfolio_management.services.notifications import (
    DiscordNotificationWarning,
    create_discord_dispatcher,
    format_discord_message,
    send_discord_alert,
)


class FakeResponse:
    def __init__(
        self,
        status_code: int = 204,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self.headers = headers or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


def _alert(alert_type: str, message: str) -> PortfolioAlert:
    return PortfolioAlert(
        id=1,
        alert_hash="hash",
        timestamp=datetime.now(UTC),
        alert_type=alert_type,
        message=message,
        is_acknowledged=False,
    )


def test_discord_price_payload_uses_markdown_and_price_emoji() -> None:
    alert = _alert(
        "PRICE_DROP",
        "PRICE ALERT: VWRP.L dropped by 0.6% from its previous close.",
    )
    calls = []

    delivered = send_discord_alert(
        alert,
        "https://discord.com/api/webhooks/1/token",
        post=lambda *args, **kwargs: calls.append((args, kwargs)) or FakeResponse(),
    )

    assert delivered is True
    assert calls[0][0] == ("https://discord.com/api/webhooks/1/token",)
    assert calls[0][1]["timeout"] == 10
    content = calls[0][1]["json"]["content"]
    assert content.startswith("\U0001f6a8 **Price Drop Alert**")
    assert "**VWRP.L**" in content


def test_discord_drift_payload_formats_asset_class() -> None:
    alert = _alert(
        "DRIFT",
        "DRIFT ALERT: EQUITY is 6.0% above target for account 1.",
    )

    content = format_discord_message(alert)

    assert content.startswith("\u2696\ufe0f **Portfolio Drift Alert**")
    assert "**EQUITY** is" in content


def test_discord_rate_limit_warns_without_raising() -> None:
    alert = _alert("DRIFT", "DRIFT ALERT: CASH is 8.0% below target.")

    with pytest.warns(DiscordNotificationWarning, match="rate limit"):
        delivered = send_discord_alert(
            alert,
            "https://discord.com/api/webhooks/1/token",
            post=lambda *args, **kwargs: FakeResponse(
                status_code=429,
                headers={"Retry-After": "2"},
            ),
        )

    assert delivered is False


def test_discord_timeout_warns_without_raising() -> None:
    alert = _alert("PRICE_DROP", "PRICE ALERT: VWRP.L dropped.")

    def timeout(*args, **kwargs):
        raise requests.Timeout("request timed out")

    with pytest.warns(DiscordNotificationWarning, match="timed out"):
        delivered = send_discord_alert(
            alert,
            "https://discord.com/api/webhooks/1/token",
            post=timeout,
        )

    assert delivered is False


def test_discord_http_error_warns_without_raising() -> None:
    alert = _alert("DRIFT", "DRIFT ALERT: CASH is below target.")

    with pytest.warns(DiscordNotificationWarning, match="HTTP 500"):
        delivered = send_discord_alert(
            alert,
            "https://discord.com/api/webhooks/1/token",
            post=lambda *args, **kwargs: FakeResponse(status_code=500),
        )

    assert delivered is False


def test_discord_dispatcher_is_optional() -> None:
    assert create_discord_dispatcher(None) is None
    assert callable(
        create_discord_dispatcher("https://discord.com/api/webhooks/1/token")
    )
