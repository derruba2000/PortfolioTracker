from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from portfolio_management.db.models import (
    Account,
    AssetClass,
    Broker,
    Portfolio,
    Security,
    Transaction,
    TransactionType,
)
from portfolio_management.db.session import get_session_factory
from portfolio_management.services.accounts import (
    DEFAULT_PORTFOLIO_NAME,
    get_or_create_account,
    get_or_create_broker,
    get_or_create_portfolio,
    parse_choice_id,
)


DEFAULT_BROKER_NAME = "Default Broker"
DEFAULT_ACCOUNT_NAME = "Default Account"
DEFAULT_CURRENCY_CODE = "USD"


CSV_COLUMN_ALIASES = {
    "broker": "broker_name",
    "broker_name": "broker_name",
    "account": "account_name",
    "account_name": "account_name",
    "portfolio": "portfolio_name",
    "portfolio_name": "portfolio_name",
    "portfolio_id": "portfolio_id",
    "account_currency": "account_currency_code",
    "account_currency_code": "account_currency_code",
    "tax_wrapper_type": "tax_wrapper_type",
    "tax_wrapper": "tax_wrapper_type",
    "is_simulated": "is_simulated",
    "simulated": "is_simulated",
    "date": "date",
    "transaction_date": "date",
    "type": "transaction_type",
    "transaction_type": "transaction_type",
    "description": "description",
    "notes": "description",
    "note": "description",
    "memo": "description",
    "ticker": "ticker",
    "symbol": "ticker",
    "security_name": "security_name",
    "name": "security_name",
    "asset_class": "asset_class",
    "security_currency": "security_currency_code",
    "security_currency_code": "security_currency_code",
    "currency": "security_currency_code",
    "quantity": "quantity",
    "shares": "quantity",
    "price": "price",
    "fees": "fees",
    "fee": "fees",
    "total": "total_value",
    "total_value": "total_value",
    "amount": "total_value",
    "fx_rate": "currency_exchange_rate",
    "currency_exchange_rate": "currency_exchange_rate",
}


@dataclass(frozen=True)
class TransactionInput:
    date: datetime
    transaction_type: TransactionType
    ticker: str | None
    quantity: int
    price: Decimal
    fees: Decimal = Decimal("0")
    total_value: Decimal | None = None
    currency_exchange_rate: Decimal = Decimal("1")
    description: str | None = None
    broker_name: str = DEFAULT_BROKER_NAME
    account_name: str = DEFAULT_ACCOUNT_NAME
    portfolio_id: int | None = None
    portfolio_name: str = DEFAULT_PORTFOLIO_NAME
    account_currency_code: str = DEFAULT_CURRENCY_CODE
    tax_wrapper_type: str | None = None
    is_simulated: bool = False
    security_name: str | None = None
    asset_class: AssetClass = AssetClass.EQUITY
    security_currency_code: str = DEFAULT_CURRENCY_CODE


def create_transaction(session: Session, transaction_input: TransactionInput) -> Transaction:
    _validate_transaction_input(transaction_input)

    portfolio = _resolve_portfolio(session, transaction_input)
    security = _get_or_create_security(session, transaction_input)
    total_value = _calculate_total_value(transaction_input)

    transaction = Transaction(
        portfolio=portfolio,
        security=security,
        date=transaction_input.date,
        type=transaction_input.transaction_type,
        description=transaction_input.description,
        quantity=transaction_input.quantity,
        price=transaction_input.price,
        fees=transaction_input.fees,
        total_value=total_value,
        currency_exchange_rate=transaction_input.currency_exchange_rate,
    )
    session.add(transaction)
    session.flush()
    return transaction


def add_manual_transaction(**raw_values: Any) -> str:
    transaction_input = transaction_input_from_mapping(raw_values)
    session_factory = get_session_factory()

    with session_factory() as session:
        transaction = create_transaction(session, transaction_input)
        session.commit()

    ticker = transaction_input.ticker or "cash"
    return f"Added transaction #{transaction.id}: {transaction_input.transaction_type.value} {ticker}"


def transfer_cash(
    source_account_choice: str | int | None,
    target_account_choice: str | int | None,
    amount: str | Decimal,
    transfer_date: Any,
    description: str = "",
) -> str:
    source_account_id = parse_choice_id(source_account_choice)
    target_account_id = parse_choice_id(target_account_choice)

    if source_account_id is None or target_account_id is None:
        raise ValueError("Source and target accounts are required.")
    if source_account_id == target_account_id:
        raise ValueError("Source and target accounts must be different.")

    transfer_amount = _parse_decimal(amount, default=Decimal("0"))
    if transfer_amount <= 0:
        raise ValueError("Transfer amount must be greater than zero.")

    session_factory = get_session_factory()
    with session_factory() as session:
        source_account = session.get(Account, source_account_id)
        target_account = session.get(Account, target_account_id)
        if source_account is None or target_account is None:
            raise ValueError("Source or target account does not exist.")

        if source_account.currency_code != target_account.currency_code:
            raise ValueError("Source and target accounts must have the same currency code.")

        source_portfolio = get_or_create_portfolio(session, source_account, DEFAULT_PORTFOLIO_NAME)
        target_portfolio = get_or_create_portfolio(session, target_account, DEFAULT_PORTFOLIO_NAME)

        parsed_transfer_date = _parse_datetime(transfer_date)
        transfer_note = (
            f"Cash transfer | source account: {source_account.name} | "
            f"target account: {target_account.name} | cash transferred: {transfer_amount}"
        )
        user_description = _clean_string(description)
        if user_description:
            transfer_note = f"{transfer_note} | note: {user_description}"

        withdrawal = create_transaction(
            session,
            TransactionInput(
                portfolio_id=source_portfolio.id,
                date=parsed_transfer_date,
                transaction_type=TransactionType.WITHDRAWAL,
                ticker=None,
                quantity=1,
                price=transfer_amount,
                fees=Decimal("0"),
                currency_exchange_rate=Decimal("1"),
                description=transfer_note,
            ),
        )
        deposit = create_transaction(
            session,
            TransactionInput(
                portfolio_id=target_portfolio.id,
                date=parsed_transfer_date,
                transaction_type=TransactionType.DEPOSIT,
                ticker=None,
                quantity=1,
                price=transfer_amount,
                fees=Decimal("0"),
                currency_exchange_rate=Decimal("1"),
                description=transfer_note,
            ),
        )
        session.commit()

    return (
        f"Transferred {transfer_amount} {source_account.currency_code} from "
        f"'{source_account.name}' to '{target_account.name}' "
        f"(transactions #{withdrawal.id} and #{deposit.id})."
    )


def import_transactions_from_dataframe(
    session: Session,
    dataframe: pd.DataFrame,
    portfolio_id: int | None = None,
) -> int:
    normalized = _normalize_dataframe(dataframe)
    imported_count = 0

    for row_number, row in normalized.iterrows():
        try:
            row_values = row.to_dict()
            if portfolio_id is not None:
                row_values["portfolio_id"] = portfolio_id
            transaction_input = transaction_input_from_mapping(row_values)
            create_transaction(session, transaction_input)
            imported_count += 1
        except Exception as exc:
            raise ValueError(f"CSV row {row_number + 2}: {exc}") from exc

    session.flush()
    return imported_count


def import_transactions_from_csv(file_path: str | Path, portfolio_id: int | str | None) -> str:
    dataframe = pd.read_csv(file_path)
    session_factory = get_session_factory()
    parsed_portfolio_id = parse_choice_id(portfolio_id)
    if parsed_portfolio_id is None:
        raise ValueError("Choose a portfolio before importing CSV transactions.")

    with session_factory() as session:
        imported_count = import_transactions_from_dataframe(
            session,
            dataframe,
            portfolio_id=parsed_portfolio_id,
        )
        session.commit()

    return f"Imported {imported_count} transaction(s)."


def list_transactions(account_filter: str = "All") -> pd.DataFrame:
    session_factory = get_session_factory()

    with session_factory() as session:
        stmt = (
            select(Transaction, Portfolio, Account, Broker, Security)
            .join(Transaction.portfolio)
            .join(Portfolio.account)
            .join(Account.broker)
            .join(Transaction.security, isouter=True)
            .order_by(Transaction.date.desc(), Transaction.id.desc())
        )
        if account_filter == "Real":
            stmt = stmt.where(Account.is_simulated.is_(False))
        elif account_filter == "Test":
            stmt = stmt.where(Account.is_simulated.is_(True))
        rows = session.execute(stmt).all()

    return pd.DataFrame(
        [
            {
                "ID": transaction.id,
                "Date": transaction.date.date().isoformat(),
                "Broker": broker.name,
                "Account": f"{account.name} [TEST]" if account.is_simulated else account.name,
                "Portfolio": portfolio.name,
                "Ticker": security.ticker if security else "",
                "Type": transaction.type.value,
                "Description": transaction.description or "",
                "Quantity": str(transaction.quantity),
                "Price": str(transaction.price),
                "Fees": str(transaction.fees),
                "Total Value": str(transaction.total_value),
                "FX Rate": str(transaction.currency_exchange_rate),
            }
            for transaction, portfolio, account, broker, security in rows
        ],
        columns=[
            "ID",
            "Date",
            "Broker",
            "Account",
            "Portfolio",
            "Ticker",
            "Type",
            "Description",
            "Quantity",
            "Price",
            "Fees",
            "Total Value",
            "FX Rate",
        ],
    )


def transaction_input_from_mapping(raw_values: dict[str, Any]) -> TransactionInput:
    values = _normalize_mapping(raw_values)
    transaction_type = _parse_transaction_type(values.get("transaction_type"))

    return TransactionInput(
        broker_name=_clean_string(values.get("broker_name")) or DEFAULT_BROKER_NAME,
        account_name=_clean_string(values.get("account_name")) or DEFAULT_ACCOUNT_NAME,
        portfolio_id=_parse_optional_int(values.get("portfolio_id")),
        portfolio_name=_clean_string(values.get("portfolio_name")) or DEFAULT_PORTFOLIO_NAME,
        account_currency_code=(
            _clean_string(values.get("account_currency_code")) or DEFAULT_CURRENCY_CODE
        ).upper(),
        tax_wrapper_type=_clean_string(values.get("tax_wrapper_type")) or None,
        is_simulated=_parse_bool(values.get("is_simulated")),
        date=_parse_datetime(values.get("date")),
        transaction_type=transaction_type,
        description=_clean_string(values.get("description")) or None,
        ticker=_clean_string(values.get("ticker")).upper()
        if _clean_string(values.get("ticker"))
        else None,
        security_name=_clean_string(values.get("security_name")),
        asset_class=_parse_asset_class(values.get("asset_class")),
        security_currency_code=(
            _clean_string(values.get("security_currency_code")) or DEFAULT_CURRENCY_CODE
        ).upper(),
        quantity=_parse_int(values.get("quantity"), default=0),
        price=_parse_decimal(values.get("price"), default=Decimal("0")),
        fees=_parse_decimal(values.get("fees"), default=Decimal("0")),
        total_value=_parse_optional_decimal(values.get("total_value")),
        currency_exchange_rate=_parse_decimal(
            values.get("currency_exchange_rate"),
            default=Decimal("1"),
        ),
    )


def _validate_transaction_input(transaction_input: TransactionInput) -> None:
    if transaction_input.transaction_type in {
        TransactionType.BUY,
        TransactionType.SELL,
        TransactionType.DIVIDEND,
        TransactionType.SPLIT,
    } and not transaction_input.ticker:
        raise ValueError(f"{transaction_input.transaction_type.value} transactions require a ticker.")

    if transaction_input.quantity < 0:
        raise ValueError("Quantity cannot be negative.")

    if transaction_input.price < 0:
        raise ValueError("Price cannot be negative.")

    if transaction_input.fees < 0:
        raise ValueError("Fees cannot be negative.")

    if transaction_input.currency_exchange_rate <= 0:
        raise ValueError("Currency exchange rate must be greater than zero.")

    if transaction_input.transaction_type in {TransactionType.BUY, TransactionType.SELL}:
        if transaction_input.quantity <= 0:
            raise ValueError("BUY and SELL transactions require quantity greater than zero.")
        if transaction_input.price <= 0:
            raise ValueError("BUY and SELL transactions require price greater than zero.")

    if transaction_input.transaction_type == TransactionType.SPLIT:
        if transaction_input.quantity <= 0:
            raise ValueError("SPLIT transactions store the split ratio in quantity.")
        if transaction_input.price != 0 or transaction_input.fees != 0:
            raise ValueError("SPLIT transactions must not have price or fees.")

    if (
        transaction_input.transaction_type == TransactionType.DIVIDEND
        and _calculate_total_value(transaction_input) <= 0
    ):
        raise ValueError("DIVIDEND transactions require a positive total value.")


def _calculate_total_value(transaction_input: TransactionInput) -> Decimal:
    if transaction_input.transaction_type == TransactionType.SPLIT:
        return Decimal("0")

    if transaction_input.total_value is not None:
        return transaction_input.total_value

    gross_value = Decimal(transaction_input.quantity) * transaction_input.price

    if transaction_input.transaction_type == TransactionType.BUY:
        return gross_value + transaction_input.fees

    if transaction_input.transaction_type == TransactionType.SELL:
        return gross_value - transaction_input.fees

    if transaction_input.transaction_type == TransactionType.DIVIDEND:
        return gross_value - transaction_input.fees

    if transaction_input.transaction_type == TransactionType.DEPOSIT:
        return gross_value

    if transaction_input.transaction_type == TransactionType.WITHDRAWAL:
        return -gross_value

    return gross_value


def _resolve_portfolio(session: Session, transaction_input: TransactionInput) -> Portfolio:
    if transaction_input.portfolio_id is not None:
        portfolio = session.get(Portfolio, transaction_input.portfolio_id)
        if portfolio is None:
            raise ValueError(f"Portfolio id {transaction_input.portfolio_id} does not exist.")
        return portfolio

    broker = get_or_create_broker(session, transaction_input.broker_name)
    account = get_or_create_account(
        session=session,
        broker=broker,
        name=transaction_input.account_name,
        currency_code=transaction_input.account_currency_code,
        tax_wrapper_type=transaction_input.tax_wrapper_type,
        is_simulated=transaction_input.is_simulated,
    )
    return get_or_create_portfolio(
        session=session,
        account=account,
        name=transaction_input.portfolio_name,
    )


def _get_or_create_security(
    session: Session,
    transaction_input: TransactionInput,
) -> Security | None:
    if transaction_input.transaction_type in {
        TransactionType.DEPOSIT,
        TransactionType.WITHDRAWAL,
    } and not transaction_input.ticker:
        return None

    if transaction_input.ticker is None:
        return None

    security = session.scalar(
        select(Security).where(Security.ticker == transaction_input.ticker)
    )
    if security is None:
        security = Security(
            ticker=transaction_input.ticker,
            name=transaction_input.security_name or transaction_input.ticker,
            asset_class=transaction_input.asset_class,
            currency_code=transaction_input.security_currency_code,
        )
        session.add(security)
        session.flush()
    return security


def _normalize_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame:
    if dataframe.empty:
        raise ValueError("CSV file has no rows.")

    dataframe = dataframe.rename(columns={column: _normalize_key(column) for column in dataframe.columns})
    dataframe = dataframe.rename(
        columns={
            column: CSV_COLUMN_ALIASES.get(column, column)
            for column in dataframe.columns
        }
    )
    return dataframe


def _normalize_mapping(raw_values: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in raw_values.items():
        normalized_key = CSV_COLUMN_ALIASES.get(_normalize_key(key), _normalize_key(key))
        normalized[normalized_key] = value
    return normalized


def _normalize_key(key: Any) -> str:
    return str(key).strip().lower().replace(" ", "_").replace("-", "_")


def _parse_transaction_type(value: Any) -> TransactionType:
    clean_value = _clean_string(value).upper()
    if not clean_value:
        raise ValueError("Transaction type is required.")

    try:
        return TransactionType(clean_value)
    except ValueError as exc:
        allowed = ", ".join(transaction_type.value for transaction_type in TransactionType)
        raise ValueError(f"Unsupported transaction type '{clean_value}'. Use one of: {allowed}.") from exc


def _parse_asset_class(value: Any) -> AssetClass:
    clean_value = _clean_string(value).upper()
    if not clean_value:
        return AssetClass.EQUITY

    try:
        return AssetClass(clean_value)
    except ValueError as exc:
        allowed = ", ".join(asset_class.value for asset_class in AssetClass)
        raise ValueError(f"Unsupported asset class '{clean_value}'. Use one of: {allowed}.") from exc


def _parse_datetime(value: Any) -> datetime:
    clean_value = _clean_string(value)
    if not clean_value:
        raise ValueError("Date is required.")

    parsed = pd.to_datetime(clean_value, errors="raise")
    if pd.isna(parsed):
        raise ValueError("Date is required.")
    return parsed.to_pydatetime()


def _parse_decimal(value: Any, default: Decimal) -> Decimal:
    if _is_missing(value):
        return default

    try:
        normalized = str(value).strip().replace(",", "")
        if normalized == "":
            return default
        return Decimal(normalized)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Invalid decimal value '{value}'.") from exc


def _parse_optional_decimal(value: Any) -> Decimal | None:
    if _is_missing(value):
        return None
    if str(value).strip() == "":
        return None
    return _parse_decimal(value, default=Decimal("0"))


def _parse_optional_int(value: Any) -> int | None:
    return parse_choice_id(_clean_string(value))


def _parse_int(value: Any, default: int) -> int:
    if _is_missing(value):
        return default

    try:
        normalized = str(value).strip().replace(",", "")
        if normalized == "":
            return default
        decimal_value = Decimal(normalized)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Invalid integer value '{value}'.") from exc

    if decimal_value != decimal_value.to_integral_value():
        raise ValueError(f"Quantity must be an integer value, got '{value}'.")

    return int(decimal_value)


def _parse_bool(value: Any) -> bool:
    clean_value = _clean_string(value).lower()
    return clean_value in {"1", "true", "yes", "y", "simulated", "test"}


def _clean_string(value: Any) -> str:
    if _is_missing(value):
        return ""
    return str(value).strip()


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False
