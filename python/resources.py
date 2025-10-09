"""Falcon resources for the Teller sample backend."""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Dict

import falcon
from falcon import Request, Response

from . import models
from .repository import Repository
from .teller_api import TellerAPIError, TellerClient
from .utils import ensure_json_serializable

LOGGER = logging.getLogger(__name__)


def parse_bearer_token(req: Request) -> str:
    auth_header = req.get_header("Authorization")
    if not auth_header:
        raise falcon.HTTPUnauthorized("Authentication required", challenges=["Bearer token"])
    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise falcon.HTTPUnauthorized("Invalid authorization header", challenges=["Bearer token"])
    return parts[1]



class BaseResource:
    def __init__(self, session_factory, teller_client: TellerClient):
        self._session_factory = session_factory
        self.teller = teller_client

    @contextmanager
    def session_scope(self):
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def authenticate(self, req: Request, repo: Repository) -> models.User:
        token = parse_bearer_token(req)
        user = repo.get_user_by_token(token)
        if not user:
            raise falcon.HTTPUnauthorized("Unknown access token", challenges=["Reconnect via Teller Connect"])
        return user

    @staticmethod
    def set_no_cache(resp: Response) -> None:
        resp.set_header("Cache-Control", "no-store")


class ConnectTokenResource(BaseResource):
    def on_post(self, req: Request, resp: Response) -> None:
        payload = req.media or {}
        token = self.teller.create_connect_token(**payload)
        resp.media = ensure_json_serializable(token)
        self.set_no_cache(resp)


class EnrollmentResource(BaseResource):
    def on_post(self, req: Request, resp: Response) -> None:
        body = req.media or {}
        enrollment = body.get("enrollment") or body

        access_token = enrollment.get("accessToken") or enrollment.get("access_token")
        user_payload = enrollment.get("user") or {}
        user_id = user_payload.get("id")
        if not access_token or not user_id:
            raise falcon.HTTPBadRequest("invalid-enrollment", "accessToken and user.id are required")

        with self.session_scope() as session:
            repo = Repository(session)
            user = repo.upsert_user(user_id, access_token, user_payload.get("name"))

            accounts_payload = list(self.teller.list_accounts(access_token))
            accounts = [repo.upsert_account(user, account_payload) for account_payload in accounts_payload]

            for account in accounts:
                try:
                    balance = self.teller.get_account_balances(access_token, account.id)
                    repo.update_balance(account, balance)
                except TellerAPIError as exc:
                    LOGGER.warning("Failed to prime balance for %s: %s", account.id, exc)
                try:
                    transactions = list(self.teller.get_account_transactions(access_token, account.id, count=10))
                    repo.replace_transactions(account, transactions)
                except TellerAPIError as exc:
                    LOGGER.warning("Failed to prime transactions for %s: %s", account.id, exc)

            session.flush()

            resp.media = ensure_json_serializable(
                {
                    "user": {
                        "id": user.id,
                        "name": user.name,
                    },
                    "accounts": [serialize_account(account) for account in accounts],
                }
            )
        self.set_no_cache(resp)


class AccountsResource(BaseResource):
    def on_get(self, req: Request, resp: Response) -> None:
        with self.session_scope() as session:
            repo = Repository(session)
            user = self.authenticate(req, repo)
            accounts = repo.list_accounts(user)
            resp.media = ensure_json_serializable(
                {"accounts": [serialize_account(account) for account in accounts]}
            )
        self.set_no_cache(resp)


class CachedBalanceResource(BaseResource):
    def on_get(self, req: Request, resp: Response, account_id: str) -> None:
        with self.session_scope() as session:
            repo = Repository(session)
            user = self.authenticate(req, repo)
            account = repo.get_account(account_id)
            if not account or account.user_id != user.id:
                raise falcon.HTTPNotFound()
            balance = account.balance
            if not balance:
                raise falcon.HTTPNotFound()
            resp.media = ensure_json_serializable(
                {
                    "account_id": account.id,
                    "cached_at": balance.cached_at,
                    "balance": balance.raw,
                }
            )
        self.set_no_cache(resp)


class CachedTransactionsResource(BaseResource):
    def on_get(self, req: Request, resp: Response, account_id: str) -> None:
        limit = 10
        if "limit" in req.params:
            try:
                limit = max(1, min(100, int(req.params["limit"])))
            except ValueError:
                raise falcon.HTTPBadRequest("invalid-limit", "limit must be an integer")

        with self.session_scope() as session:
            repo = Repository(session)
            user = self.authenticate(req, repo)
            account = repo.get_account(account_id)
            if not account or account.user_id != user.id:
                raise falcon.HTTPNotFound()
            transactions = repo.list_transactions(account.id, limit=limit)
            resp.media = ensure_json_serializable(
                {
                    "account_id": account.id,
                    "transactions": [tx.raw for tx in transactions],
                    "cached_at": transactions[0].cached_at if transactions else None,
                }
            )
        self.set_no_cache(resp)


class LiveBalanceResource(BaseResource):
    def on_get(self, req: Request, resp: Response, account_id: str) -> None:
        with self.session_scope() as session:
            repo = Repository(session)
            user = self.authenticate(req, repo)
            account = repo.get_account(account_id)
            if not account or account.user_id != user.id:
                raise falcon.HTTPNotFound()
            try:
                balance = self.teller.get_account_balances(user.access_token, account.id)
            except TellerAPIError as exc:
                raise falcon.HTTPBadGateway(description=str(exc)) from exc
            repo.update_balance(account, balance)
            session.flush()
            resp.media = ensure_json_serializable({"account_id": account.id, "balance": balance})
        self.set_no_cache(resp)


class LiveTransactionsResource(BaseResource):
    def on_get(self, req: Request, resp: Response, account_id: str) -> None:
        count = req.get_param_as_int("count")
        if count is not None:
            if count < 1 or count > 100:
                raise falcon.HTTPBadRequest("invalid-count", "count must be between 1 and 100")
        else:
            count = 10

        with self.session_scope() as session:
            repo = Repository(session)
            user = self.authenticate(req, repo)
            account = repo.get_account(account_id)
            if not account or account.user_id != user.id:
                raise falcon.HTTPNotFound()
            try:
                transactions = list(self.teller.get_account_transactions(user.access_token, account.id, count=count))
            except TellerAPIError as exc:
                raise falcon.HTTPBadGateway(description=str(exc)) from exc
            repo.replace_transactions(account, transactions)
            session.flush()
            resp.media = ensure_json_serializable(
                {
                    "account_id": account.id,
                    "transactions": transactions,
                }
            )
        self.set_no_cache(resp)


def serialize_account(account: models.Account) -> Dict[str, Any]:
    return {
        "id": account.id,
        "name": account.name,
        "institution": account.institution,
        "last_four": account.last_four,
        "type": account.type,
        "subtype": account.subtype,
        "currency": account.currency,
    }
