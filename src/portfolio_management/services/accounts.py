from __future__ import annotations

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from portfolio_management.db.models import Account, Broker, Portfolio
from portfolio_management.db.session import get_session_factory


DEFAULT_PORTFOLIO_NAME = "Default Portfolio"


def create_account(
    broker_name: str,
    account_name: str,
    currency_code: str,
    description: str = "",
    tax_wrapper_type: str = "",
    is_simulated: bool = False,
) -> str:
    if not broker_name.strip():
        raise ValueError("Broker is required.")
    if not account_name.strip():
        raise ValueError("Account is required.")

    session_factory = get_session_factory()
    with session_factory() as session:
        broker = get_or_create_broker(session, broker_name.strip())
        account = get_or_create_account(
            session=session,
            broker=broker,
            name=account_name.strip(),
            currency_code=currency_code.strip().upper() or "USD",
            description=description.strip() or None,
            tax_wrapper_type=tax_wrapper_type.strip() or None,
            is_simulated=bool(is_simulated),
        )
        session.commit()

    account_type = "TEST" if account.is_simulated else "REAL"
    return f"Created {account_type} account '{account.name}'."


def create_portfolio(
    account_choice: str | int | None,
    portfolio_name: str,
    description: str = "",
) -> str:
    account_id = parse_choice_id(account_choice)
    if account_id is None:
        raise ValueError("Account is required.")
    if not portfolio_name.strip():
        raise ValueError("Portfolio is required.")

    session_factory = get_session_factory()
    with session_factory() as session:
        account = session.get(Account, account_id)
        if account is None:
            raise ValueError(f"Account id {account_id} does not exist.")
        portfolio = get_or_create_portfolio(
            session,
            account,
            portfolio_name.strip(),
            description=description.strip() or None,
        )
        session.commit()

    return f"Created portfolio '{portfolio.name}' for account '{account.name}'."


def create_account_with_portfolio(
    broker_name: str,
    account_name: str,
    currency_code: str,
    description: str = "",
    tax_wrapper_type: str = "",
    is_simulated: bool = False,
    portfolio_name: str = DEFAULT_PORTFOLIO_NAME,
    portfolio_description: str = "",
) -> str:
    create_account(
        broker_name=broker_name,
        account_name=account_name,
        currency_code=currency_code,
        description=description,
        tax_wrapper_type=tax_wrapper_type,
        is_simulated=is_simulated,
    )
    return create_portfolio(
        account_choice=_find_account_choice(broker_name, account_name),
        portfolio_name=portfolio_name,
        description=portfolio_description,
    )


def account_description(account_choice: str | int | None) -> str:
    account_id = parse_choice_id(account_choice)
    if account_id is None:
        return ""

    session_factory = get_session_factory()
    with session_factory() as session:
        account = session.get(Account, account_id)
        if account is None:
            return ""
        return account.description or ""


def update_account_description(
    account_choice: str | int | None,
    description: str,
) -> str:
    account_id = parse_choice_id(account_choice)
    if account_id is None:
        raise ValueError("Account is required.")

    session_factory = get_session_factory()
    with session_factory() as session:
        account = session.get(Account, account_id)
        if account is None:
            raise ValueError(f"Account id {account_id} does not exist.")
        account.description = description.strip() or None
        session.commit()

    return f"Updated account description for '{account.name}'."


def get_or_create_broker(session: Session, name: str) -> Broker:
    broker = session.scalar(select(Broker).where(Broker.name == name))
    if broker is None:
        broker = Broker(name=name)
        session.add(broker)
        session.flush()
    return broker


def get_or_create_account(
    session: Session,
    broker: Broker,
    name: str,
    currency_code: str,
    description: str | None = None,
    tax_wrapper_type: str | None = None,
    is_simulated: bool = False,
) -> Account:
    account = session.scalar(
        select(Account).where(Account.broker_id == broker.id, Account.name == name)
    )
    if account is None:
        account = Account(
            broker=broker,
            name=name,
            description=description,
            currency_code=currency_code,
            tax_wrapper_type=tax_wrapper_type,
            is_simulated=is_simulated,
        )
        session.add(account)
        session.flush()
    return account


def get_or_create_portfolio(
    session: Session,
    account: Account,
    name: str = DEFAULT_PORTFOLIO_NAME,
    description: str | None = None,
) -> Portfolio:
    portfolio = session.scalar(
        select(Portfolio).where(Portfolio.account_id == account.id, Portfolio.name == name)
    )
    if portfolio is None:
        portfolio = Portfolio(account=account, name=name, description=description)
        session.add(portfolio)
        session.flush()
    return portfolio


def account_choices(include_simulated: bool = True) -> list[str]:
    session_factory = get_session_factory()
    with session_factory() as session:
        statement = (
            select(Account, Broker)
            .join(Account.broker)
            .order_by(Broker.name, Account.name)
        )
        if not include_simulated:
            statement = statement.where(Account.is_simulated.is_(False))
        rows = session.execute(statement).all()
    return [_account_label(account, broker) for account, broker in rows]


def list_brokers() -> pd.DataFrame:
    session_factory = get_session_factory()
    with session_factory() as session:
        rows = session.scalars(select(Broker).order_by(Broker.name)).all()

    return pd.DataFrame(
        [{"ID": broker.id, "Broker": broker.name} for broker in rows],
        columns=["ID", "Broker"],
    )


def list_accounts(account_filter: str = "All") -> pd.DataFrame:
    session_factory = get_session_factory()
    with session_factory() as session:
        stmt = (
            select(Account, Broker)
            .join(Account.broker)
            .order_by(Broker.name, Account.name)
        )
        if account_filter == "Real":
            stmt = stmt.where(Account.is_simulated.is_(False))
        elif account_filter == "Test":
            stmt = stmt.where(Account.is_simulated.is_(True))
        rows = session.execute(stmt).all()

    return pd.DataFrame(
        [
            {
                "ID": account.id,
                "Broker": broker.name,
                "Account": account.name,
                "Description": account.description or "",
                "Currency": account.currency_code,
                "Tax Wrapper": account.tax_wrapper_type or "",
                "Simulated": "Yes" if account.is_simulated else "No",
            }
            for account, broker in rows
        ],
        columns=[
            "ID",
            "Broker",
            "Account",
            "Description",
            "Currency",
            "Tax Wrapper",
            "Simulated",
        ],
    )


def list_portfolios(account_filter: str = "All") -> pd.DataFrame:
    session_factory = get_session_factory()
    with session_factory() as session:
        stmt = (
            select(Portfolio, Account, Broker)
            .join(Portfolio.account)
            .join(Account.broker)
            .order_by(Broker.name, Account.name, Portfolio.name)
        )
        if account_filter == "Real":
            stmt = stmt.where(Account.is_simulated.is_(False))
        elif account_filter == "Test":
            stmt = stmt.where(Account.is_simulated.is_(True))
        rows = session.execute(stmt).all()

    return pd.DataFrame(
        [
            {
                "ID": portfolio.id,
                "Broker": broker.name,
                "Account": account.name,
                "Portfolio": portfolio.name,
                "Description": portfolio.description or "",
                "Currency": account.currency_code,
                "Simulated Account": "Yes" if account.is_simulated else "No",
            }
            for portfolio, account, broker in rows
        ],
        columns=[
            "ID",
            "Broker",
            "Account",
            "Portfolio",
            "Description",
            "Currency",
            "Simulated Account",
        ],
    )


def portfolio_choices_for_account(account_choice: str | int | None) -> list[str]:
    account_id = parse_choice_id(account_choice)
    if account_id is None:
        return []

    session_factory = get_session_factory()
    with session_factory() as session:
        rows = session.scalars(
            select(Portfolio)
            .where(Portfolio.account_id == account_id)
            .order_by(Portfolio.name)
        ).all()
    return [_portfolio_label(portfolio) for portfolio in rows]


def default_account_choice() -> str | None:
    choices = account_choices(include_simulated=True)
    return choices[0] if choices else None


def default_portfolio_choice(account_choice: str | int | None) -> str | None:
    choices = portfolio_choices_for_account(account_choice)
    return choices[0] if choices else None


def parse_choice_id(choice: str | int | None) -> int | None:
    if choice is None or choice == "":
        return None
    if isinstance(choice, int):
        return choice
    raw_id = str(choice).split("|", maxsplit=1)[0].strip()
    return int(raw_id) if raw_id else None


def _account_label(account: Account, broker: Broker) -> str:
    badge = " [TEST]" if account.is_simulated else ""
    wrapper = f" ({account.tax_wrapper_type})" if account.tax_wrapper_type else ""
    return f"{account.id} | {broker.name} / {account.name}{wrapper}{badge}"


def _portfolio_label(portfolio: Portfolio) -> str:
    return f"{portfolio.id} | {portfolio.name}"


def _find_account_choice(broker_name: str, account_name: str) -> str:
    for choice in account_choices(include_simulated=True):
        if f"{broker_name.strip()} / {account_name.strip()}" in choice:
            return choice
    raise ValueError(f"Account '{account_name}' does not exist.")
