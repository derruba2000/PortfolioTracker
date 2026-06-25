from __future__ import annotations

import re
import warnings
from collections.abc import Callable
from typing import Any

import requests

from portfolio_management.db.models import PortfolioAlert


DEFAULT_DISCORD_TIMEOUT_SECONDS = 10


class DiscordNotificationWarning(RuntimeWarning):
    """A Discord notification could not be delivered."""


DiscordPost = Callable[..., Any]


def format_discord_message(alert: PortfolioAlert) -> str:
    message = alert.message
    if alert.alert_type == "PRICE_DROP":
        message = re.sub(
            r"^(PRICE ALERT:\s+)(\S+)",
            r"\1**\2**",
            message,
            count=1,
        )
        return f"\U0001f6a8 **Price Drop Alert**\n{message}"
    if alert.alert_type == "DRIFT":
        message = re.sub(
            r"^(DRIFT ALERT:\s+)(.+?)(\s+is\s+)",
            r"\1**\2**\3",
            message,
            count=1,
        )
        return f"\u2696\ufe0f **Portfolio Drift Alert**\n{message}"
    return f"\u26a0\ufe0f **Portfolio Alert**\n{message}"


def send_discord_alert(
    alert: PortfolioAlert,
    webhook_url: str,
    *,
    timeout_seconds: int = DEFAULT_DISCORD_TIMEOUT_SECONDS,
    post: DiscordPost = requests.post,
) -> bool:
    try:
        response = post(
            webhook_url,
            json={"content": format_discord_message(alert)},
            timeout=timeout_seconds,
        )
    except requests.RequestException as exc:
        warnings.warn(
            f"Discord notification failed: {exc}",
            DiscordNotificationWarning,
            stacklevel=2,
        )
        return False

    if response.status_code == 429:
        retry_after = response.headers.get("Retry-After")
        retry_message = f" Retry after {retry_after} seconds." if retry_after else ""
        warnings.warn(
            f"Discord rate limit reached; notification was not delivered.{retry_message}",
            DiscordNotificationWarning,
            stacklevel=2,
        )
        return False

    try:
        response.raise_for_status()
    except requests.RequestException as exc:
        warnings.warn(
            f"Discord notification failed with HTTP {response.status_code}: {exc}",
            DiscordNotificationWarning,
            stacklevel=2,
        )
        return False
    return True


def create_discord_dispatcher(
    webhook_url: str | None,
) -> Callable[[PortfolioAlert], None] | None:
    if not webhook_url:
        return None

    def dispatch(alert: PortfolioAlert) -> None:
        send_discord_alert(alert, webhook_url)

    return dispatch
