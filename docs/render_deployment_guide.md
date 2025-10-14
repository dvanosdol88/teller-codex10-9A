# Render deployment runbook for repository 9A

This guide describes how to bring **teller-codex10-9A** to a production-ready state on [Render](https://render.com), including pre-deployment preparation, Render configuration, and post-deploy validation.

---

## 1. Pre-deployment preparation (local)

1. **Clone and bootstrap the project**
   ```bash
   git clone https://github.com/dvanosdol88/teller-codex10-9A.git
   cd teller-codex10-9A
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r python/requirements.txt
   ```

2. **Create a `.env.render` template** for secrets you will add in Render. This helps ensure nothing is missed when you provision environment variables:
   ```env
   TELLER_APPLICATION_ID=
   TELLER_ENVIRONMENT=production
   TELLER_APP_API_BASE_URL=/api
   DATABASE_INTERNAL_URL=
   DATABASE_SSLMODE=require
   GCP_PROJECT_ID=
   TELLER_SECRET_CERTIFICATE_NAME=
   TELLER_SECRET_PRIVATE_KEY_NAME=
   ```
   > Keep Teller certificate/private key PEM blobs out of source control. Store them in Google Secret Manager or Render managed secrets instead of `render.yaml`.

3. **Run database migrations locally** so you can catch any drift before deploying:
   ```bash
   python python/teller.py migrate
   ```

4. **Execute the automated test suite** (required for production readiness):
   ```bash
   pytest tests/ -v
   ```
   > If you have Docker installed, optionally repeat with PostgreSQL using `docker-compose up -d` and `DATABASE_INTERNAL_URL="postgresql+psycopg://teller:teller_dev@localhost:5432/teller_dev"` to mirror Render’s database stack.

5. **Verify Teller credentials** you plan to use in production. Confirm:
   - The Teller application ID is active for the target environment (`development` vs `production`).
   - Your TLS certificate and private key PEMs are valid (matching pair, correct chain). Use `openssl x509 -in cert.pem -text -noout` as a quick sanity check.
   - Google Secret Manager (or Render secrets) contains the PEM values under the names you will reference in environment variables.

6. **Remove embedded secrets from configuration files.** Delete the inline certificate/private key in `render.yaml` (if present) or ensure you never commit sensitive values. Render environment variables or Secret Manager references should be used instead.

7. **Decide on Teller response shape.** Repository 9A serves the lean enrollment payload by default. Confirm your frontend expects that shape (no enriched balances/transactions). Document that choice in your release notes so QA knows what to validate.

---

## 2. Provision Render resources

1. **Create (or reuse) a Render Postgres instance.**
   - From the Render dashboard, choose **Databases → New Database**.
   - Select the region closest to your users (e.g., Oregon), give it a descriptive name, and note the `Internal Database URL`.
   - Enable high availability/backups according to your production SLOs.

2. **Create Google Secret Manager entries** (recommended) for the Teller certificate and private key, or plan to add them directly as Render environment variables. Capture the secret names for later.

3. **Generate a Teller production certificate** if you have not already. Teller issues PEM-encoded cert/key pairs per environment; keep them in your secret store and rotate per policy.

4. **Review network access.** If your Teller environment requires static egress IPs, record Render’s IP ranges and register them with Teller before launch.

---

## 3. Configure the Render web service

1. In Render, click **New → Web Service** and connect the `teller-codex10-9A` repository.
2. Set the **Environment** to "Python" and choose the same region as your database.
3. Use the following commands (matching `render.yaml`):
   - **Build Command:** `pip install -r python/requirements.txt`
   - **Start Command:** `python python/teller.py`
4. Set the **Health Check Path** to `/api/healthz`.
5. Configure **Environment Variables** (values from your `.env.render` template):
   - `PYTHON_VERSION=3.12.4` (to match local testing).
   - `TELLER_APPLICATION_ID`, `TELLER_ENVIRONMENT`, `TELLER_APP_API_BASE_URL`.
   - `DATABASE_INTERNAL_URL` pointing to the Render Postgres **Internal Database URL**.
   - `DATABASE_SSLMODE=require` (or your chosen mode).
   - `GCP_PROJECT_ID`, `TELLER_SECRET_CERTIFICATE_NAME`, and `TELLER_SECRET_PRIVATE_KEY_NAME` if you use Google Secret Manager.
   - If you are injecting PEM contents directly, add `TELLER_CERTIFICATE` and `TELLER_PRIVATE_KEY` as **Secret Files** or environment variables (avoid pasting PEMs directly in YAML).
6. (Optional) Disable **Auto Deploy** until you validate the first release, then re-enable.
7. Save the service. Render will queue the initial build but will fail until migrations run and secrets are populated—complete the next step before promoting to production.

---

## 4. Run database migrations on Render

1. Add a **Render Job** (or pre-deploy hook) to execute migrations against the production database:
   - **Command:** `python python/teller.py migrate`
   - **Environment:** same environment variables as the web service.
   - Run the job manually once before the first deployment, and add it to your deployment checklist for future schema changes.
2. Verify the job completes successfully in the Render dashboard. If it fails, inspect logs, fix the issue locally, rerun tests, and retry.

---

## 5. Kick off the first deployment

1. Ensure all environment variables and secret values are present in Render.
2. Trigger a deploy via the Render dashboard (or push to the connected branch if auto-deploy is enabled).
3. Watch the build logs until Render reports the service as **Live**.
4. Confirm the health check succeeds: the Render dashboard will display a green status once `/api/healthz` responds with HTTP 200.

---

## 6. Post-deploy validation & monitoring

Once the service is live, follow this test plan:

1. **Smoke tests**
   - From your terminal:
     ```bash
     curl -I https://<your-service>.onrender.com/api/healthz
     curl https://<your-service>.onrender.com/api/config
     ```
   - Expect HTTP 200, JSON payload with application ID and environment.

2. **UI walkthrough (Teller sandbox)**
   - Visit `https://<your-service>.onrender.com` in a browser.
   - Click **Connect an account** and authenticate using Teller’s sandbox credentials.
   - After onboarding, confirm the dashboard shows flip-cards for accounts with cached balances and transaction counts.

3. **API spot checks**
   - Use an API client (curl, Postman) with Teller sandbox tokens from your enrollment to hit:
     ```bash
     curl https://<your-service>.onrender.com/api/enrollments
     curl https://<your-service>.onrender.com/api/db/accounts/<account_id>/balances
     curl 'https://<your-service>.onrender.com/api/db/accounts/<account_id>/transactions?limit=10'
     ```
   - Verify responses match the lean schema (no enriched data). Confirm `Cache-Control: no-store` headers are present.

4. **Database verification**
   - Connect to the Render Postgres instance using `psql` (or Render’s data browser) and run the queries in [`docs/sql_verification.md`](sql_verification.md) to confirm row counts and recent timestamps for users/accounts/balances/transactions.

5. **Log monitoring**
   - Inspect Render logs for `ERROR`/`WARNING` entries. Ensure enrollment and refresh flows log expected events without stack traces.
   - Configure alerting (PagerDuty, Slack) on HTTP error rates or latency using Render metrics.

6. **Regression safety net**
   - Before each subsequent deploy, rerun the local preparation steps (tests, migrations) and execute the Render migration job. Document releases in your change log for traceability.

Following this runbook ensures repository 9A is hardened for a stable Render deployment while keeping the enrollment endpoint simple and production-ready.
