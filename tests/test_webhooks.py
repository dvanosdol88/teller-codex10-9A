import os
import types
import json
import hmac
import hashlib
import time

from falcon import testing

from python.teller import create_app


def _make_app_with_secrets(secrets: str):
    args = types.SimpleNamespace(
        debug=False,
        db_echo=False,
        environment="sandbox",
        application_id="app_test",
        certificate=None,
        private_key=None,
        app_api_base_url="/api",
        webhook_secrets=secrets,
        webhook_tolerance_seconds=180,
    )
    return create_app(args)


def _signed_headers(secret: str, body: dict):
    raw = json.dumps(body, separators=(",", ":"))
    ts = str(int(time.time()))
    msg = f"{ts}.{raw}".encode()
    sig = hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()
    return {
        "Content-Type": "application/json",
        "Teller-Signature": f"t={ts},v1={sig}",
    }, raw


def test_webhook_test_event_success():
    app = _make_app_with_secrets("secret1")
    client = testing.TestClient(app)

    body = {"id": "wh_test", "payload": {}, "timestamp": "2025-01-01T00:00:00Z", "type": "webhook.test"}
    headers, raw = _signed_headers("secret1", body)

    resp = client.simulate_post("/api/webhooks/teller", headers=headers, body=raw)
    assert resp.status_code == 200
    data = resp.json
    assert data.get("ok") is True


def test_webhook_invalid_signature():
    app = _make_app_with_secrets("secret1")
    client = testing.TestClient(app)

    body = {"id": "wh_test", "payload": {}, "timestamp": "2025-01-01T00:00:00Z", "type": "webhook.test"}
    # Sign with a different secret
    headers, raw = _signed_headers("wrong", body)

    resp = client.simulate_post("/api/webhooks/teller", headers=headers, body=raw)
    assert resp.status_code == 401

