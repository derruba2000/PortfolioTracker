from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from portfolio_management.config import (
    AlertThresholdConfigurationWarning,
    load_settings,
)
from portfolio_management.db.base import Base
from portfolio_management.db.models import (
    Account,
    AssetClass,
    Broker,
    Portfolio,
    PortfolioAlert,
    PriceHistory,
    Security,
    Transaction,
    TransactionType,
)
from portfolio_management.services.alerts import (
    DRIFT,
    PRICE_DROP,
    AlertCondition,
    alert_hash,
    create_alert,
    detect_portfolio_drift,
    detect_price_drop,
    detect_stored_price_drops,
    main,
)


def test_price_drop_detection_supports_previous_close_and_trailing_stop() -> None:
    condition = detect_price_drop(
        symbol="VWRP.L",
        latest_price=Decimal("99.4"),
        previous_close=Decimal("100"),
        threshold_pct=Decimal("0.5"),
        event_date=date(2026, 6, 25),
    )

    assert condition is not None
    assert condition.alert_type == PRICE_DROP
    assert condition.subject == "VWRP.L"
    assert "dropped by 0.6%" in condition.message
    assert "0.5% threshold" in condition.message

    trailing_condition = detect_price_drop(
        symbol="VWRP.L",
        latest_price=Decimal("94"),
        previous_close=Decimal("93"),
        trailing_stop=Decimal("95"),
        threshold_pct=Decimal("0.5"),
        event_date=date(2026, 6, 25),
    )
    assert trailing_condition is not None
    assert "trailing stop" in trailing_condition.message


def test_price_drop_below_threshold_does_not_trigger() -> None:
    assert (
        detect_price_drop(
            symbol="VWRP.L",
            latest_price=Decimal("99.6"),
            previous_close=Decimal("100"),
            threshold_pct=Decimal("0.5"),
            event_date=date(2026, 6, 25),
        )
        is None
    )
    assert (
        detect_price_drop(
            symbol="VWRP.L",
            latest_price=Decimal("99.5"),
            previous_close=Decimal("100"),
            threshold_pct=Decimal("0.5"),
            event_date=date(2026, 6, 25),
        )
        is None
    )


def test_drift_detection_uses_rebalance_report_drift_percentages() -> None:
    report = pd.DataFrame(
        [
            {"Asset Class": "EQUITY", "Drift %": "5.1"},
            {"Asset Class": "CASH", "Drift %": "-5.1"},
            {"Asset Class": "BOND", "Drift %": "2"},
        ]
    )

    conditions = detect_portfolio_drift(
        account_id=7,
        account_name="Retirement ISA",
        report=report,
        tolerance_pct=Decimal("5"),
        event_date=date(2026, 6, 25),
    )

    assert [condition.alert_type for condition in conditions] == [DRIFT, DRIFT]
    assert [condition.subject for condition in conditions] == [
        "ACCOUNT-7:EQUITY",
        "ACCOUNT-7:CASH",
    ]
    assert "above target" in conditions[0].message
    assert "below target" in conditions[1].message
    assert "Retirement ISA" in conditions[0].message
    assert "account 7" not in conditions[0].message


def test_alert_hash_is_stable_and_changes_with_condition_identity() -> None:
    event_date = date(2026, 6, 25)
    first = alert_hash(PRICE_DROP, "VWRP.L", event_date)

    assert first == alert_hash(PRICE_DROP, "VWRP.L", event_date)
    assert first != alert_hash(DRIFT, "VWRP.L", event_date)
    assert len(first) == 64


def test_create_alert_is_idempotent_and_dispatches_only_new_alert(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = lambda: sessionmaker(bind=engine, expire_on_commit=False, future=True)
    monkeypatch.setattr("portfolio_management.services.alerts.get_session_factory", factory)
    dispatched = []
    condition = AlertCondition(
        alert_type=PRICE_DROP,
        subject="VWRP.L",
        event_date=date(2026, 6, 25),
        message="Price dropped",
    )

    first = create_alert(condition, dispatcher=dispatched.append)
    duplicate = create_alert(condition, dispatcher=dispatched.append)

    assert first is not None
    assert duplicate is None
    assert dispatched == [first]
    with Session(engine) as session:
        assert len(session.scalars(select(PortfolioAlert)).all()) == 1


def test_stored_price_detection_uses_latest_two_prices_for_tracked_securities(
    monkeypatch,
) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = lambda: sessionmaker(bind=engine, expire_on_commit=False, future=True)
    monkeypatch.setattr("portfolio_management.services.alerts.get_session_factory", factory)

    with Session(engine) as session:
        broker = Broker(name="Broker")
        account = Account(broker=broker, name="ISA", currency_code="GBP")
        portfolio = Portfolio(account=account, name="Core")
        security = Security(
            ticker="VWRP.L",
            name="Vanguard FTSE All-World",
            asset_class=AssetClass.EQUITY,
            currency_code="GBP",
        )
        session.add_all(
            [
                Transaction(
                    portfolio=portfolio,
                    security=security,
                    date=date(2026, 6, 1),
                    type=TransactionType.BUY,
                    quantity=1,
                    price=Decimal("100"),
                    fees=Decimal("0"),
                    total_value=Decimal("100"),
                    currency_exchange_rate=Decimal("1"),
                ),
                PriceHistory(
                    security=security,
                    date=date(2026, 6, 24),
                    close=Decimal("100"),
                ),
                PriceHistory(
                    security=security,
                    date=date(2026, 6, 25),
                    close=Decimal("99"),
                ),
            ]
        )
        session.commit()

    conditions = detect_stored_price_drops(Decimal("0.5"))

    assert len(conditions) == 1
    assert conditions[0].subject == "VWRP.L"
    assert conditions[0].event_date == date(2026, 6, 25)


def test_alert_thresholds_load_from_environment(monkeypatch) -> None:
    monkeypatch.setattr("portfolio_management.config.load_dotenv", lambda: None)
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/1/token")
    monkeypatch.setenv("PRICE_DROP_THRESHOLD_PCT", "0.75")
    monkeypatch.setenv("DRIFT_TOLERANCE_PCT", "4.25")

    settings = load_settings()

    assert settings.price_drop_threshold_pct == Decimal("0.75")
    assert settings.drift_tolerance_pct == Decimal("4.25")


def test_invalid_alert_threshold_uses_default(monkeypatch) -> None:
    monkeypatch.setattr("portfolio_management.config.load_dotenv", lambda: None)
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/1/token")
    monkeypatch.setenv("DRIFT_TOLERANCE_PCT", "not-a-number")

    with pytest.warns(AlertThresholdConfigurationWarning):
        settings = load_settings()

    assert settings.drift_tolerance_pct == Decimal("5.0")


def test_monitor_once_prints_cycle_result(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "portfolio_management.services.alerts.run_alert_monitor",
        lambda dispatcher=None: type(
            "Result",
            (),
            {
                "price_conditions": 2,
                "drift_conditions": 1,
                "alerts_created": 1,
            },
        )(),
    )
    monkeypatch.setattr("sys.argv", ["portfolio-monitor", "--once"])

    main()

    output = capsys.readouterr().out
    assert "2 price condition(s)" in output
    assert "1 drift condition(s)" in output
    assert "1 new alert(s)" in output
