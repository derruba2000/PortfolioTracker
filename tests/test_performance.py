from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import numpy as np
import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from portfolio_management.db.base import Base
from portfolio_management.db.models import (
    Account,
    AssetClass,
    Broker,
    Portfolio,
    PriceHistory,
    Security,
    Transaction,
    TransactionType,
)
from portfolio_management.services.db_performance import (
    asset_price_history,
    cash_flow_history,
    portfolio_value_history,
)
from portfolio_management.services.performance import (
    benchmark_metrics,
    calculate_mwr,
    calculate_twr,
    correlation_matrix,
    drawdown_curve,
    historical_stress_tests,
    risk_metrics,
)


def test_performance_data_layer_extracts_values_prices_and_external_flows(
    monkeypatch,
) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        broker = Broker(name="Broker")
        account = Account(broker=broker, name="Account", currency_code="GBP")
        portfolio = Portfolio(account=account, name="Portfolio")
        security = Security(
            ticker="ETF.L",
            name="ETF",
            asset_class=AssetClass.ETF,
            currency_code="GBP",
        )
        session.add_all(
            [
                Transaction(
                    portfolio=portfolio,
                    date=datetime(2026, 1, 1),
                    type=TransactionType.DEPOSIT,
                    quantity=100,
                    price=Decimal("1"),
                    fees=Decimal("0"),
                    total_value=Decimal("100"),
                    currency_exchange_rate=Decimal("1"),
                ),
                Transaction(
                    portfolio=portfolio,
                    security=security,
                    date=datetime(2026, 1, 1),
                    type=TransactionType.BUY,
                    quantity=10,
                    price=Decimal("10"),
                    fees=Decimal("0"),
                    total_value=Decimal("100"),
                    currency_exchange_rate=Decimal("1"),
                ),
                PriceHistory(
                    security=security,
                    date=date(2026, 1, 1),
                    close=Decimal("10"),
                ),
                PriceHistory(
                    security=security,
                    date=date(2026, 1, 2),
                    close=Decimal("11"),
                ),
            ]
        )
        session.commit()

    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    monkeypatch.setattr(
        "portfolio_management.services.db_performance.get_session_factory",
        lambda: factory,
    )

    values = portfolio_value_history(
        reporting_currency="GBP",
        end_date=date(2026, 1, 2),
    )
    flows = cash_flow_history(
        reporting_currency="GBP",
        end_date=date(2026, 1, 2),
    )
    prices = asset_price_history(end_date=date(2026, 1, 2))

    assert list(values["Portfolio Value"]) == [100.0, 110.0]
    assert flows.to_dict("records") == [{"Date": "2026-01-01", "Cash Flow": 100.0}]
    assert list(prices["Close"]) == [10.0, 11.0]


def test_portfolio_value_without_explicit_cash_uses_full_holding_value(
    monkeypatch,
) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        broker = Broker(name="Broker")
        account = Account(broker=broker, name="Account", currency_code="USD")
        portfolio = Portfolio(account=account, name="Portfolio")
        security = Security(
            ticker="ETF",
            name="ETF",
            asset_class=AssetClass.ETF,
            currency_code="USD",
        )
        session.add_all(
            [
                Transaction(
                    portfolio=portfolio,
                    security=security,
                    date=datetime(2026, 1, 1),
                    type=TransactionType.BUY,
                    quantity=10,
                    price=Decimal("10"),
                    fees=Decimal("0"),
                    total_value=Decimal("100"),
                    currency_exchange_rate=Decimal("1"),
                ),
                PriceHistory(
                    security=security,
                    date=date(2026, 1, 1),
                    close=Decimal("10"),
                ),
                PriceHistory(
                    security=security,
                    date=date(2026, 1, 2),
                    close=Decimal("11"),
                ),
            ]
        )
        session.commit()

    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    monkeypatch.setattr(
        "portfolio_management.services.db_performance.get_session_factory",
        lambda: factory,
    )

    values = portfolio_value_history(
        reporting_currency="USD",
        end_date=date(2026, 1, 2),
    )

    assert list(values["Portfolio Value"]) == [100.0, 110.0]


def test_return_drawdown_and_mwr_calculations() -> None:
    values = pd.DataFrame(
        {
            "Date": ["2025-01-01", "2025-12-31", "2026-01-01"],
            "Portfolio Value": [100.0, 110.0, 99.0],
        }
    )
    flows = pd.DataFrame(
        {"Date": ["2025-01-01"], "Cash Flow": [100.0]}
    )

    twr = calculate_twr(values, flows)
    mwr = calculate_mwr(values.iloc[:2], flows)
    drawdown = drawdown_curve(values)

    assert np.isclose(twr.iloc[1]["TWR"], 0.10)
    assert np.isclose(twr.iloc[2]["TWR"], -0.01)
    assert np.isclose(mwr.iloc[-1]["MWR"], 0.10, atol=0.002)
    assert np.isclose(drawdown.iloc[-1]["Drawdown"], -0.10)


def test_risk_benchmark_correlation_and_stress_metrics() -> None:
    index = pd.date_range("2026-01-01", periods=4)
    portfolio = pd.Series([0.01, -0.01, 0.02, 0.0], index=index)
    benchmark = pd.Series([0.005, -0.005, 0.01, 0.0], index=index)

    risk = risk_metrics(portfolio, benchmark, risk_free_rate=0.0)
    comparison = benchmark_metrics(portfolio, benchmark)
    correlations = correlation_matrix(
        pd.DataFrame(
            {
                "Date": list(index.astype(str)) * 2,
                "Ticker": ["A"] * 4 + ["B"] * 4,
                "Close": [100, 101, 100, 102, 200, 202, 200, 204],
            }
        )
    )
    stress = historical_stress_tests(
        pd.DataFrame(
            {
                "Date": ["2026-01-01", "2026-01-02"],
                "Portfolio Value": [100.0, 80.0],
            }
        ),
        {"Test Shock": (date(2026, 1, 1), date(2026, 1, 2))},
    )

    assert np.isfinite(risk["Volatility"])
    assert np.isclose(risk["Beta"], 2.0)
    assert np.isclose(comparison["R-Squared"], 1.0)
    assert set(correlations.columns) == {"A", "B"}
    assert np.isclose(stress.iloc[0]["Return"], -0.20)
