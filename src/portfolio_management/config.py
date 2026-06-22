from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


DEFAULT_DATABASE_PATH = Path(
    "/Users/joaoramo/Data/trading_experiment/portfolio_management.sqlite3"
)


@dataclass(frozen=True)
class Settings:
    database_path: Path

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.database_path}"


def load_settings() -> Settings:
    load_dotenv()
    database_path = Path(os.getenv("DATABASE_PATH", str(DEFAULT_DATABASE_PATH))).expanduser()
    return Settings(database_path=database_path)
