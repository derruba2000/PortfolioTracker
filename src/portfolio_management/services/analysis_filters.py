from __future__ import annotations

from sqlalchemy import select

from portfolio_management.db.models import Account, Broker, Portfolio
from portfolio_management.db.session import get_session_factory
from portfolio_management.services.accounts import parse_choice_id
from portfolio_management.services.analytics import (
    ALL_ACCOUNTS_MODE,
    LIVE_MODE,
    SANDBOX_MODE,
)

ALL_PORTFOLIOS = "All Portfolios"
ACCOUNT_SCOPE_CHOICES = [LIVE_MODE, SANDBOX_MODE, ALL_ACCOUNTS_MODE]


def portfolio_filter_choices(account_mode: str) -> list[str]:
    session_factory = get_session_factory()
    with session_factory() as session:
        statement = (
            select(Portfolio, Account, Broker)
            .join(Portfolio.account)
            .join(Account.broker)
            .where(Broker.is_active.is_(True))
            .where(Account.is_active.is_(True))
            .where(Portfolio.is_active.is_(True))
            .order_by(Broker.name, Account.name, Portfolio.name)
        )
        if account_mode == SANDBOX_MODE:
            statement = statement.where(Account.is_simulated.is_(True))
        elif account_mode == LIVE_MODE:
            statement = statement.where(Account.is_simulated.is_(False))
        rows = session.execute(statement).all()

    choices = [ALL_PORTFOLIOS]
    for portfolio, account, broker in rows:
        account_type = "PAPER/TEST" if account.is_simulated else "LIVE"
        choices.append(
            f"{portfolio.id} | {broker.name} / {account.name} / "
            f"{portfolio.name} [{account_type}]"
        )
    return choices


def parse_portfolio_filter(portfolio_choice: str | int | None) -> int | None:
    if portfolio_choice in (None, "", ALL_PORTFOLIOS):
        return None
    return parse_choice_id(portfolio_choice)
