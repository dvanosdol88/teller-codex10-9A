# Render PostgreSQL Integration Plan (Revised)

## Feedback responses
1. **"Make the plan more actionable and sequential."** — Incorporated by reworking the rollout section into discrete, testable phases with entry/exit criteria so that each change can ship independently and be reverted if needed.
2. **"Explain how we will trace configuration and schema changes."** — Incorporated by expanding the traceability section to cover Git workflows, Alembic revision tracking, Render change history, and operational checklists.
3. **"Clarify how existing cached data will be migrated without downtime."** — Incorporated with a dedicated data-migration section that details export/import mechanics, dual-write validation, and verification queries before cutover.
4. **"Normalize driver/URL handling to match psycopg usage."** — Incorporated because the repo already depends on `psycopg[binary]`, so teaching `build_database_url` to rewrite `postgres://` to `postgresql+psycopg://` plus enabling `pool_pre_ping=True` prevents connection surprises on Render while keeping the dependency set stable.【F:python/requirements.txt†L1-L2】【F:python/db.py†L16-L42】
5. **"Avoid running Alembic on every boot in scaled deploys."** — Incorporated by moving migration execution to an explicit Render job/one-off step in each rollout phase, ensuring horizontal scaling does not produce migration races while preserving SQLite fallback for quick rollback.
6. **"Keep secrets out of render.yaml and lean on Render links."** — Incorporated by documenting the database link in `render.yaml` and reiterating that sensitive credentials remain in Render-managed environment variables or Secret Manager references, so no certs/keys land in Git.【F:render.yaml†L1-L34】
7. **"Tune connection pools for Render starter tiers."** — Incorporated by specifying `pool_size=5`, `max_overflow=5`, and `pool_pre_ping=True` in the engine configuration phase and mapping those values to Render's connection limits to prevent saturation.

## 1. Current persistence design summary
- The SQLAlchemy engine URL prefers Render's `DATABASE_INTERNAL_URL`, falls back to `DATABASE_URL`, and finally to a local SQLite file; SSL parameters are appended automatically when provided. The migration plan will extend `build_database_url` to normalize `postgres://` URLs into `postgresql+psycopg://` so SQLAlchemy loads the psycopg v3 driver Render expects.【F:python/db.py†L16-L42】
- App startup eagerly creates tables with `Base.metadata.create_all(engine)` and configures a single global `sessionmaker` that yields short-lived sessions per request.【F:python/teller.py†L192-L239】【F:python/db.py†L45-L63】
- ORM models already align with PostgreSQL: UUID-like string primary keys, JSON payload columns, numeric currency fields, and cached timestamp columns that match Render defaults.【F:python/models.py†L12-L91】
- All read/write logic is centralized in the `Repository` class, so swapping storage backends only requires satisfying that interface — no caller reaches into SQLAlchemy directly.【F:python/repository.py†L14-L146】

## 2. Risks, prerequisites, and safety rails
| Area | Risk | Mitigation |
|------|------|------------|
| Infrastructure | Misconfigured Render service or env vars lead to boot failure. | Stage changes behind feature flags, validate in preview envs, document env var matrix before production update. |
| Schema drift | `create_all` hides migration errors once Postgres is live. | Introduce Alembic before cutover and run migrations during Render build/deploy hooks. |
| Data integrity | Cached data lost or duplicated during migration. | Export/import via scripts with checksums; run dual-write shadowing before switching traffic. |
| Connection limits | Excess connections on small Render plans. | Keep current per-request session pattern and configure SQLAlchemy pool size to stay < Render limits (e.g., `pool_size=5`, `max_overflow=5`). |
| Rollback complexity | Hard to revert if migration fails mid-deploy. | Maintain SQLite fallback path and keep Alembic reversible revisions ready; document how to flip env vars back instantly. |

## 3. Step-by-step implementation plan
Each phase is a small PR + deployment. Do not proceed until the exit criteria are met.

1. **Phase 0 – Baseline & tooling**
   - Add Alembic configuration, generate an initial `baseline` revision against the existing models, and replace the runtime `create_all` call with an Alembic migration invocation run via a dedicated CLI command or Render job so migrations do not execute implicitly on every web dyno boot.【F:python/teller.py†L192-L239】
   - Update `build_database_url` to normalize `postgres://` → `postgresql+psycopg://` whenever psycopg is in `requirements.txt`, and add `pool_pre_ping=True` alongside Render-friendly limits (`pool_size=5`, `max_overflow=5`, `pool_recycle=300`).【F:python/requirements.txt†L1-L2】【F:python/db.py†L16-L63】
   - Exit criteria: `alembic upgrade head` succeeds locally against SQLite and a local Postgres instance when invoked manually; unit/integration tests pass; documentation updated with the explicit migration command developers must run.

2. **Phase 1 – Local & CI validation on Postgres**
   - Run Postgres locally (Docker) and in CI using the same normalized DSN format Render expects (`postgresql+psycopg://...`).
   - Execute smoke tests: enroll a demo user, refresh balances/transactions, assert persisted rows in Postgres tables via SQL queries.
   - Capture schema diff with `alembic revision --autogenerate` (should be empty) to ensure models and migrations align.
   - Exit criteria: CI job green on both SQLite (fallback) and Postgres job matrix; documented SQL samples for verification.

3. **Phase 2 – Render preview environment**
   - Provision Render Postgres and link it to the preview service in `render.yaml` (or via the dashboard) so `DATABASE_INTERNAL_URL` is injected automatically; keep credentials out of source control by relying on Render-managed secrets or Secret Manager references.【F:render.yaml†L1-L34】
   - Deploy app pointing to Postgres; run `alembic upgrade head` via a one-off job or manual trigger immediately after deploy instead of the runtime start command, preventing concurrent web instances from racing migrations.
   - Execute manual QA: exercise API routes that touch the database, verify rows via `psql` or Render data browser, enable SQL logging temporarily using `--db-echo` or `DB_ECHO=true` to monitor queries.【F:python/teller.py†L109-L139】【F:python/db.py†L37-L42】
   - Exit criteria: No errors in logs for 24h, data persists across service restarts, database metrics within limits.

4. **Phase 3 – Data migration rehearsal**
   - Run migration script (see section 4) that exports SQLite data, imports into Postgres, and compares record counts/hashes.
   - As part of the rehearsal, validate that Render connection pool limits are respected under load tests by checking `pg_stat_activity` and adjusting SQLAlchemy pool parameters if necessary.
   - Perform dual-write experiment: keep SQLite primary, but after each repository mutation, optionally (flag-controlled) mirror into Postgres to validate schema assumptions before cutover.【F:python/repository.py†L14-L146】
   - Exit criteria: Backfilled Postgres matches SQLite row counts and spot-checked balances/transactions for sampled accounts.

5. **Phase 4 – Production cutover**
   - Take final SQLite snapshot (copy file) and Render Postgres backup.
   - Update production service env vars to include Postgres DSN (now normalized in code) and confirm the Render database link is active; deploy commit enabling Postgres as primary.
   - Run health checks, targeted user workflows, and readiness probes; monitor logs/metrics closely for 1–2 hours, watching for connection saturation warnings to confirm pool tuning is sufficient.
   - Exit criteria: No elevated error rates, Postgres metrics stable, QA sign-off.

6. **Phase 5 – Post-cutover hardening**
   - Remove SQLite fallback only after multiple successful deploys and confirmed restore drills.
   - Schedule recurring backups and document rotation cadence; enable alerts for connection saturation or slow queries.
   - Retire dual-write code paths once confidence established.

## 4. Data migration & verification
1. **Export** — Use a management command or standalone Python script that opens the SQLite file with SQLAlchemy, dumps each table to CSV/JSON (respecting foreign-key order). Keep snapshot artifacts in object storage with timestamps.
2. **Import** — Load CSV/JSON into Postgres using `COPY` or SQLAlchemy bulk inserts inside transactions; wrap in Alembic `data` migrations so it is replayable in staging.
3. **Integrity checks**
   - Record counts per table must match between SQLite and Postgres.
   - Hash critical columns (e.g., SHA256 of `id||updated_at`) to detect drift.
   - Sample validation: run repository queries (list accounts, balances, transactions) against both databases and diff the results.
4. **Dual-write validation (optional but recommended)**
   - Feature-flag a path where repository mutations write to both databases for a limited window; compare row versions nightly until confidence is high.
   - Disable flag prior to final cutover.

## 5. Change traceability & rollback mechanics
- **Git discipline** — Use dedicated branches per phase, squash-merge with descriptive commit messages, and tag releases (`vX.Y-postgres-phaseN`) so every deployment maps to a commit SHA.
- **Alembic history** — Each migration revision captures `up`/`down` scripts; keep them reversible and practice `alembic downgrade` against staging before production use.
- **Render change log** — Document environment variable updates and deploys in Render's built-in history; copy details into an ops runbook for quick audit.
- **Configuration diffs** — Store `render.yaml` (or IaC equivalent) in Git so Render service changes are code-reviewed; include connection/pooling settings alongside secrets references.
- **Rollback path** — To revert, (1) run `alembic downgrade` to previous schema if needed, (2) clear `DATABASE_INTERNAL_URL` so app falls back to SQLite immediately thanks to existing logic, and (3) restore latest SQLite snapshot if changes occurred while Postgres was primary.【F:python/db.py†L16-L42】

## 6. Operational readiness checklist
- [ ] Alembic migrations version-controlled and rehearsed.
- [ ] Render Postgres backups enabled and restore drill documented.
- [ ] Monitoring/alerting configured for connection usage, slow queries, and error rates.
- [ ] Runbooks cover deploy steps, rollback, and credential rotation.
- [ ] Team briefed on phased rollout timeline and verification responsibilities.

This revised plan keeps risk low by introducing tooling early, verifying each incremental change, and documenting explicit rollback levers so the team can confidently adopt Render's managed PostgreSQL.
