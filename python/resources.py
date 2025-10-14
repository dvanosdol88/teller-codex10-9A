"""Falcon resources for the Teller sample backend."""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Dict, Optional

import falcon
from falcon import Request, Response

from . import models
from .repository import Repository
from .teller_api import TellerAPIError, TellerClient
from .utils import ensure_json_serializable
import hmac
import hashlib
import json
import time
from typing import List, Tuple

LOGGER = logging.getLogger(__name__)


def log_enrollment_event(stage: str, **payload: Any) -> None:
    """Emit a structured enrollment log line."""

    record = {"stage": stage, **payload}
    LOGGER.info("enrollment %s", ensure_json_serializable(record))


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

        log_enrollment_event("start", user_id=user_id)

        accounts_response: Optional[Dict[str, Any]] = None

        with self.session_scope() as session:
            repo = Repository(session)
            user = repo.upsert_user(user_id, access_token, user_payload.get("name"))

            accounts_payload = list(self.teller.list_accounts(access_token))
            accounts = [repo.upsert_account(user, account_payload) for account_payload in accounts_payload]

            log_enrollment_event(
                "accounts_fetched",
                user_id=user.id,
                account_ids=[account.id for account in accounts],
            )

            for account in accounts:
                priming_result: Dict[str, Any] = {
                    "user_id": user.id,
                    "account_id": account.id,
                    "balance_primed": False,
                    "transactions_primed": False,
                }
                try:
                    balance = self.teller.get_account_balances(access_token, account.id)
                    repo.update_balance(account, balance)
                    priming_result["balance_primed"] = True
                except TellerAPIError as exc:
                    priming_result["balance_error"] = str(exc)
                    LOGGER.warning("Failed to prime balance for %s: %s", account.id, exc)
                try:
                    transactions = list(self.teller.get_account_transactions(access_token, account.id, count=10))
                    repo.replace_transactions(account, transactions)
                    priming_result["transactions_primed"] = True
                    priming_result["transaction_count"] = len(transactions)
                except TellerAPIError as exc:
                    priming_result["transactions_error"] = str(exc)
                    LOGGER.warning("Failed to prime transactions for %s: %s", account.id, exc)

                log_enrollment_event("priming_result", **priming_result)

            session.flush()

            accounts_response = {
                "user": {"id": user.id, "name": user.name},
                "accounts": [serialize_account(account) for account in accounts],
            }

        if accounts_response is None:
            log_enrollment_event("finish", user_id=user_id, account_count=0)
            return

        log_enrollment_event(
            "finish",
            user_id=user_id,
            account_count=len(accounts_response["accounts"]),
        )
        resp.media = ensure_json_serializable(accounts_response)
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
            LOGGER.info(
                "db.accounts.response %s",
                {"user_id": user.id, "account_ids": [account.id for account in accounts]},
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
            LOGGER.info(
                "db.accounts.balance.response %s",
                {"user_id": user.id, "account_id": account.id, "has_balance": bool(balance.raw)},
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
            LOGGER.info(
                "db.accounts.transactions.response %s",
                {
                    "user_id": user.id,
                    "account_id": account.id,
                    "transaction_count": len(transactions),
                    "limit": limit,
                },
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


class WebhookResource:
    """Teller webhook receiver with signature verification.

    Expects the `Teller-Signature` header and validates HMAC-SHA256 signatures
    using one or more configured signing secrets. Supports secret rotation by
    allowing multiple secrets.
    """

    def __init__(self, signing_secrets: List[str], tolerance_seconds: int = 180) -> None:
        self.secrets = [s for s in (signing_secrets or []) if s]
        self.tolerance_seconds = tolerance_seconds

    @staticmethod
    def _parse_signature_header(header: str) -> Tuple[int, List[str]]:
        """Parse `Teller-Signature` header into (timestamp, [v1 signatures])."""
        if not header:
            raise falcon.HTTPUnauthorized("missing-signature", "Teller-Signature header required")

        timestamp: Optional[int] = None
        sigs: List[str] = []
        for part in header.split(","):
            part = part.strip()
            if not part or "=" not in part:
                continue
            k, v = part.split("=", 1)
            if k == "t":
                try:
                    timestamp = int(v)
                except ValueError:
                    raise falcon.HTTPBadRequest("invalid-signature", "invalid timestamp in signature header")
            elif k == "v1":
                if v:
                    sigs.append(v)
        if timestamp is None or not sigs:
            raise falcon.HTTPUnauthorized("invalid-signature", "missing timestamp or signature")
        return timestamp, sigs

    def _verify(self, header: str, raw_body: bytes) -> None:
        if not self.secrets:
            raise falcon.HTTPInternalServerError(
                title="webhook-not-configured",
                description="No signing secrets configured",
            )

        timestamp, signatures = self._parse_signature_header(header)

        # Reject old timestamps to mitigate replay attacks
        now = int(time.time())
        if abs(now - timestamp) > self.tolerance_seconds:
            raise falcon.HTTPUnauthorized("stale-signature", "signature timestamp too old")

        # Create the signed message: "{timestamp}.{raw_json_body}"
        try:
            body_text = raw_body.decode("utf-8")
        except Exception:
            raise falcon.HTTPBadRequest("invalid-body", "payload must be utf-8 JSON")
        message = f"{timestamp}.{body_text}".encode("utf-8")

        # Validate against any configured secret (supports rotation)
        for secret in self.secrets:
            digest = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
            for provided in signatures:
                if hmac.compare_digest(digest, provided):
                    return

        raise falcon.HTTPUnauthorized("signature-mismatch", "no matching signature")

    def on_post(self, req: Request, resp: Response) -> None:
        # Read raw body once; use for verification and JSON parsing
        raw = req.bounded_stream.read() or b""

        sig_header = req.get_header("Teller-Signature")
        self._verify(sig_header, raw)

        try:
            event = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            raise falcon.HTTPBadRequest("invalid-json", "unable to parse webhook payload")

        event_id = event.get("id")
        event_type = event.get("type")
        payload = event.get("payload") or {}

        # Minimal processing + logging. Business logic can be extended here.
        LOGGER.info(
            "webhook.received %s",
            ensure_json_serializable({"id": event_id, "type": event_type, "payload_keys": list(payload.keys())}),
        )

        # Handle known types with no-op side effects for now.
        if event_type == "webhook.test":
            resp.media = {"ok": True, "echo": event_id}
        elif event_type == "enrollment.disconnected":
            # payload: { enrollment_id, reason }
            LOGGER.warning("enrollment.disconnected %s", ensure_json_serializable(payload))
            resp.media = {"ok": True}
        elif event_type == "transactions.processed":
            # payload: { transactions: [...] }
            tx_count = len(payload.get("transactions", []))
            LOGGER.info("transactions.processed count=%d", tx_count)
            resp.media = {"ok": True, "processed": tx_count}
        elif event_type == "account.number_verification.processed":
            # payload: { account_id, status }
            LOGGER.info("account.number_verification.processed %s", ensure_json_serializable(payload))
            resp.media = {"ok": True}
        else:
            LOGGER.info("webhook.unknown_type %s", event_type)
            resp.media = {"ok": True, "ignored": True}

        resp.set_header("Cache-Control", "no-store")
