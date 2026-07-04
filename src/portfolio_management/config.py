from __future__ import annotations

import os
import json
import warnings
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlparse

from cryptography.fernet import Fernet, InvalidToken
from dotenv import load_dotenv


DEFAULT_DATABASE_PATH = Path(
    "/Users/joaoramo/Data/trading_experiment/portfolio_management.sqlite3"
)
DEFAULT_THEME_NAME = "Soft"
DEFAULT_PRICE_DROP_THRESHOLD_PCT = Decimal("0.5")
DEFAULT_DRIFT_TOLERANCE_PCT = Decimal("5.0")
DEFAULT_OLLAMA_MODEL = "gemma4"
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_OLLAMA_TIMEOUT_SECONDS = 300
DEFAULT_API_USAGE = "OLLAMA"
DEFAULT_NVIDIA_API_MODEL = "meta/llama-3.3-70b-instruct"
DEFAULT_NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
DEFAULT_NVIDIA_VERIFY_SSL = False
SETTINGS_PATH = Path.home() / ".portfolio_management" / "settings.json"
SECRETS_PATH = Path.home() / ".portfolio_management" / "secrets.json"
SECRET_KEY_PATH = Path.home() / ".portfolio_management" / "secrets.key"


_MISSING = object()


class DiscordWebhookConfigurationWarning(UserWarning):
    """Discord notifications are disabled because webhook configuration is missing."""


class AlertThresholdConfigurationWarning(UserWarning):
    """An alert threshold is invalid and its default value will be used."""


@dataclass(frozen=True)
class Settings:
    database_path: Path
    theme_name: str = DEFAULT_THEME_NAME
    export_symbols_csv_path: Path | None = None
    market_prices_delta_path: Path | None = None
    fx_rates_delta_path: Path | None = None
    discord_webhook_url: str | None = None
    price_drop_threshold_pct: Decimal = DEFAULT_PRICE_DROP_THRESHOLD_PCT
    drift_tolerance_pct: Decimal = DEFAULT_DRIFT_TOLERANCE_PCT
    api_usage: str = DEFAULT_API_USAGE
    ollama_model: str = DEFAULT_OLLAMA_MODEL
    ollama_base_url: str = DEFAULT_OLLAMA_BASE_URL
    ollama_timeout_seconds: int = DEFAULT_OLLAMA_TIMEOUT_SECONDS
    nvidia_api_model: str = DEFAULT_NVIDIA_API_MODEL
    nvidia_base_url: str = DEFAULT_NVIDIA_BASE_URL
    nvidia_verify_ssl: bool = DEFAULT_NVIDIA_VERIFY_SSL
    nvidia_api_key: str | None = None

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.database_path}"


def load_settings() -> Settings:
    load_dotenv()
    database_path = Path(os.getenv("DATABASE_PATH", str(DEFAULT_DATABASE_PATH))).expanduser()
    theme_name = DEFAULT_THEME_NAME
    export_symbols_csv_path: Path | None = None
    market_prices_delta_path: Path | None = None
    fx_rates_delta_path: Path | None = None
    secrets = _load_encrypted_secrets()
    discord_webhook_url = _load_discord_webhook_url(secrets.get("discord_webhook_url"))
    price_drop_threshold_pct = _load_non_negative_decimal(
        "PRICE_DROP_THRESHOLD_PCT",
        DEFAULT_PRICE_DROP_THRESHOLD_PCT,
    )
    drift_tolerance_pct = _load_non_negative_decimal(
        "DRIFT_TOLERANCE_PCT",
        DEFAULT_DRIFT_TOLERANCE_PCT,
    )
    ollama_model = os.getenv("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL).strip() or DEFAULT_OLLAMA_MODEL
    ollama_base_url = (
        os.getenv("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL).strip()
        or DEFAULT_OLLAMA_BASE_URL
    ).rstrip("/")
    ollama_timeout_seconds = _load_positive_int(
        "OLLAMA_TIMEOUT_SECONDS",
        DEFAULT_OLLAMA_TIMEOUT_SECONDS,
    )
    api_usage = _normalize_api_usage(os.getenv("API_USAGE", DEFAULT_API_USAGE))
    nvidia_api_model = (
        os.getenv("NVIDIA_API_MODEL", DEFAULT_NVIDIA_API_MODEL).strip()
        or DEFAULT_NVIDIA_API_MODEL
    )
    nvidia_base_url = (
        os.getenv("NVIDIA_BASE_URL", DEFAULT_NVIDIA_BASE_URL).strip()
        or DEFAULT_NVIDIA_BASE_URL
    ).rstrip("/")
    nvidia_verify_ssl = _load_bool("NVIDIA_VERIFY_SSL", DEFAULT_NVIDIA_VERIFY_SSL)
    nvidia_api_key = os.getenv("NVIDIA_API_KEY", "").strip() or secrets.get("nvidia_api_key")

    if SETTINGS_PATH.exists():
        try:
            data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            theme_name = str(data.get("theme_name", DEFAULT_THEME_NAME)) or DEFAULT_THEME_NAME
            raw_csv = data.get("export_symbols_csv_path")
            export_symbols_csv_path = Path(str(raw_csv)).expanduser() if raw_csv else None
            raw_prices_delta = data.get("market_prices_delta_path")
            market_prices_delta_path = (
                Path(str(raw_prices_delta)).expanduser() if raw_prices_delta else None
            )
            raw_fx_delta = data.get("fx_rates_delta_path")
            fx_rates_delta_path = Path(str(raw_fx_delta)).expanduser() if raw_fx_delta else None
            api_usage = _normalize_api_usage(data.get("api_usage", api_usage))
            ollama_model = (
                str(data.get("ollama_model", ollama_model)).strip()
                or DEFAULT_OLLAMA_MODEL
            )
            ollama_base_url = (
                str(data.get("ollama_base_url", ollama_base_url)).strip()
                or DEFAULT_OLLAMA_BASE_URL
            ).rstrip("/")
            ollama_timeout_seconds = _positive_int_value(
                data.get("ollama_timeout_seconds"),
                ollama_timeout_seconds,
            )
            nvidia_api_model = (
                str(data.get("nvidia_api_model", nvidia_api_model)).strip()
                or DEFAULT_NVIDIA_API_MODEL
            )
            nvidia_base_url = (
                str(data.get("nvidia_base_url", nvidia_base_url)).strip()
                or DEFAULT_NVIDIA_BASE_URL
            ).rstrip("/")
            nvidia_verify_ssl = _bool_value(
                data.get("nvidia_verify_ssl"),
                nvidia_verify_ssl,
            )
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            theme_name = DEFAULT_THEME_NAME

    return Settings(
        database_path=database_path,
        theme_name=theme_name,
        export_symbols_csv_path=export_symbols_csv_path,
        market_prices_delta_path=market_prices_delta_path,
        fx_rates_delta_path=fx_rates_delta_path,
        discord_webhook_url=discord_webhook_url,
        price_drop_threshold_pct=price_drop_threshold_pct,
        drift_tolerance_pct=drift_tolerance_pct,
        api_usage=api_usage,
        ollama_model=ollama_model,
        ollama_base_url=ollama_base_url,
        ollama_timeout_seconds=ollama_timeout_seconds,
        nvidia_api_model=nvidia_api_model,
        nvidia_base_url=nvidia_base_url,
        nvidia_verify_ssl=nvidia_verify_ssl,
        nvidia_api_key=nvidia_api_key,
    )


def save_settings(
    *,
    theme_name: str | None = None,
    export_symbols_csv_path: "str | Path | None | object" = _MISSING,
    market_prices_delta_path: "str | Path | None | object" = _MISSING,
    fx_rates_delta_path: "str | Path | None | object" = _MISSING,
    discord_webhook_url: "str | None | object" = _MISSING,
    api_usage: str | None = None,
    ollama_model: str | None = None,
    ollama_base_url: str | None = None,
    ollama_timeout_seconds: int | str | None = None,
    nvidia_api_model: str | None = None,
    nvidia_base_url: str | None = None,
    nvidia_verify_ssl: bool | str | None = None,
    nvidia_api_key: "str | None | object" = _MISSING,
) -> Settings:
    current = load_settings()
    resolved_csv = _resolve_optional_path(
        export_symbols_csv_path, current.export_symbols_csv_path
    )
    resolved_prices_delta = _resolve_optional_path(
        market_prices_delta_path, current.market_prices_delta_path
    )
    resolved_fx_delta = _resolve_optional_path(
        fx_rates_delta_path, current.fx_rates_delta_path
    )
    updated = Settings(
        database_path=current.database_path,
        theme_name=theme_name or current.theme_name,
        export_symbols_csv_path=resolved_csv,
        market_prices_delta_path=resolved_prices_delta,
        fx_rates_delta_path=resolved_fx_delta,
        discord_webhook_url=current.discord_webhook_url,
        price_drop_threshold_pct=current.price_drop_threshold_pct,
        drift_tolerance_pct=current.drift_tolerance_pct,
        api_usage=_normalize_api_usage(api_usage or current.api_usage),
        ollama_model=(ollama_model or current.ollama_model).strip() or DEFAULT_OLLAMA_MODEL,
        ollama_base_url=(
            (ollama_base_url or current.ollama_base_url).strip()
            or DEFAULT_OLLAMA_BASE_URL
        ).rstrip("/"),
        ollama_timeout_seconds=_positive_int_value(
            ollama_timeout_seconds,
            current.ollama_timeout_seconds,
        ),
        nvidia_api_model=(nvidia_api_model or current.nvidia_api_model).strip()
        or DEFAULT_NVIDIA_API_MODEL,
        nvidia_base_url=(
            (nvidia_base_url or current.nvidia_base_url).strip()
            or DEFAULT_NVIDIA_BASE_URL
        ).rstrip("/"),
        nvidia_verify_ssl=_bool_value(
            nvidia_verify_ssl,
            current.nvidia_verify_ssl,
        ),
        nvidia_api_key=current.nvidia_api_key,
    )
    if discord_webhook_url is not _MISSING or nvidia_api_key is not _MISSING:
        secrets = _load_encrypted_secrets()
        if discord_webhook_url is not _MISSING:
            webhook = str(discord_webhook_url or "").strip()
            if webhook:
                _validate_discord_webhook_url(webhook)
                secrets["discord_webhook_url"] = webhook
                object.__setattr__(updated, "discord_webhook_url", webhook)
            else:
                secrets.pop("discord_webhook_url", None)
                object.__setattr__(updated, "discord_webhook_url", None)
        if nvidia_api_key is not _MISSING:
            api_key = str(nvidia_api_key or "").strip()
            if api_key:
                secrets["nvidia_api_key"] = api_key
                object.__setattr__(updated, "nvidia_api_key", api_key)
            else:
                secrets.pop("nvidia_api_key", None)
                object.__setattr__(updated, "nvidia_api_key", None)
        _save_encrypted_secrets(secrets)

    data: dict[str, str | int | bool | None] = {"theme_name": updated.theme_name}
    if updated.export_symbols_csv_path is not None:
        data["export_symbols_csv_path"] = str(updated.export_symbols_csv_path)
    if updated.market_prices_delta_path is not None:
        data["market_prices_delta_path"] = str(updated.market_prices_delta_path)
    if updated.fx_rates_delta_path is not None:
        data["fx_rates_delta_path"] = str(updated.fx_rates_delta_path)
    data.update(
        {
            "api_usage": updated.api_usage,
            "ollama_model": updated.ollama_model,
            "ollama_base_url": updated.ollama_base_url,
            "ollama_timeout_seconds": updated.ollama_timeout_seconds,
            "nvidia_api_model": updated.nvidia_api_model,
            "nvidia_base_url": updated.nvidia_base_url,
            "nvidia_verify_ssl": updated.nvidia_verify_ssl,
        }
    )
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return updated


def _resolve_optional_path(value: object, current: Path | None) -> Path | None:
    if value is _MISSING:
        return current
    if value:
        return Path(str(value)).expanduser()
    return None


def _load_discord_webhook_url(saved_webhook_url: str | None = None) -> str | None:
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "").strip() or (saved_webhook_url or "")
    if not webhook_url:
        warnings.warn(
            "DISCORD_WEBHOOK_URL is not configured; Discord notifications are disabled.",
            DiscordWebhookConfigurationWarning,
            stacklevel=2,
        )
        return None

    try:
        _validate_discord_webhook_url(webhook_url)
    except ValueError:
        warnings.warn(
            "DISCORD_WEBHOOK_URL must be an absolute HTTPS URL; "
            "Discord notifications are disabled.",
            DiscordWebhookConfigurationWarning,
            stacklevel=2,
        )
        return None

    return webhook_url


def _validate_discord_webhook_url(webhook_url: str) -> None:
    parsed_url = urlparse(webhook_url)
    if parsed_url.scheme != "https" or not parsed_url.netloc:
        raise ValueError("Discord webhook URL must be an absolute HTTPS URL.")


def _load_non_negative_decimal(name: str, default: Decimal) -> Decimal:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default
    try:
        value = Decimal(raw_value)
    except InvalidOperation:
        value = Decimal("-1")
    if not value.is_finite() or value < 0:
        warnings.warn(
            f"{name} must be a non-negative number; using default {default}.",
            AlertThresholdConfigurationWarning,
            stacklevel=2,
        )
        return default
    return value


def _load_positive_int(name: str, default: int) -> int:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default
    try:
        value = int(raw_value)
    except ValueError:
        return default
    return value if value > 0 else default


def _positive_int_value(value: object, default: int) -> int:
    try:
        parsed = int(str(value))
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _load_bool(name: str, default: bool) -> bool:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default
    return _bool_value(raw_value, default)


def _bool_value(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _normalize_api_usage(value: object) -> str:
    normalized = str(value or DEFAULT_API_USAGE).strip().upper()
    return normalized if normalized in {"OLLAMA", "NVIDIA"} else DEFAULT_API_USAGE


def _load_encrypted_secrets() -> dict[str, str]:
    if not SECRETS_PATH.exists():
        return {}
    try:
        encrypted_data = json.loads(SECRETS_PATH.read_text(encoding="utf-8"))
        cipher = _get_secret_cipher()
        secrets: dict[str, str] = {}
        for key, token in encrypted_data.items():
            if not isinstance(token, str):
                continue
            try:
                secrets[key] = cipher.decrypt(token.encode("utf-8")).decode("utf-8")
            except (InvalidToken, ValueError):
                continue
        return secrets
    except (OSError, TypeError, json.JSONDecodeError):
        return {}


def _save_encrypted_secrets(secrets: dict[str, str]) -> None:
    cipher = _get_secret_cipher()
    encrypted_data = {
        key: cipher.encrypt(value.encode("utf-8")).decode("utf-8")
        for key, value in secrets.items()
        if value
    }
    SECRETS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SECRETS_PATH.write_text(json.dumps(encrypted_data, indent=2), encoding="utf-8")
    try:
        SECRETS_PATH.chmod(0o600)
    except OSError:
        pass


def _get_secret_cipher() -> Fernet:
    SECRET_KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    if SECRET_KEY_PATH.exists():
        key = SECRET_KEY_PATH.read_bytes().strip()
    else:
        key = Fernet.generate_key()
        SECRET_KEY_PATH.write_bytes(key)
        try:
            SECRET_KEY_PATH.chmod(0o600)
        except OSError:
            pass
    return Fernet(key)
