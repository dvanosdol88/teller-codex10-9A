"""SQLAlchemy models for Teller cached data."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Optional

from sqlalchemy import Column, Date, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.types import JSON

Base = declarative_base()


class TimestampMixin:
    """Common columns for created/updated timestamps."""

    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=dt.datetime.utcnow,
        onupdate=dt.datetime.utcnow,
        nullable=False,
    )


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: str = Column(String, primary_key=True)
    access_token: str = Column(String, nullable=False, index=True)
    name: Optional[str] = Column(String, nullable=True)

    accounts = relationship("Account", back_populates="user", cascade="all, delete-orphan")


class Account(Base, TimestampMixin):
    __tablename__ = "accounts"

    id: str = Column(String, primary_key=True)
    user_id: str = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    name: Optional[str] = Column(String)
    institution: Optional[str] = Column(String)
    last_four: Optional[str] = Column(String)
    type: Optional[str] = Column(String)
    subtype: Optional[str] = Column(String)
    currency: Optional[str] = Column(String)
    raw: dict = Column(JSON, nullable=False)

    user = relationship("User", back_populates="accounts")
    balance = relationship(
        "Balance",
        back_populates="account",
        uselist=False,
        cascade="all, delete-orphan",
    )
    transactions = relationship(
        "Transaction",
        back_populates="account",
        cascade="all, delete-orphan",
        order_by="Transaction.date.desc()",
    )


class Balance(Base):
    __tablename__ = "balances"

    account_id: str = Column(String, ForeignKey("accounts.id"), primary_key=True)
    available: Optional[Decimal] = Column(Numeric(18, 2))
    ledger: Optional[Decimal] = Column(Numeric(18, 2))
    currency: Optional[str] = Column(String)
    raw: dict = Column(JSON, nullable=False)
    cached_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)

    account = relationship("Account", back_populates="balance")


class Transaction(Base):
    __tablename__ = "transactions"

    id: str = Column(String, primary_key=True)
    account_id: str = Column(String, ForeignKey("accounts.id"), index=True, nullable=False)
    description: Optional[str] = Column(Text)
    amount: Optional[Decimal] = Column(Numeric(18, 2))
    date: Optional[Date] = Column(Date)
    running_balance: Optional[Decimal] = Column(Numeric(18, 2))
    type: Optional[str] = Column(String)
    raw: dict = Column(JSON, nullable=False)
    cached_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False, index=True)

    account = relationship("Account", back_populates="transactions")
