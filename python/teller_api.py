"""Thin wrapper around the Teller HTTP API."""
from __future__ import annotations

import base64
import logging
import os
import tempfile
import atexit
from typing import Any, Dict, Iterable, Optional

import requests

LOGGER = logging.getLogger(__name__)

BASE_URL = "https://api.teller.io"


class TellerAPIError(RuntimeError):
    """Raised when the Teller API returns an error."""

    def __init__(self, status_code: int, payload: Any):
        super().__init__(f"Teller API error ({status_code}): {payload}")
        self.status_code = status_code
        self.payload = payload


class TellerClient:
    """Client for interacting with Teller over mutual TLS."""

    def __init__(
        self,
        environment: str,
        application_id: str,
        certificate: Optional[str] = None, # This will now be content or path
        private_key: Optional[str] = None, # This will now be content or path
    ) -> None:
        self.environment = environment
        self.application_id = application_id
        self.cert_tuple = None

        if certificate and private_key:
            # Check if the provided 'certificate' and 'private_key' are file paths or content
            # For simplicity, assume if they are not existing files, they are content.
            # A more robust check might involve trying to read them as files first.
            if os.path.exists(certificate) and os.path.exists(private_key):
                self.cert_tuple = (certificate, private_key)
            else:
                # Assume they are content and write to temporary files
                cert_file = tempfile.NamedTemporaryFile(delete=False)
                cert_file.write(certificate.encode())
                cert_file.close()

                key_file = tempfile.NamedTemporaryFile(delete=False)
                key_file.write(private_key.encode())
                key_file.close()

                self.cert_tuple = (cert_file.name, key_file.name)

                # Register cleanup for temporary files
                atexit.register(os.remove, cert_file.name)
                atexit.register(os.remove, key_file.name)

    # ---------------- Connect ---------------- #
    def create_connect_token(self, **kwargs) -> Dict[str, Any]:
        """Request a Teller Connect token.

        The request is authenticated with the application ID. When the backend
        runs outside of sandbox the certificate pair must be provided.
        """

        payload = {"application_id": self.application_id}
        payload.update(kwargs)
        response = requests.post(
            f"{BASE_URL}/connect/token",
            json=payload,
            headers={"Content-Type": "application/json"},
            cert=self.cert_tuple,
            timeout=15,
        )
        return _handle_response(response)

    # ---------------- Accounts ---------------- #
    def list_accounts(self, access_token: str) -> Iterable[Dict[str, Any]]:
        return self._get(access_token, "/accounts")

    def get_account_balances(self, access_token: str, account_id: str) -> Dict[str, Any]:
        return self._get(access_token, f"/accounts/{account_id}/balances")

    def get_account_transactions(
        self,
        access_token: str,
        account_id: str,
        count: Optional[int] = None,
    ) -> Iterable[Dict[str, Any]]:
        path = f"/accounts/{account_id}/transactions"
        params = {"count": count} if count is not None else None
        return self._get(access_token, path, params=params)

    # ---------------- Internal ---------------- #
    def _get(
        self,
        access_token: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Any:
        url = f"{BASE_URL}{path}"
        headers = {
            "Authorization": _bearer_to_basic(access_token),
            "Accept": "application/json",
        }
        LOGGER.debug("GET %s params=%s", url, params)
        resp = requests.get(url, headers=headers, params=params, cert=self.cert_tuple, timeout=15)
        return _handle_response(resp)


def _bearer_to_basic(token: str) -> str:
    token = token.strip()
    if token.lower().startswith("basic "):
        return token
    if token.lower().startswith("bearer "):
        token = token.split(" ", 1)[1]
    encoded = base64.b64encode(f"{token}:".encode()).decode()
    return f"Basic {encoded}"


def _handle_response(response: requests.Response):
    try:
        payload = response.json()
    except ValueError:
        payload = response.text

    if not response.ok:
        raise TellerAPIError(response.status_code, payload)
    return payload
