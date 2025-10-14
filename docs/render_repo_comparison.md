# Render Deployment Repo Comparison

This document captures the deltas between the `teller-codex10-9A` repository (this repo) and `teller-codex10-9B` to help decide which codebase to run on Render.

## High-level assessment

- **teller-codex10-9A** keeps the `/api/enrollments` response minimal (user metadata plus the enrolled account list) and focuses on structured logging for enrollment priming without altering the API surface. 【F:python/resources.py†L74-L144】
- **teller-codex10-9B** introduces an `ENROLLMENT_ENRICHED_RESPONSE` feature flag that optionally returns cached balances, transactions, and partial failure metadata directly from the enrollment call. 【F:../teller-codex10-9B/python/resources.py†L70-L136】
- Both repositories share the same Render blueprint (`render.yaml`) including inline Teller certificate/private key material that should be migrated into Render-managed secrets before production deployment. 【F:render.yaml†L1-L75】

## Production readiness

- Repo 9A’s simpler response schema and existing structured logging (`log_enrollment_event`) mean fewer moving parts to validate for Render deployment, making it the faster path to a stable release once secrets management is corrected. 【F:python/resources.py†L85-L144】
- Repo 9B’s enrichment path requires additional QA around pagination limits, partial failure handling, and UI coordination, as described in its README, extending the stabilization timeline. 【F:../teller-codex10-9B/README.md†L72-L139】

## Render bring-up effort

- Both repos boot the same Waitress-backed Falcon app with identical start and build commands, so day-one Render setup is equivalent. 【F:python/teller.py†L200-L246】【F:render.yaml†L1-L75】
- Enabling the enrichment flag in 9B introduces extra environment configuration and testing requirements, whereas 9A can ship with the default environment variables already documented. 【F:../teller-codex10-9B/README.md†L101-L124】

## Feature complexity cost

- The enriched enrollment payload surfaces cached balances/transactions and a `partials` array to surface Teller API priming failures. This can improve perceived performance but adds branching logic on both the backend and frontend to handle optional fields. 【F:../teller-codex10-9B/python/resources.py†L79-L135】
- Tests in 9B cover the enriched behavior and assert schema stability when the flag is off, highlighting the extra maintenance surface relative to 9A’s lighter test suite. 【F:../teller-codex10-9B/tests/test_enrollment_enrichment.py†L78-L159】

## Recommended adjustments

- Remove inline secret material from `render.yaml` in both repos and rely on Render environment variables or a secret store before any public deployment. 【F:render.yaml†L15-L75】
- If we adopt repo 9B, ensure the UI is updated (or feature-flagged) to consume the enriched payload without duplicate data fetches; otherwise leave the flag disabled until the end-to-end flow is verified.
- Regardless of repo choice, add documentation for the missing `INTERNAL_HANDOFF.md` referenced in stakeholder notes so future teams share the same deployment expectations.
