from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from portfolio_management.config import load_settings


def get_engine() -> Engine:
    settings = load_settings()
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(settings.database_url, future=True)


def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)


def get_session() -> Iterator[Session]:
    session_factory = get_session_factory()
    with session_factory() as session:
        yield session
