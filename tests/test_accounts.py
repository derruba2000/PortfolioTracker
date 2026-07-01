from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from portfolio_management.db.base import Base
from portfolio_management.db.models import Portfolio
from portfolio_management.services.accounts import (
    account_description,
    create_broker,
    create_portfolio,
    get_or_create_account,
    get_or_create_broker,
    get_or_create_portfolio,
    list_accounts,
    list_brokers,
    list_brokers_detailed,
    list_portfolios,
    portfolio_details,
    update_broker,
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


def test_broker_fee_fields_persist_on_create_and_update(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    monkeypatch.setattr(
        "portfolio_management.services.accounts.get_session_factory",
        lambda: factory,
    )

    create_broker(
        "Interactive Brokers",
        "US and EU markets",
        trade_fee_fixed="1",
        trade_fee_percent="0.05",
        fx_fee_percent="0.20",
        spread_fee_percent="0.10",
        custody_fee_percent_annual="0.30",
        platform_fee_fixed_monthly="5",
        account_fee_fixed_monthly="2",
        inactivity_fee_fixed_monthly="1",
        withdrawal_fee_fixed="0.50",
        deposit_fee_fixed="0",
        stamp_duty_percent="0.50",
        regulatory_fee_percent="0.01",
        margin_interest_percent_annual="6.5",
        short_borrow_fee_percent_annual="3.5",
    )

    detailed = list_brokers_detailed()
    broker_choice = f"{detailed.loc[0, 'ID']} | Interactive Brokers"

    update_broker(
        broker_choice,
        "Interactive Brokers",
        "Updated",
        True,
        trade_fee_fixed="2",
        trade_fee_percent="0.06",
        fx_fee_percent="0.25",
        spread_fee_percent="0.11",
        custody_fee_percent_annual="0.40",
        platform_fee_fixed_monthly="6",
        account_fee_fixed_monthly="3",
        inactivity_fee_fixed_monthly="2",
        withdrawal_fee_fixed="0.75",
        deposit_fee_fixed="0.10",
        stamp_duty_percent="0.55",
        regulatory_fee_percent="0.02",
        margin_interest_percent_annual="7.0",
        short_borrow_fee_percent_annual="4.0",
    )

    detailed = list_brokers_detailed()
    row = detailed.iloc[0]

    assert row["Trade Fee (Fixed)"] == "2"
    assert row["Trade Fee (%)"] == "0.06"
    assert row["FX Fee (%)"] == "0.25"
    assert row["Spread Fee (%)"] == "0.11"
    assert row["Custody Fee Annual (%)"] == "0.4"
    assert row["Platform Fee Monthly (Fixed)"] == "6"
    assert row["Account Fee Monthly (Fixed)"] == "3"
    assert row["Inactivity Fee Monthly (Fixed)"] == "2"
    assert row["Withdrawal Fee (Fixed)"] == "0.75"
    assert row["Deposit Fee (Fixed)"] == "0.1"
    assert row["Stamp Duty (%)"] == "0.55"
    assert row["Regulatory Fee (%)"] == "0.02"
    assert row["Margin Interest Annual (%)"] == "7"
    assert row["Short Borrow Fee Annual (%)"] == "4"


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
