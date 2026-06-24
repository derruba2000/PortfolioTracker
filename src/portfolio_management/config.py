from __future__ import annotations

import os
import json
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


DEFAULT_DATABASE_PATH = Path(
    "/Users/joaoramo/Data/trading_experiment/portfolio_management.sqlite3"
)
DEFAULT_THEME_NAME = "Soft"
SETTINGS_PATH = Path.home() / ".portfolio_management" / "settings.json"


_MISSING = object()


@dataclass(frozen=True)
class Settings:
    database_path: Path
    theme_name: str = DEFAULT_THEME_NAME
    export_symbols_csv_path: Path | None = None
    market_prices_delta_path: Path | None = None
    fx_rates_delta_path: Path | None = None

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
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            theme_name = DEFAULT_THEME_NAME

    return Settings(
        database_path=database_path,
        theme_name=theme_name,
        export_symbols_csv_path=export_symbols_csv_path,
        market_prices_delta_path=market_prices_delta_path,
        fx_rates_delta_path=fx_rates_delta_path,
    )


def save_settings(
    *,
    theme_name: str | None = None,
    export_symbols_csv_path: "str | Path | None | object" = _MISSING,
    market_prices_delta_path: "str | Path | None | object" = _MISSING,
    fx_rates_delta_path: "str | Path | None | object" = _MISSING,
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
    )
    data: dict[str, str | None] = {"theme_name": updated.theme_name}
    if updated.export_symbols_csv_path is not None:
        data["export_symbols_csv_path"] = str(updated.export_symbols_csv_path)
    if updated.market_prices_delta_path is not None:
        data["market_prices_delta_path"] = str(updated.market_prices_delta_path)
    if updated.fx_rates_delta_path is not None:
        data["fx_rates_delta_path"] = str(updated.fx_rates_delta_path)
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return updated


def _resolve_optional_path(value: object, current: Path | None) -> Path | None:
    if value is _MISSING:
        return current
    if value:
        return Path(str(value)).expanduser()
    return None
