from __future__ import annotations

from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from portfolio_management.db.base import Base
from portfolio_management.db.models import (
    Account,
    AccountStrategy,
    Benchmark,
    Broker,
    Strategy,
)
from portfolio_management.db.seed import seed_defaults


def test_seed_defaults_is_idempotent() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)

    seed_defaults(engine)
    seed_defaults(engine)

    with Session(engine) as session:
        benchmarks = session.scalars(select(Benchmark)).all()
        strategies = session.scalars(select(Strategy)).all()

    assert len(benchmarks) == 3
    assert len(strategies) == 2


def test_sqlite_decimal_round_trips_exactly() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    seed_defaults(engine)

    with Session(engine) as session:
        strategy = session.scalar(select(Strategy).where(Strategy.name == "Core Growth"))
        assert strategy is not None
        value = Decimal("0.3333333333333333333333333333")
        broker = Broker(name="Test Broker")
        account = Account(broker=broker, name="Taxable", currency_code="USD")
        session.add(
            AccountStrategy(
                account=account,
                strategy=strategy,
                allocation_weight=value,
            )
        )
        session.commit()

    with Session(engine) as session:
        account_strategy = session.scalar(select(AccountStrategy))
        assert account_strategy is not None
        assert account_strategy.allocation_weight == Decimal(
            "0.3333333333333333333333333333"
        )
