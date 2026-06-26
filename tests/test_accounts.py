from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from portfolio_management.db.base import Base
from portfolio_management.db.models import Portfolio
from portfolio_management.services.accounts import (
    account_description,
    create_portfolio,
    get_or_create_account,
    get_or_create_broker,
    get_or_create_portfolio,
    list_accounts,
    list_brokers,
    list_portfolios,
    portfolio_details,
    update_portfolio,
    update_account_description,
)


def test_account_can_have_multiple_portfolios() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        broker = get_or_create_broker(session, "Vanguard")
        account = get_or_create_account(
            session=session,
            broker=broker,
            name="ISA",
            currency_code="GBP",
            description="Long-term tax efficient account",
        )

        core = get_or_create_portfolio(
            session,
            account,
            "Core ETF",
            description="Long-term global ETF allocation",
        )
        dividends = get_or_create_portfolio(session, account, "Dividend")
        duplicate_core = get_or_create_portfolio(session, account, "Core ETF")
        session.commit()

        portfolios = session.scalars(
            select(Portfolio).where(Portfolio.account_id == account.id).order_by(Portfolio.name)
        ).all()

    assert core.id == duplicate_core.id
    assert account.description == "Long-term tax efficient account"
    assert core.description == "Long-term global ETF allocation"
    assert dividends.id != core.id
    assert [portfolio.name for portfolio in portfolios] == ["Core ETF", "Dividend"]


def test_list_functions_return_expected_columns(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        broker = get_or_create_broker(session, "Vanguard")
        account = get_or_create_account(
            session=session,
            broker=broker,
            name="ISA",
            currency_code="GBP",
            description="Tax efficient account",
        )
        get_or_create_portfolio(session, account, "Core ETF")
        session.commit()

    monkeypatch.setattr(
        "portfolio_management.services.accounts.get_session_factory",
        lambda: sessionmaker(bind=engine, expire_on_commit=False, future=True),
    )

    brokers = list_brokers()
    accounts = list_accounts()
    portfolios = list_portfolios()

    assert brokers.to_dict("records") == [{"ID": 1, "Broker": "Vanguard"}]
    assert accounts.loc[0, "Account"] == "ISA"
    assert accounts.loc[0, "Description"] == "Tax efficient account"
    assert portfolios.loc[0, "Portfolio"] == "Core ETF"


def test_update_account_description(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        broker = get_or_create_broker(session, "BPI")
        account = get_or_create_account(
            session=session,
            broker=broker,
            name="Portugal",
            currency_code="EUR",
            description="Old description",
        )
        session.commit()
        account_choice = f"{account.id} | BPI / Portugal"

    monkeypatch.setattr(
        "portfolio_management.services.accounts.get_session_factory",
        lambda: sessionmaker(bind=engine, expire_on_commit=False, future=True),
    )

    update_account_description(account_choice, "New description for later notes")

    assert account_description(account_choice) == "New description for later notes"


def test_portfolio_goals_are_saved_and_listed(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    monkeypatch.setattr(
        "portfolio_management.services.accounts.get_session_factory",
        lambda: factory,
    )

    with Session(engine) as session:
        broker = get_or_create_broker(session, "Vanguard")
        account = get_or_create_account(
            session=session,
            broker=broker,
            name="ISA",
            currency_code="GBP",
        )
        session.commit()
        account_choice = f"{account.id} | Vanguard / ISA"

    create_portfolio(
        account_choice=account_choice,
        portfolio_name="Goals",
        description="Goal-based portfolio",
        portfolio_goals=["Retirement", "Income"],
        goal_type="Balanced",
        goal_timeline="10+ years",
    )
    portfolios = list_portfolios()
    portfolio_choice = f"{portfolios.loc[0, 'ID']} | Vanguard / ISA / Goals"

    update_portfolio(
        portfolio_choice=portfolio_choice,
        portfolio_name="Goals",
        description="Updated",
        portfolio_url="",
        portfolio_goals=["Capital Growth"],
        goal_type="Growth",
        goal_timeline="5-10 years",
        is_active=True,
    )

    details = portfolio_details(portfolio_choice)
    portfolios = list_portfolios()

    assert details[3] == ["Capital Growth"]
    assert details[4] == "Growth"
    assert details[5] == "5-10 years"
    assert portfolios.loc[0, "Goals"] == "Capital Growth"
