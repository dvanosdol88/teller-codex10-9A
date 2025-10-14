# Teller Webhooks

This app exposes a verified webhook endpoint to receive Teller events and protect against spoofing and replay attacks.

Endpoint
- URL: `/api/webhooks/teller`
- Method: `POST`
- Auth: HMAC signature via `Teller-Signature` header (required)

Configure Secrets
- Set `TELLER_WEBHOOK_SECRETS` to a comma-separated list of active signing secrets from the Teller Dashboard → Application Settings.
- Optional: `TELLER_WEBHOOK_TOLERANCE_SECONDS` (default `180`) limits how old a signed timestamp can be.

How Signature Verification Works
- Teller sends `Teller-Signature: t=<unix_ts>,v1=<sig>[,v1=<sig2>...]`.
- The server computes `HMAC_SHA256(secret, f"{t}.{raw_body}")` and compares against any `v1` in the header using constant-time comparison.
- The request is rejected if:
  - The header is missing or malformed.
  - No configured secret matches the computed HMAC.
  - The timestamp is older than the tolerance window.

Supported Events (logged; extend as needed)
- `webhook.test`: Acknowledge test pings.
- `enrollment.disconnected`: Logs reason; hook here to notify users to reconnect.
- `transactions.processed`: Logs count; hook here to refresh cached transactions.
- `account.number_verification.processed`: Logs status; hook here to update verification state.

Local Testing
```bash
export TELLER_WEBHOOK_SECRETS="shhh_secret"
python python/teller.py

# Create a signed payload
BODY='{"id":"wh_test","payload":{},"timestamp":"2023-07-10T03:49:29Z","type":"webhook.test"}'
TS=$(date +%s)
SIG=$(python - <<'PY'
import hmac,hashlib,os
secret=os.environ.get('TELLER_WEBHOOK_SECRETS','').split(',')[0].strip().encode()
ts=os.environ['TS']
body=os.environ['BODY']
msg=f"{ts}.{body}".encode()
print(hmac.new(secret,msg,hashlib.sha256).hexdigest())
PY
)

curl -i \
  -H "Content-Type: application/json" \
  -H "Teller-Signature: t=${TS},v1=${SIG}" \
  --data "$BODY" \
  http://localhost:8001/api/webhooks/teller
```

Production
- Point the Teller Dashboard webhook URL to your deployed service: `https://<your-domain>/api/webhooks/teller`.
- Rotate secrets by adding the new secret to `TELLER_WEBHOOK_SECRETS` alongside the old one until the old expires.

Reference: https://teller.io/docs/api/webhooks
