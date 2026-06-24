from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd
from deltalake import write_deltalake
import pyarrow as pa
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from portfolio_management.db.base import Base
from portfolio_management.db.models import (
    Account,
    AssetClass,
    Broker,
    FxRateHistory,
    ImportErrorLog,
    Portfolio,
    PriceHistory,
    Security,
    Transaction,
    TransactionType,
)
from portfolio_management.services.market_data import (
    import_market_data_from_delta_for_session,
    parse_fx_symbol,
    update_market_data_for_session,
    yahoo_fx_symbol,
)


def test_update_market_data_stores_prices_and_fx_rates() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)

    calls: list[str] = []

    def fetcher(symbol: str, start_date: date, end_date: date) -> pd.DataFrame:
        calls.append(symbol)
        return pd.DataFrame(
            {"Close": [Decimal("100.25"), Decimal("101.50")]},
            index=pd.to_datetime(["2026-06-20", "2026-06-21"]),
        )

    with Session(engine) as session:
        broker = Broker(name="Broker")
        account = Account(broker=broker, name="ISA", currency_code="GBP")
        portfolio = Portfolio(account=account, name="Core")
        security = Security(
            ticker="VWCE.AS",
            name="Vanguard FTSE All-World UCITS ETF",
            asset_class=AssetClass.ETF,
            currency_code="EUR",
        )
        session.add(
            Transaction(
                portfolio=portfolio,
                security=security,
                date=datetime(2026, 6, 20),
                type=TransactionType.BUY,
                quantity=1,
                price=Decimal("100"),
                fees=Decimal("0"),
                total_value=Decimal("100"),
                currency_exchange_rate=Decimal("1"),
            )
        )
        session.flush()

        result = update_market_data_for_session(
            session=session,
            start_date=date(2026, 6, 20),
            end_date=date(2026, 6, 21),
            fetcher=fetcher,
        )
        result_again = update_market_data_for_session(
            session=session,
            start_date=date(2026, 6, 20),
            end_date=date(2026, 6, 21),
            fetcher=fetcher,
        )

        prices = session.scalars(select(PriceHistory).order_by(PriceHistory.date)).all()
        fx_rates = session.scalars(select(FxRateHistory).order_by(FxRateHistory.date)).all()

    assert calls[:2] == ["VWCE.AS", "EURGBP=X"]
    assert result.prices_inserted == 2
    assert result.fx_rates_inserted == 2
    assert result_again.prices_inserted == 0
    assert result_again.fx_rates_inserted == 0
    assert [price.close_price for price in prices] == [Decimal("100.25"), Decimal("101.50")]
    assert [rate.rate for rate in fx_rates] == [Decimal("100.25"), Decimal("101.50")]


def test_yahoo_fx_symbol() -> None:
    assert yahoo_fx_symbol("eur", "gbp") == "EURGBP=X"


def test_import_market_data_from_delta_upserts_ohlcv(tmp_path: Path) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    prices_path = tmp_path / "prices"
    fx_path = tmp_path / "fx"
    columns = {
        "date": [date(2026, 6, 20)],
        "open": [Decimal("99.5")],
        "high": [Decimal("102")],
        "low": [Decimal("98")],
        "close": [Decimal("101.5")],
        "volume": [Decimal("1000")],
    }
    write_deltalake(
        prices_path,
        pa.Table.from_pydict({"symbol": ["AAPL"], **columns}),
    )
    write_deltalake(
        fx_path,
        pa.Table.from_pydict({"symbol": ["EURGBP=X"], **columns}),
    )

    with Session(engine) as session:
        session.add(
            Security(
                ticker="AAPL",
                name="Apple Inc.",
                asset_class=AssetClass.EQUITY,
                currency_code="USD",
            )
        )
        session.commit()

        result = import_market_data_from_delta_for_session(
            session,
            market_prices_path=prices_path,
            fx_rates_path=fx_path,
        )
        session.commit()
        price = session.scalar(select(PriceHistory))
        fx_rate = session.scalar(select(FxRateHistory))

    assert result.prices_upserted == 1
    assert result.fx_rates_upserted == 1
    assert price is not None
    assert price.symbol == "AAPL"
    assert price.open == Decimal("99.5000000000")
    assert price.close_price == Decimal("101.5000000000")
    assert price.volume == Decimal("1000.0000000000")
    assert fx_rate is not None
    assert fx_rate.symbol == "EURGBP=X"
    assert fx_rate.rate == Decimal("101.5000000000")

    updated_columns = {
        **columns,
        "close": [Decimal("105.2")],
        "volume": [Decimal("1250")],
    }
    write_deltalake(
        prices_path,
        pa.Table.from_pydict({"symbol": ["AAPL"], **updated_columns}),
        mode="overwrite",
    )
    write_deltalake(
        fx_path,
        pa.Table.from_pydict({"symbol": ["EURGBP=X"], **updated_columns}),
        mode="overwrite",
    )

    with Session(engine) as session:
        merged = import_market_data_from_delta_for_session(
            session,
            market_prices_path=prices_path,
            fx_rates_path=fx_path,
        )
        session.commit()
        price = session.scalar(select(PriceHistory))
        fx_rate = session.scalar(select(FxRateHistory))

    assert merged.prices_upserted == 1
    assert merged.fx_rates_upserted == 1
    assert price is not None
    assert price.close == Decimal("105.2000000000")
    assert price.volume == Decimal("1250.0000000000")
    assert fx_rate is not None
    assert fx_rate.close == Decimal("105.2000000000")


def test_parse_fx_symbol_accepts_common_formats() -> None:
    assert parse_fx_symbol("EURGBP=X") == ("EUR", "GBP")
    assert parse_fx_symbol("eur/gbp") == ("EUR", "GBP")


def test_delta_import_logs_row_errors() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        result = import_market_data_from_delta_for_session(
            session,
            market_prices_path=None,
            fx_rates_path=None,
        )
        session.commit()
        errors = session.scalars(
            select(ImportErrorLog).order_by(ImportErrorLog.pipeline_name)
        ).all()

    assert len(result.skipped) == 2
    assert [error.pipeline_name for error in errors] == [
        "delta_fx_rates",
        "delta_market_prices",
    ]
    assert all(error.timestamp is not None for error in errors)
