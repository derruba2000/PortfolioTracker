from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from portfolio_management.db.base import Base
from portfolio_management.db.models import Security
from portfolio_management.services.reference_data import seed_reference_data
from portfolio_management.services.securities import (
    create_security,
    list_asset_subclass_choices,
    list_securities,
    security_form_values,
)


def test_create_security_saves_asset_subclass(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    monkeypatch.setattr("portfolio_management.services.securities.get_session_factory", lambda: factory)

    with Session(engine) as session:
        seed_reference_data(session)
        session.commit()

    status = create_security(
        ticker="VWRP.L",
        description="Vanguard FTSE All-World UCITS ETF",
        asset_class="EQUITY",
        asset_subclass="ETF 50% EQUITY 50% BOND",
        currency_code="GBP",
    )

    with Session(engine) as session:
        security = session.scalar(select(Security).where(Security.ticker == "VWRP.L"))
    securities = list_securities()

    assert status == "Saved security 'VWRP.L'."
    assert security is not None
    assert security.asset_subclass == "ETF 50% EQUITY 50% BOND"
    assert "ETF 100% GOLD" in list_asset_subclass_choices()
    assert securities.loc[0, "Asset Subclass"] == "ETF 50% EQUITY 50% BOND"


def test_security_form_loads_existing_ticker_and_save_overwrites(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    monkeypatch.setattr("portfolio_management.services.securities.get_session_factory", lambda: factory)

    with Session(engine) as session:
        seed_reference_data(session)
        session.commit()

    create_security(
        ticker="GLD",
        description="Gold ETF",
        asset_class="COMMODITY",
        asset_subclass="ETF 100% GOLD",
        currency_code="USD",
    )

    assert security_form_values(
        " gld ",
        current_description="",
        current_asset_class="EQUITY",
        current_asset_subclass="STOCK",
        current_currency="GBP",
    ) == (
        "Gold ETF",
        "COMMODITY",
        "ETF 100% GOLD",
        "USD",
        "Loaded security 'GLD'.",
    )

    create_security(
        ticker="GLD",
        description="Updated Gold ETF",
        asset_class="COMMODITY",
        asset_subclass="GOLD",
        currency_code="GBP",
    )

    with Session(engine) as session:
        securities = session.scalars(select(Security)).all()

    assert len(securities) == 1
    assert securities[0].description == "Updated Gold ETF"
    assert securities[0].asset_subclass == "GOLD"
    assert securities[0].currency_code == "GBP"
