# Teller Cached Dashboard

This example implements a single Falcon service that serves both the Teller Connect UI and the API required to cache account data. The UI renders a flip-card for every connected account – balances on the front, the 10 most recent cached transactions on the back – and allows the user to refresh live Teller data on demand.

## Getting started

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r python/requirements.txt
python python/teller.py --environment sandbox --application-id <your-app-id>
```

The server listens on `http://localhost:8001` by default and serves both the frontend and `/api/*` endpoints. When you are ready to exercise the development environment with Teller's mutual TLS, place the provided secrets inside a local `secrets/` directory:

```bash
mkdir -p secrets
cp /path/to/certificate.pem secrets/certificate.pem
cp /path/to/private_key.pem secrets/private_key.pem
python python/teller.py --environment development --application-id app_pj4c5t83p8q0ibrr8k000
```

`python/teller.py` automatically picks up those files (or paths supplied through `TELLER_CERTIFICATE`/`TELLER_PRIVATE_KEY`) so you can verify the Teller development environment locally. When deploying to Render use the `--environment development` flag with the same certificate and private key.

## Environment variables

| Variable | Purpose |
| --- | --- |
| `TELLER_APPLICATION_ID` | Teller application identifier. |
| `TELLER_ENVIRONMENT` | `sandbox`, `development`, or `production`. |
| `TELLER_CERTIFICATE` | Path to the TLS certificate (development/production). |
| `TELLER_PRIVATE_KEY` | Path to the TLS private key (development/production). |
| `DATABASE_INTERNAL_URL` | Render Postgres URL (falls back to local SQLite). |
| `DATABASE_SSLMODE` | SSL mode appended to the Postgres URL when provided. |

## Frontend behaviour

- Teller Connect launches from the “Connect an account” button. On success the enrollment is posted to `/api/enrollments`, cached in the database, and persisted to `localStorage`.
- Cards fetch cached balances (`/api/db/accounts/{id}/balances`) and cached transactions (`/api/db/accounts/{id}/transactions?limit=10`).
- “Refresh live” calls both `/api/accounts/{id}/balances` and `/api/accounts/{id}/transactions?count=10`, then re-renders the cached data.
- Static assets are cached by the browser, while all API responses set `Cache-Control: no-store`.

## Database schema

Tables are created automatically on boot and include:

- `users` – Teller user ID and latest access token.
- `accounts` – metadata about the user’s Teller accounts.
- `balances` – most recent cached balance per account.
- `transactions` – cached transactions (pruned to the latest window returned).

The repository layer handles idempotent upserts for each table so subsequent refreshes simply update the cached data.
