# Teller Cached Dashboard

This example implements a single Falcon service that serves both the Teller Connect UI and the API required to cache account data. The UI renders a flip-card for every connected account – balances on the front, the 10 most recent cached transactions on the back – and allows the user to refresh live Teller data on demand.

## Getting started

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r python/requirements.txt

# Run database migrations (required before first start)
python python/teller.py migrate

# Or use Alembic directly
alembic upgrade head

export TELLER_APPLICATION_ID="<your-app-id>"
#export TELLER_CERTIFICATE="/path/to/certificate.pem"  # or the PEM contents
#export TELLER_PRIVATE_KEY="/path/to/private_key.pem"  # or the PEM contents
## Certs are stored in the Render dashboard
# Optional overrides
export TELLER_ENVIRONMENT="development"
export TELLER_APP_API_BASE_URL="/api"

python python/teller.py
```

The server listens on `http://localhost:8001` by default and serves both the frontend and `/api/*` endpoints. Runtime configuration values (application ID, environment, and API base URL) are sourced from environment variables and exposed to the frontend via `GET /api/config` after the page loads.

## Environment variables

| Variable | Purpose |
| --- | --- |
| `TELLER_APPLICATION_ID` | Teller application identifier. |
| `TELLER_ENVIRONMENT` | Teller environment passed to both the backend client and Teller Connect (defaults to `development`). |
| `TELLER_APP_API_BASE_URL` | Base URL the frontend uses for API requests (defaults to `/api`). |
| `TELLER_CERTIFICATE` | Path to the TLS certificate (development/production). |
| `TELLER_PRIVATE_KEY` | Path to the TLS private key (development/production). |
| `DATABASE_INTERNAL_URL` | Render Postgres URL (falls back to local SQLite). |
| `DATABASE_SSLMODE` | SSL mode appended to the Postgres URL when provided. |
| `GCP_PROJECT_ID` | Google Cloud project ID for Secret Manager. |
| `TELLER_SECRET_CERTIFICATE_NAME` | The name of the secret in Google Secret Manager containing the Teller certificate. |
| `TELLER_SECRET_PRIVATE_KEY_NAME` | The name of the secret in Google Secret Manager containing the Teller private key. |

## Google Secret Manager Integration

Instead of storing the certificate and private key files locally, the application can be configured to fetch them from Google Cloud Secret Manager.

To enable this, set the following environment variables:

- `GCP_PROJECT_ID`: Your Google Cloud project ID.
- `TELLER_SECRET_CERTIFICATE_NAME`: The name of the secret containing the TLS certificate.
- `TELLER_SECRET_PRIVATE_KEY_NAME`: The name of the secret containing the TLS private key.

The application will then use these secrets when run in `development` or `production` environments.

## Secrets inventory

All credentials must be provisioned via environment variables or Secret Manager entries; the local `./secrets` directory is no longer used for defaults.

| Secret | Environment variable | Storage recommendation |
| --- | --- | --- |
| Teller application ID | `TELLER_APPLICATION_ID` | Render environment variable or Secret Manager |
| Teller certificate (PEM contents or path) | `TELLER_CERTIFICATE` | Secret Manager preferred; Render env var for development |
| Teller private key (PEM contents or path) | `TELLER_PRIVATE_KEY` | Secret Manager preferred; Render env var for development |
| Database connection string | `DATABASE_INTERNAL_URL` | Render managed Postgres / secret |
| Database SSL mode (if required) | `DATABASE_SSLMODE` | Render environment variable |
| Google Cloud project | `GCP_PROJECT_ID` | Render environment variable |
| Secret names for Teller certificate/key | `TELLER_SECRET_CERTIFICATE_NAME`, `TELLER_SECRET_PRIVATE_KEY_NAME` | Render environment variable |

## Frontend behaviour

- Teller Connect launches from the “Connect an account” button. On success the enrollment is posted to `/api/enrollments`, cached in the database, and persisted to `localStorage`.
- Cards fetch cached balances (`/api/db/accounts/{id}/balances`) and cached transactions (`/api/db/accounts/{id}/transactions?limit=10`).
- “Refresh live” calls both `/api/accounts/{id}/balances` and `/api/accounts/{id}/transactions?count=10`, then re-renders the cached data.
- Static assets are cached by the browser, while all API responses set `Cache-Control: no-store`.

## Database schema

Tables are managed via Alembic migrations. Run `python python/teller.py migrate` or `alembic upgrade head` to create or update the schema.

Schema includes:

- `users` – Teller user ID and latest access token.
- `accounts` – metadata about the user's Teller accounts.
- `balances` – most recent cached balance per account.
- `transactions` – cached transactions (pruned to the latest window returned).

The repository layer handles idempotent upserts for each table so subsequent refreshes simply update the cached data.

## Deployment

Before deploying to production, make sure to run database migrations:

```bash
python python/teller.py migrate
```

For production deployments on Render, run this migration as a one-off job or in a pre-deploy hook to ensure the database is properly initialized before the web service starts.

## Development and Testing

### Running Tests

This project uses pytest for testing. Tests validate functionality against both SQLite and PostgreSQL.

#### Install test dependencies
```bash
pip install -r python/requirements.txt
```

#### Run tests with SQLite (default)
```bash
pytest tests/ -v
```

#### Run tests with local PostgreSQL
First, start the PostgreSQL container:
```bash
docker-compose up -d
```

Then run tests with the PostgreSQL database URL:
```bash
export DATABASE_INTERNAL_URL="postgresql+psycopg://teller:teller_dev@localhost:5432/teller_dev"
python python/teller.py migrate
pytest tests/ -v
```

Stop the PostgreSQL container when done:
```bash
docker-compose down
```

### Continuous Integration

GitHub Actions runs tests automatically on every push and pull request against both SQLite and PostgreSQL to ensure compatibility.

### Database Migrations

This project uses Alembic for database migrations. To run migrations:

```bash
python python/teller.py migrate
```

To verify that your models are in sync with migrations:

```bash
alembic revision --autogenerate -m "check_drift"
# Should output "No changes detected" (important-comment)
# Delete the generated file if it was created (important-comment)
```

### SQL Verification

See [docs/sql_verification.md](docs/sql_verification.md) for SQL queries to verify data integrity and row counts in your database.
