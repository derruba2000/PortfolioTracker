from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from portfolio_management.db.models import ImportErrorLog
from portfolio_management.db.session import get_session_factory


def add_import_error(
    session: Session,
    *,
    pipeline_name: str,
    error_message: str,
) -> ImportErrorLog:
    error = ImportErrorLog(
        pipeline_name=pipeline_name.strip() or "unknown",
        error_message=str(error_message),
        timestamp=datetime.now(UTC),
    )
    session.add(error)
    return error


def log_import_error(*, pipeline_name: str, error_message: str) -> ImportErrorLog:
    session_factory = get_session_factory()
    with session_factory() as session:
        error = add_import_error(
            session,
            pipeline_name=pipeline_name,
            error_message=error_message,
        )
        session.commit()
        return error
