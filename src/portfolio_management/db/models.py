from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, synonym

from portfolio_management.db.base import Base
from portfolio_management.db.types import SqliteDecimal


class AssetClass(StrEnum):
    CASH = "CASH"
    EQUITY = "EQUITY"
    BOND = "BOND"
    FUND = "FUND"
    CRYPTO = "CRYPTO"
    REAL_ESTATE = "REAL_ESTATE"
    COMMODITY = "COMMODITY"
    OTHER = "OTHER"


class TransactionType(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    DIVIDEND = "DIVIDEND"
    SPLIT = "SPLIT"
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"


class OrderType(StrEnum):
    BUY = "BUY"
    SELL = "SELL"
    DEPOSIT = "DEPOSIT"
    WITHDRAW = "WITHDRAW"


class OrderStatus(StrEnum):
    PENDING = "PENDING"
    EXECUTED = "EXECUTED"
    CANCELLED = "CANCELLED"


class AssetClassOption(Base):
    __tablename__ = "asset_classes"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Currency(Base):
    __tablename__ = "currencies"

    code: Mapped[str] = mapped_column(String(3), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Broker(Base):
    __tablename__ = "brokers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    trade_fee_fixed: Mapped[Decimal] = mapped_column(Numeric(32, 10), nullable=False, default=Decimal("0"))
    trade_fee_percent: Mapped[Decimal] = mapped_column(Numeric(32, 10), nullable=False, default=Decimal("0"))
    fx_fee_percent: Mapped[Decimal] = mapped_column(Numeric(32, 10), nullable=False, default=Decimal("0"))
    spread_fee_percent: Mapped[Decimal] = mapped_column(Numeric(32, 10), nullable=False, default=Decimal("0"))
    custody_fee_percent_annual: Mapped[Decimal] = mapped_column(
        Numeric(32, 10),
        nullable=False,
        default=Decimal("0"),
    )
    platform_fee_fixed_monthly: Mapped[Decimal] = mapped_column(
        Numeric(32, 10),
        nullable=False,
        default=Decimal("0"),
    )
    account_fee_fixed_monthly: Mapped[Decimal] = mapped_column(
        Numeric(32, 10),
        nullable=False,
        default=Decimal("0"),
    )
    inactivity_fee_fixed_monthly: Mapped[Decimal] = mapped_column(
        Numeric(32, 10),
        nullable=False,
        default=Decimal("0"),
    )
    withdrawal_fee_fixed: Mapped[Decimal] = mapped_column(
        Numeric(32, 10),
        nullable=False,
        default=Decimal("0"),
    )
    deposit_fee_fixed: Mapped[Decimal] = mapped_column(Numeric(32, 10), nullable=False, default=Decimal("0"))
    stamp_duty_percent: Mapped[Decimal] = mapped_column(Numeric(32, 10), nullable=False, default=Decimal("0"))
    regulatory_fee_percent: Mapped[Decimal] = mapped_column(
        Numeric(32, 10),
        nullable=False,
        default=Decimal("0"),
    )
    margin_interest_percent_annual: Mapped[Decimal] = mapped_column(
        Numeric(32, 10),
        nullable=False,
        default=Decimal("0"),
    )
    short_borrow_fee_percent_annual: Mapped[Decimal] = mapped_column(
        Numeric(32, 10),
        nullable=False,
        default=Decimal("0"),
    )

    accounts: Mapped[list["Account"]] = relationship(back_populates="broker")


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    broker_id: Mapped[int] = mapped_column(ForeignKey("brokers.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000))
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    tax_wrapper_type: Mapped[str | None] = mapped_column(String(64))
    is_simulated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    broker: Mapped[Broker] = relationship(back_populates="accounts")
    portfolios: Mapped[list["Portfolio"]] = relationship(
        back_populates="account",
        cascade="all, delete-orphan",
    )
    account_strategies: Mapped[list["AccountStrategy"]] = relationship(
        back_populates="account",
        cascade="all, delete-orphan",
    )

    __table_args__ = (UniqueConstraint("broker_id", "name", name="uq_accounts_broker_name"),)


class Portfolio(Base):
    __tablename__ = "portfolios"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000))
    portfolio_url: Mapped[str | None] = mapped_column(String(2000))
    portfolio_goals: Mapped[str | None] = mapped_column(Text)
    goal_type: Mapped[str | None] = mapped_column(String(64))
    goal_timeline: Mapped[str | None] = mapped_column(String(64))
    rewritten_goals: Mapped[str | None] = mapped_column(Text)
    strategy_recommendation: Mapped[str | None] = mapped_column(Text)
    portfolio_profile: Mapped[str | None] = mapped_column(Text)
    ai_notes: Mapped[str | None] = mapped_column(Text)
    llm_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    account: Mapped[Account] = relationship(back_populates="portfolios")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="portfolio")
    orders: Mapped[list["Order"]] = relationship(back_populates="portfolio")

    __table_args__ = (
        UniqueConstraint("account_id", "name", name="uq_portfolios_account_name"),
    )


class Strategy(Base):
    __tablename__ = "strategies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000))

    account_strategies: Mapped[list["AccountStrategy"]] = relationship(
        back_populates="strategy",
        cascade="all, delete-orphan",
    )


class AccountStrategy(Base):
    __tablename__ = "account_strategies"

    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), primary_key=True)
    strategy_id: Mapped[int] = mapped_column(ForeignKey("strategies.id"), primary_key=True)
    allocation_weight: Mapped[Decimal] = mapped_column(Numeric(32, 10), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )

    account: Mapped[Account] = relationship(back_populates="account_strategies")
    strategy: Mapped[Strategy] = relationship(back_populates="account_strategies")


class Security(Base):
    __tablename__ = "securities"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000))
    asset_class: Mapped[AssetClass] = mapped_column(Enum(AssetClass), nullable=False)
    asset_subclass: Mapped[str] = mapped_column(String(64), nullable=False, default="STOCK")
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")

    transactions: Mapped[list["Transaction"]] = relationship(back_populates="security")
    orders: Mapped[list["Order"]] = relationship(back_populates="security")
    price_history: Mapped[list["PriceHistory"]] = relationship(
        back_populates="security",
        cascade="all, delete-orphan",
    )


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id"), nullable=False)
    security_id: Mapped[int | None] = mapped_column(ForeignKey("securities.id"))
    order_type: Mapped[OrderType] = mapped_column(Enum(OrderType), nullable=False)
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus),
        nullable=False,
        default=OrderStatus.PENDING,
    )
    target_quantity: Mapped[Decimal | None] = mapped_column(Numeric(32, 10))
    target_price: Mapped[Decimal | None] = mapped_column(Numeric(32, 10))
    target_cash_amount: Mapped[Decimal | None] = mapped_column(Numeric(32, 10))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    portfolio: Mapped[Portfolio] = relationship(back_populates="orders")
    security: Mapped[Security | None] = relationship(back_populates="orders")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="order")


class Benchmark(Base):
    __tablename__ = "benchmarks"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"))
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id"), nullable=False)
    security_id: Mapped[int | None] = mapped_column(ForeignKey("securities.id"))
    date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    type: Mapped[TransactionType] = mapped_column(Enum(TransactionType), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000))
    quantity: Mapped[Decimal] = mapped_column(Numeric(32, 10), nullable=False, default=Decimal("0"))
    price: Mapped[Decimal] = mapped_column(Numeric(32, 10), nullable=False, default=Decimal("0"))
    fees: Mapped[Decimal] = mapped_column(Numeric(32, 10), nullable=False, default=Decimal("0"))
    total_value: Mapped[Decimal] = mapped_column(Numeric(32, 10), nullable=False)
    currency_exchange_rate: Mapped[Decimal] = mapped_column(
        Numeric(32, 10),
        nullable=False,
        default=Decimal("1"),
    )

    portfolio: Mapped[Portfolio] = relationship(back_populates="transactions")
    security: Mapped[Security | None] = relationship(back_populates="transactions")
    order: Mapped[Order | None] = relationship(back_populates="transactions")


class ImportErrorLog(Base):
    __tablename__ = "import_error_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    pipeline_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)


class PortfolioAlert(Base):
    __tablename__ = "portfolio_alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    alert_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=text("CURRENT_TIMESTAMP"),
    )
    alert_type: Mapped[str] = mapped_column(String(32), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_acknowledged: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("0"),
    )

    __table_args__ = (
        UniqueConstraint("alert_hash", name="uq_portfolio_alerts_alert_hash"),
    )


class PriceHistory(Base):
    __tablename__ = "price_history"

    security_id: Mapped[int] = mapped_column(ForeignKey("securities.id"), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    symbol: Mapped[str | None] = mapped_column(String(32))
    open: Mapped[Decimal | None] = mapped_column(Numeric(32, 10))
    high: Mapped[Decimal | None] = mapped_column(Numeric(32, 10))
    low: Mapped[Decimal | None] = mapped_column(Numeric(32, 10))
    close: Mapped[Decimal] = mapped_column(Numeric(32, 10), nullable=False)
    volume: Mapped[Decimal | None] = mapped_column(Numeric(32, 10))
    close_price = synonym("close")

    security: Mapped[Security] = relationship(back_populates="price_history")

    __table_args__ = (
        UniqueConstraint("security_id", "date", name="uq_price_history_security_date"),
    )


class FxRateHistory(Base):
    __tablename__ = "fx_rate_history"

    base_currency_code: Mapped[str] = mapped_column(String(3), primary_key=True)
    quote_currency_code: Mapped[str] = mapped_column(String(3), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    symbol: Mapped[str | None] = mapped_column(String(32))
    open: Mapped[Decimal | None] = mapped_column(Numeric(32, 10))
    high: Mapped[Decimal | None] = mapped_column(Numeric(32, 10))
    low: Mapped[Decimal | None] = mapped_column(Numeric(32, 10))
    close: Mapped[Decimal] = mapped_column(Numeric(32, 10), nullable=False)
    volume: Mapped[Decimal | None] = mapped_column(Numeric(32, 10))
    rate = synonym("close")

    __table_args__ = (
        UniqueConstraint(
            "base_currency_code",
            "quote_currency_code",
            "date",
            name="uq_fx_rate_history_pair_date",
        ),
    )
