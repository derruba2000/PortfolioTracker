from __future__ import annotations

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from portfolio_management.db.models import Benchmark, Strategy
from portfolio_management.db.session import get_engine
from portfolio_management.services.reference_data import seed_reference_data


DEFAULT_BENCHMARKS = [
    ("SPY", "SPDR S&P 500 ETF Trust"),
    ("QQQ", "Invesco QQQ Trust"),
    ("AGG", "iShares Core U.S. Aggregate Bond ETF"),
]

DEFAULT_STRATEGIES = [
    ("Core Growth", "Long-term growth allocation for diversified portfolio accounts."),
    ("Income", "Income-oriented allocation for dividend and bond-heavy accounts."),
]


def seed_defaults(engine: Engine | None = None) -> None:
    engine = engine or get_engine()

    with Session(engine) as session:
        for ticker, name in DEFAULT_BENCHMARKS:
            exists = session.scalar(select(Benchmark).where(Benchmark.ticker == ticker))
            if exists is None:
                session.add(Benchmark(ticker=ticker, name=name))

        for name, description in DEFAULT_STRATEGIES:
            exists = session.scalar(select(Strategy).where(Strategy.name == name))
            if exists is None:
                session.add(Strategy(name=name, description=description))

        seed_reference_data(session)

        session.commit()


def main() -> None:
    seed_defaults()
    print("Seeded default benchmarks and strategies.")


if __name__ == "__main__":
    main()
