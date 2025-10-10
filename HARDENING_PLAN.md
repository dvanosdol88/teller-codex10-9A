# Teller Sample Application Hardening Plan

## Overview
This plan sequences the work required to move the Teller sample app toward a production-grade security posture. It
pulls from the current implementation in `python/` and `static/`, and the constraints mentioned in the prior dialog
(two trusted users, preference for simplicity, Render deployment). Each phase builds on the previous one so we can
ship incremental improvements without destabilizing the app.

## Phase 1 – Stabilize runtime and secrets (Days 0‑3)
1. **Replace the development WSGI server.** Swap `wsgiref.simple_server` for Waitress so the app uses a production-ready
   server while staying pure-Python and easy to operate on Render. (`python/teller.py` currently imports
   `wsgiref.simple_server` in `main`.)
2. **Move hard-coded identifiers into configuration.** Load the Teller application ID, environment flag, and API base URL
   from environment variables instead of embedding them in both backend arguments and the frontend bundle
   (`python/teller.py` defaults the application ID; `static/index.js` hardcodes the same string).
3. **Centralize config delivery to the client.** Expose a read-only `/api/config` endpoint backed by environment
   variables so the frontend can request runtime configuration after authentication, eliminating exposed values in the
   static assets.
4. **Inventory secrets and key material.** Document every credential the app needs (Teller cert pair, database DSN,
   Render-provided secrets). Ensure all are stored as Render environment variables or Secret Manager entries instead of
   files under `./secrets`.

## Phase 2 – Strengthen authentication & data handling (Days 3‑7)
1. **Protect stored Teller access tokens.** Encrypt `models.User.access_token` before persisting and store the encryption
   key in a managed secret store. Tokens are currently saved in plaintext (`python/models.py`).
2. **Constrain enrollment payload processing.** Add schema validation for `/api/enrollments` and other endpoints to
   reject malformed or unexpected fields early (`python/resources.py`).
3. **Reduce client-side token exposure.** Stop writing the Teller access token to `localStorage` and avoid echoing it in
   the UI status panel (`static/index.js`). Prefer short-lived, HttpOnly session cookies issued by the backend.
4. **Implement rate limiting and abuse detection.** Apply middleware to throttle sensitive endpoints such as
   `/api/connect/token` and live Teller calls.

## Phase 3 – Platform hardening & observability (Weeks 2‑3)
1. **Introduce TLS termination and security headers.** Use Render's TLS termination plus Falcon middleware to add
   headers like HSTS, CSP, and X-Frame-Options across the app.
2. **Upgrade the database layer.** Migrate from SQLite to managed PostgreSQL, add Alembic migrations, and configure
   SQLAlchemy connection pooling suitable for Waitress.
3. **Add structured logging and tracing.** Emit JSON logs for API requests/responses and integrate with Render's log
   drains or an external aggregator. Add health and readiness probes for deployment automation.

## Phase 4 – Operational safeguards (Weeks 3‑4)
1. **Containerize the service.** Provide a Dockerfile (multi-stage) for reproducible builds, pinned dependencies, and
   vulnerability scanning.
2. **Automate testing & security checks.** Enforce linting, type checks, unit tests, and SAST in CI. Include dependency
   scanning (e.g., `pip-audit`) and container image scans in the pipeline.
3. **Disaster recovery and access review.** Establish backup/restore procedures for the database and rotate Teller
   credentials regularly. Document an incident response playbook covering Teller API failures and access revocation.

## Recommended next step
Begin Phase 1 by swapping the runtime to Waitress (add it to `requirements.txt` and update the entry point to launch
with `waitress.serve`). This immediately removes the most fragile component in the stack and provides a stable base for
subsequent hardening work.

## Deployment milestone
Deploy to Render once every Phase 1 task is complete: the app should already be running on Waitress, sourcing all
runtime configuration from environment variables, and serving those values to the frontend through the new
`/api/config` endpoint. At that point, secrets are centralized, no sensitive identifiers are baked into the static
bundle, and the runtime surface is sufficiently hardened for a managed platform rollout. Subsequent phases can then be
executed against the Render environment.
