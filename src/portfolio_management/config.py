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


@dataclass(frozen=True)
class Settings:
    database_path: Path
    theme_name: str = DEFAULT_THEME_NAME

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.database_path}"


def load_settings() -> Settings:
    load_dotenv()
    database_path = Path(os.getenv("DATABASE_PATH", str(DEFAULT_DATABASE_PATH))).expanduser()
    theme_name = DEFAULT_THEME_NAME

    if SETTINGS_PATH.exists():
        try:
            data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            theme_name = str(data.get("theme_name", DEFAULT_THEME_NAME)) or DEFAULT_THEME_NAME
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            theme_name = DEFAULT_THEME_NAME

    return Settings(database_path=database_path, theme_name=theme_name)


def save_settings(*, theme_name: str | None = None) -> Settings:
    current = load_settings()
    updated = Settings(
        database_path=current.database_path,
        theme_name=theme_name or current.theme_name,
    )
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(
        json.dumps({"theme_name": updated.theme_name}, indent=2),
        encoding="utf-8",
    )
    return updated
