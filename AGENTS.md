# Repository Guidelines

## Project Structure & Module Organization
- `python/` — backend service (Falcon):
  - `teller.py` (entrypoint, server + routing), `resources.py` (API resources),
    `teller_api.py` (Teller client), `db.py` (engine/session), `models.py` (ORM), `utils.py`.
- `static/` — frontend assets served at `/` and `/static/*` (`index.html`, `index.js`, `styles.css`).
- `secrets/` — intentionally unused (only `.gitignore`); use environment variables or Secret Manager.
- See `README.md` for environment details.

## Build, Test, and Development Commands
- Create env and install deps:
  - `python3 -m venv .venv && source .venv/bin/activate`
  - `pip install -r python/requirements.txt`
- Set required config (examples):
  - `export TELLER_APPLICATION_ID=your-app-id`
  - Optional: `TELLER_ENVIRONMENT=development`, `TELLER_APP_API_BASE_URL=/api`
  - TLS/Secrets: `TELLER_CERTIFICATE`, `TELLER_PRIVATE_KEY` (PEM path or contents)
  - DB: `DATABASE_INTERNAL_URL` (Render) or `DATABASE_URL` (defaults to `sqlite:///teller.db`)
- Run locally:
  - `python python/teller.py --debug --db-echo` (listens on `http://localhost:8001`)
  - Health check: `curl http://localhost:8001/api/healthz`

## Coding Style & Naming Conventions
- Python: follow PEP 8 and PEP 484. Use 4‑space indentation and type hints.
- Naming: `snake_case` for modules/functions/vars; `PascalCase` for classes.
- Prefer clear docstrings, small functions, and explicit imports. Keep API routes and DB logic in `resources.py` and `db.py`/`models.py` respectively.

## Testing Guidelines
- No test suite is included yet. If adding tests, use `pytest` and Falcon’s testing client.
- Place tests under `tests/` with `test_*.py` naming. Run with `pytest -q`.
- For DB tests, prefer SQLite: `export DATABASE_URL=sqlite:///:memory:` or a temp file.

## Commit & Pull Request Guidelines
- Commits: concise, imperative subject; include rationale. Prefer Conventional Commits (`feat:`, `fix:`, `chore:`, `docs:`).
- PRs: clear description, steps to validate locally, affected env vars, and screenshots of UI changes. For API changes, include example requests/responses.

## Security & Configuration Tips
- Never commit secrets. Prefer Google Secret Manager via `GCP_PROJECT_ID`, `TELLER_SECRET_CERTIFICATE_NAME`, `TELLER_SECRET_PRIVATE_KEY_NAME`.
- In `development`/`production`, TLS certificate and key are required.
- Avoid `--debug` in production. Keep `Cache-Control: no-store` for API responses as implemented.

