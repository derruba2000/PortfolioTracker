from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from portfolio_management.db.base import Base
from portfolio_management.db.models import PortfolioAlert
from portfolio_management.services.alerts import (
    acknowledge_alerts,
    active_alert_choices,
    list_alerts,
)
from portfolio_management.tabs.alerts import acknowledge_selected_alerts


def _patch_alert_sessions(monkeypatch, engine) -> None:
    factory = lambda: sessionmaker(bind=engine, expire_on_commit=False, future=True)
    monkeypatch.setattr("portfolio_management.services.alerts.get_session_factory", factory)


def _seed_alerts(engine) -> tuple[PortfolioAlert, PortfolioAlert, PortfolioAlert]:
    now = datetime.now(UTC)
    with Session(engine) as session:
        oldest = PortfolioAlert(
            alert_hash="old-active",
            timestamp=now - timedelta(hours=2),
            alert_type="DRIFT",
            message="Older active alert",
        )
        newest = PortfolioAlert(
            alert_hash="new-active",
            timestamp=now,
            alert_type="PRICE_DROP",
            message="Newest active alert",
        )
        historical = PortfolioAlert(
            alert_hash="historical",
            timestamp=now - timedelta(hours=1),
            alert_type="DRIFT",
            message="Acknowledged alert",
            is_acknowledged=True,
        )
        session.add_all([oldest, newest, historical])
        session.commit()
    return oldest, newest, historical


def test_alert_tables_filter_and_sort_newest_first(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    _patch_alert_sessions(monkeypatch, engine)
    _seed_alerts(engine)

    active = list_alerts(False)
    historical = list_alerts(True)

    assert isinstance(active, pd.DataFrame)
    assert list(active["Message"]) == ["Newest active alert", "Older active alert"]
    assert list(historical["Message"]) == ["Acknowledged alert"]
    assert "Alert Hash" not in active.columns


def test_acknowledging_selected_hashes_moves_alerts_to_history(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    _patch_alert_sessions(monkeypatch, engine)
    _seed_alerts(engine)

    acknowledged = acknowledge_alerts(["new-active"])

    assert acknowledged == 1
    assert list(list_alerts(False)["Message"]) == ["Older active alert"]
    assert list(list_alerts(True)["Message"]) == [
        "Newest active alert",
        "Acknowledged alert",
    ]
    with Session(engine) as session:
        alert = session.scalar(
            select(PortfolioAlert).where(PortfolioAlert.alert_hash == "new-active")
        )
        assert alert is not None
        assert alert.is_acknowledged is True


def test_active_alert_choices_use_hash_values(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    _patch_alert_sessions(monkeypatch, engine)
    _seed_alerts(engine)

    choices = active_alert_choices()

    assert [value for _, value in choices] == ["new-active", "old-active"]
    assert choices[0][0].startswith("#")
    assert "PRICE_DROP" in choices[0][0]


def test_acknowledge_callback_refreshes_tables_and_choices(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    _patch_alert_sessions(monkeypatch, engine)
    _seed_alerts(engine)

    status, active, historical, choices_update = acknowledge_selected_alerts(
        ["new-active"]
    )

    assert status == "Acknowledged 1 alert(s)."
    assert list(active["Message"]) == ["Older active alert"]
    assert list(historical["Message"]) == [
        "Newest active alert",
        "Acknowledged alert",
    ]
    assert choices_update["value"] == []
    assert [value for _, value in choices_update["choices"]] == ["old-active"]
