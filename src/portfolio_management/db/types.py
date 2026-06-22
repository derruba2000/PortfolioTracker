from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import String
from sqlalchemy.types import TypeDecorator


class SqliteDecimal(TypeDecorator[Decimal]):
    """Store Decimal values as text so SQLite never coerces them to float."""

    impl = String
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> str | None:
        if value is None:
            return None
        return str(Decimal(value))

    def process_result_value(self, value: Any, dialect: Any) -> Decimal | None:
        if value is None:
            return None
        return Decimal(value)
