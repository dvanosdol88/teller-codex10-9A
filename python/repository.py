"""Database persistence helpers."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal, InvalidOperation
from typing import Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models


class Repository:
    """Encapsulates database access patterns for cached Teller data."""

    def __init__(self, session: Session):
        self.session = session

    # ---------------- Users ---------------- #
    def upsert_user(self, user_id: str, access_token: str, name: Optional[str]) -> models.User:
        user = self.session.get(models.User, user_id)
        if user:
            user.access_token = access_token
            user.name = name or user.name
        else:
            user = models.User(id=user_id, access_token=access_token, name=name)
            self.session.add(user)
        return user

    def get_user_by_token(self, token: str) -> Optional[models.User]:
        stmt = select(models.User).where(models.User.access_token == token)
        return self.session.execute(stmt).scalar_one_or_none()

    # ---------------- Accounts ---------------- #
    def upsert_account(self, user: models.User, payload: dict) -> models.Account:
        account_id = payload.get("id")
        if not account_id:
            raise ValueError("Account payload missing id")
        account = self.session.get(models.Account, account_id)
        if account:
            # When a customer reconnects through Teller Connect they may receive
            # a brand new Teller ``user.id`` even though the underlying
            # accounts are the same.  Re-associate the existing account record
            # with the latest user so subsequent API requests made with the
            # fresh access token can see the cached data.
            account.user = user
            account.raw = payload
            account.name = payload.get("name")
            account.type = payload.get("type")
            account.subtype = payload.get("subtype")
            account.last_four = payload.get("last_four") or payload.get("lastFour")
            institution = payload.get("institution") or {}
            account.institution = institution.get("id") if isinstance(institution, dict) else institution
            account.currency = payload.get("currency")
        else:
            institution = payload.get("institution") or {}
            account = models.Account(
                id=account_id,
                user=user,
                raw=payload,
                name=payload.get("name"),
                type=payload.get("type"),
                subtype=payload.get("subtype"),
                last_four=payload.get("last_four") or payload.get("lastFour"),
                institution=institution.get("id") if isinstance(institution, dict) else institution,
                currency=payload.get("currency"),
            )
            self.session.add(account)
        return account

    def list_accounts(self, user: models.User) -> List[models.Account]:
        stmt = select(models.Account).where(models.Account.user_id == user.id).order_by(models.Account.name)
        return list(self.session.scalars(stmt))

    def get_account(self, account_id: str) -> Optional[models.Account]:
        return self.session.get(models.Account, account_id)

    # ---------------- Balances ---------------- #
    def update_balance(self, account: models.Account, payload: dict) -> models.Balance:
        balance = account.balance
        if balance:
            balance.raw = payload
            balance.available = _as_decimal(payload.get("available"))
            balance.ledger = _as_decimal(payload.get("ledger"))
            balance.currency = payload.get("currency")
            balance.cached_at = dt.datetime.utcnow()
        else:
            balance = models.Balance(
                account=account,
                raw=payload,
                available=_as_decimal(payload.get("available")),
                ledger=_as_decimal(payload.get("ledger")),
                currency=payload.get("currency"),
            )
            self.session.add(balance)
        return balance

    # ---------------- Transactions ---------------- #
    def replace_transactions(
        self,
        account: models.Account,
        payloads: Iterable[dict],
    ) -> List[models.Transaction]:
        transactions: List[models.Transaction] = []
        existing_ids = {t.id for t in account.transactions}
        seen = set()
        for payload in payloads:
            tx_id = payload.get("id")
            if not tx_id or tx_id in seen:
                continue
            seen.add(tx_id)
            tx = self.session.get(models.Transaction, tx_id)
            if tx:
                tx.raw = payload
                tx.description = payload.get("description")
                tx.amount = _as_decimal(payload.get("amount"))
                tx.running_balance = _as_decimal(payload.get("running_balance"))
                tx.date = _as_date(payload.get("date"))
                tx.type = payload.get("type")
                tx.cached_at = dt.datetime.utcnow()
            else:
                tx = models.Transaction(
                    id=tx_id,
                    account=account,
                    raw=payload,
                    description=payload.get("description"),
                    amount=_as_decimal(payload.get("amount")),
                    running_balance=_as_decimal(payload.get("running_balance")),
                    date=_as_date(payload.get("date")),
                    type=payload.get("type"),
                )
                self.session.add(tx)
            transactions.append(tx)
            existing_ids.discard(tx_id)

        # Remove transactions no longer returned (within cached window)
        for tx_id in existing_ids:
            tx = self.session.get(models.Transaction, tx_id)
            if tx:
                self.session.delete(tx)
        return transactions

    def list_transactions(self, account_id: str, limit: int = 10) -> List[models.Transaction]:
        stmt = (
            select(models.Transaction)
            .where(models.Transaction.account_id == account_id)
            .order_by(models.Transaction.date.desc(), models.Transaction.cached_at.desc())
            .limit(limit)
        )
        return list(self.session.scalars(stmt))


def _as_decimal(value) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _as_date(value) -> Optional[dt.date]:
    if not value:
        return None
    if isinstance(value, dt.date):
        return value
    try:
        return dt.date.fromisoformat(value)
    except Exception:
        return None
