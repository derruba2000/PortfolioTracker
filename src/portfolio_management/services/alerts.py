from __future__ import annotations

import argparse
import hashlib
import time
import warnings
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

import pandas as pd
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from portfolio_management.config import load_settings
from portfolio_management.db.models import (
    Account,
    Broker,
    ImportErrorLog,
    PortfolioAlert,
    PriceHistory,
)
from portfolio_management.db.session import get_session_factory
from portfolio_management.services.market_data import list_tracked_securities
from portfolio_management.services.notifications import create_discord_dispatcher
from portfolio_management.services.rebalancing import rebalance_report


PRICE_DROP = "PRICE_DROP"
DRIFT = "DRIFT"


@dataclass(frozen=True)
class AlertCondition:
    alert_type: str
    subject: str
    event_date: date
    message: str


@dataclass(frozen=True)
class MonitorResult:
    price_conditions: int = 0
    drift_conditions: int = 0
    alerts_created: int = 0


AlertDispatcher = Callable[[PortfolioAlert], None]


def list_alerts(is_acknowledged: bool) -> pd.DataFrame:
    session_factory = get_session_factory()
    with session_factory() as session:
        alerts = session.scalars(
            select(PortfolioAlert)
            .where(PortfolioAlert.is_acknowledged.is_(is_acknowledged))
            .order_by(PortfolioAlert.timestamp.desc(), PortfolioAlert.id.desc())
        ).all()
    return pd.DataFrame(
        [
            {
                "ID": alert.id,
                "Timestamp": alert.timestamp.isoformat(sep=" ", timespec="seconds"),
                "Type": alert.alert_type,
                "Message": alert.message,
            }
            for alert in alerts
        ],
        columns=["ID", "Timestamp", "Type", "Message"],
    )


def active_alert_choices() -> list[tuple[str, str]]:
    session_factory = get_session_factory()
    with session_factory() as session:
        alerts = session.scalars(
            select(PortfolioAlert)
            .where(PortfolioAlert.is_acknowledged.is_(False))
            .order_by(PortfolioAlert.timestamp.desc(), PortfolioAlert.id.desc())
        ).all()
    return [
        (
            f"#{alert.id} | {alert.alert_type} | "
            f"{alert.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            alert.alert_hash,
        )
        for alert in alerts
    ]


def acknowledge_alerts(alert_hashes: Sequence[str] | None) -> int:
    selected_hashes = {
        str(alert_hash).strip()
        for alert_hash in (alert_hashes or [])
        if str(alert_hash).strip()
    }
    if not selected_hashes:
        return 0

    session_factory = get_session_factory()
    with session_factory() as session:
        result = session.execute(
            update(PortfolioAlert)
            .where(
                PortfolioAlert.alert_hash.in_(selected_hashes),
                PortfolioAlert.is_acknowledged.is_(False),
            )
            .values(is_acknowledged=True)
        )
        session.commit()
        return int(result.rowcount or 0)


def purge_all_alerts() -> tuple[int, int]:
    """Delete all rows from portfolio_alerts and import_error_logs.

    Returns a tuple of (alerts_deleted, import_errors_deleted).
    """
    session_factory = get_session_factory()
    with session_factory() as session:
        alerts_result = session.execute(delete(PortfolioAlert))
        errors_result = session.execute(delete(ImportErrorLog))
        session.commit()
    return int(alerts_result.rowcount or 0), int(errors_result.rowcount or 0)


def detect_price_drop(
    symbol: str,
    latest_price: Decimal | str | float,
    previous_close: Decimal | str | float,
    threshold_pct: Decimal | str | float,
    event_date: date,
    trailing_stop: Decimal | str | float | None = None,
) -> AlertCondition | None:
    latest = Decimal(str(latest_price))
    comparison_price = Decimal(
        str(trailing_stop if trailing_stop is not None else previous_close)
    )
    threshold = Decimal(str(threshold_pct))
    if comparison_price <= 0:
        raise ValueError("Previous close or trailing stop must be greater than zero.")
    if threshold < 0:
        raise ValueError("Price-drop threshold cannot be negative.")

    drop_pct = ((comparison_price - latest) / comparison_price) * Decimal("100")
    if drop_pct <= threshold:
        return None

    reference = "trailing stop" if trailing_stop is not None else "previous close"
    message = (
        f"PRICE ALERT: {symbol} dropped by {_format_pct(drop_pct)}% from its "
        f"{reference}, exceeding the {_format_pct(threshold)}% threshold."
    )
    return AlertCondition(
        alert_type=PRICE_DROP,
        subject=symbol,
        event_date=event_date,
        message=message,
    )


def detect_portfolio_drift(
    account_id: int,
    report: pd.DataFrame,
    tolerance_pct: Decimal | str | float,
    event_date: date,
    account_name: str | None = None,
) -> list[AlertCondition]:
    tolerance = Decimal(str(tolerance_pct))
    if tolerance < 0:
        raise ValueError("Drift tolerance cannot be negative.")

    conditions = []
    for row in report.to_dict("records"):
        drift = Decimal(str(row["Drift %"]))
        if abs(drift) <= tolerance:
            continue
        asset_class = str(row["Asset Class"])
        direction = "above" if drift > 0 else "below"
        account_label = account_name or f"Account {account_id}"
        conditions.append(
            AlertCondition(
                alert_type=DRIFT,
                subject=f"ACCOUNT-{account_id}:{asset_class}",
                event_date=event_date,
                message=(
                    f"DRIFT ALERT: {asset_class} is {_format_pct(abs(drift))}% "
                    f"{direction} target for {account_label}, exceeding the "
                    f"{_format_pct(tolerance)}% tolerance."
                ),
            )
        )
    return conditions


def alert_hash(alert_type: str, subject: str, event_date: date) -> str:
    payload = f"{alert_type}|{subject}|{event_date.isoformat()}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def create_alert(
    condition: AlertCondition,
    dispatcher: AlertDispatcher | None = None,
) -> PortfolioAlert | None:
    session_factory = get_session_factory()
    condition_hash = alert_hash(
        condition.alert_type,
        condition.subject,
        condition.event_date,
    )
    with session_factory() as session:
        existing = session.scalar(
            select(PortfolioAlert).where(PortfolioAlert.alert_hash == condition_hash)
        )
        if existing is not None:
            return None

        alert = PortfolioAlert(
            alert_hash=condition_hash,
            alert_type=condition.alert_type,
            message=condition.message,
        )
        session.add(alert)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            return None

    if dispatcher is not None:
        dispatcher(alert)
    return alert


def detect_stored_price_drops(
    threshold_pct: Decimal | str | float,
) -> list[AlertCondition]:
    session_factory = get_session_factory()
    with session_factory() as session:
        conditions = []
        for security in list_tracked_securities(session):
            prices = session.scalars(
                select(PriceHistory)
                .where(PriceHistory.security_id == security.id)
                .order_by(PriceHistory.date.desc())
                .limit(2)
            ).all()
            if len(prices) < 2:
                continue
            condition = detect_price_drop(
                symbol=security.ticker,
                latest_price=prices[0].close,
                previous_close=prices[1].close,
                threshold_pct=threshold_pct,
                event_date=prices[0].date,
            )
            if condition is not None:
                conditions.append(condition)
    return conditions


def detect_live_account_drifts(
    tolerance_pct: Decimal | str | float,
    event_date: date | None = None,
) -> list[AlertCondition]:
    event_date = event_date or date.today()
    session_factory = get_session_factory()
    with session_factory() as session:
        accounts = session.execute(
            select(Account.id, Account.name)
            .join(Account.broker)
            .where(
                Account.is_simulated.is_(False),
                Account.is_active.is_(True),
                Broker.is_active.is_(True),
            )
            .order_by(Account.id)
        ).all()

    conditions = []
    for account_id, account_name in accounts:
        report = rebalance_report(account_id)
        conditions.extend(
            detect_portfolio_drift(
                account_id=account_id,
                account_name=account_name,
                report=report,
                tolerance_pct=tolerance_pct,
                event_date=event_date,
            )
        )
    return conditions


def run_alert_monitor(
    dispatcher: AlertDispatcher | None = None,
    event_date: date | None = None,
) -> MonitorResult:
    settings = load_settings()
    price_conditions = detect_stored_price_drops(settings.price_drop_threshold_pct)
    drift_conditions = detect_live_account_drifts(
        settings.drift_tolerance_pct,
        event_date=event_date,
    )
    created = _create_alerts(price_conditions + drift_conditions, dispatcher)
    return MonitorResult(
        price_conditions=len(price_conditions),
        drift_conditions=len(drift_conditions),
        alerts_created=created,
    )


def monitor_forever(
    dispatcher: AlertDispatcher | None = None,
    interval_seconds: int = 300,
) -> None:
    if interval_seconds <= 0:
        raise ValueError("Monitor interval must be greater than zero.")
    while True:
        try:
            result = run_alert_monitor(dispatcher=dispatcher)
            _print_monitor_result(result)
        except Exception as exc:
            warnings.warn(f"Alert monitor cycle failed: {exc}", RuntimeWarning, stacklevel=2)
        time.sleep(interval_seconds)


def _create_alerts(
    conditions: Sequence[AlertCondition],
    dispatcher: AlertDispatcher | None,
) -> int:
    return sum(
        create_alert(condition, dispatcher=dispatcher) is not None
        for condition in conditions
    )


def _format_pct(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.1")), "f")


def _print_monitor_result(result: MonitorResult) -> None:
    checked_at = datetime.now().astimezone().isoformat(timespec="seconds")
    print(
        f"[{checked_at}] Alert cycle complete: "
        f"{result.price_conditions} price condition(s), "
        f"{result.drift_conditions} drift condition(s), "
        f"{result.alerts_created} new alert(s).",
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Monitor portfolio alert conditions.")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run one alert cycle and exit.",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=300,
        metavar="SECONDS",
        help="Seconds between cycles (default: 300).",
    )
    args = parser.parse_args()
    settings = load_settings()
    dispatcher = create_discord_dispatcher(settings.discord_webhook_url)

    if args.once:
        _print_monitor_result(run_alert_monitor(dispatcher=dispatcher))
        return

    print(
        f"Portfolio alert monitor started; checking every {args.interval} seconds. "
        "Press Ctrl+C to stop.",
        flush=True,
    )
    try:
        monitor_forever(
            dispatcher=dispatcher,
            interval_seconds=args.interval,
        )
    except KeyboardInterrupt:
        print("\nPortfolio alert monitor stopped.", flush=True)
