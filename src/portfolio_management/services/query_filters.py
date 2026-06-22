from __future__ import annotations

from typing import Any

from portfolio_management.db.models import Account


def exclude_simulated_accounts(statement: Any) -> Any:
    """Apply the default production firewall for global portfolio queries.

    Any query calculating global net worth, total performance, or dashboard
    summaries must call this helper unless it is intentionally building a
    sandbox/test view.
    """

    return statement.where(Account.is_simulated.is_(False))
