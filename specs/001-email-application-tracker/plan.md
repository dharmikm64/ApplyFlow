# Implementation Plan: Email-Driven Application Tracker

**Branch**: `001-email-application-tracker` (no git repo yet) | **Date**: 2026-11-25 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/001-email-application-tracker/spec.md`

## Summary

ApplyFlow turns a user's recruiting emails into a persistent application table. The user signs
in with Google (OIDC), separately grants `gmail.readonly`, picks an inclusive start date, and
starts a scan. A Postgres-backed background job lists **every** message in the exact UTC window
(no narrow keyword query). It screens each message from metadata, fetches only likely-recruiting
messages in full, and runs four separately testable stages: **retrieval → deterministic
extraction → application matching → status/date derivation**. Message IDs and extracted events
are stored so re-scans are idempotent. Uncertain results go to a review area. Users can correct,
dismiss, and restore rows. Disconnecting revokes and deletes tokens. Everything runs locally at
no cost, with only the developer's Gmail allowlisted, and can be deployed online later without
redesign. Full rationale is in [research.md](research.md).

## Technical Context

**Language/Version**: Python 3.12 (backend); TypeScript 5.x on Node 22 LTS (frontend)

**Primary Dependencies**: FastAPI, Uvicorn, SQLAlchemy 2.x + psycopg 3, Alembic, Authlib (OIDC +
OAuth2 client), httpx, cryptography (MultiFernet), tenacity, BeautifulSoup4, pydantic-settings;
React 18, Vite, React Router, TanStack Query

**Storage**: PostgreSQL 16 (Docker Compose locally; a free managed Postgres when deployed)

**Testing**: pytest (unit + integration against real Postgres), Vitest + Testing Library
(frontend components), Playwright `@playwright/test` (E2E with synthetic Gmail fixtures),
Playwright MCP (interactive UI inspection), and a manual real-Gmail checklist
([quickstart.md](quickstart.md))

**Target Platform**: Local macOS/Linux development machine. Later, a single Linux container on a
free host.

**Project Type**: Web application (frontend + backend)

**Performance Goals**: A 3-month mailbox (about 3,000 messages) scans in ≤ 10 min, with progress
updating at least every 10 s (SC-002). A returning user's dashboard loads in ≤ 3 s (SC-007).

**Constraints**: No cost (clarification Q3); read-only Gmail; no third-party processing of email content
(FR-020a); no email bodies stored or logged; refresh tokens encrypted with an env key;
resumable batched scans; single-process local run

**Scale/Scope**: 1 real user locally (≤ 100 allowlisted later); about 3k–10k messages per
scan; about 6 screens (sign-in, connect/consent, dashboard, detail, review, settings/data)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Gate | Pre-research | Post-design |
|---|---|---|---|
| I. Complete Working Workflow | Real Google sign-in and Gmail in the delivered app; mocks only in tests | ✅ | ✅ `GoogleGmailClient` is the default; `FixtureGmailClient` is only registered when `APP_ENV=test` (R14) |
| II. Simplicity & MVP Discipline | One deployable, one datastore, no extra services; no out-of-scope features | ✅ | ✅ Single FastAPI process with embedded worker on Postgres (R6); no Redis/Celery; LLM fallback is a proposal, not built (R9) |
| III. Per-User Privacy & Isolation | Every query user-scoped server-side; 404 for others' resources; no third-party sharing | ✅ | ✅ `user_id` on every table, repository methods require `user_id`, isolation tests on every route (data-model, contracts) |
| IV. Read-Only Gmail & Secret Protection | `gmail.readonly` only; server-side tokens encrypted at rest; no secrets/bodies in logs or git; disconnect revokes | ✅ | ✅ R2, R4, R12; `.env` git-ignored, `.env.example` provided |
| V. Email Content Is Untrusted Data | No instruction-following on email text; sanitized rendering; schema-validated output | ✅ | ✅ Deterministic parsing only; excerpts rendered as escaped text; `prompt-injection-text` fixture (R8, R12) |
| VI. Factual Integrity, Evidence & Idempotency | Never invent values; evidence per field; corrections win; no duplicates | ✅ | ✅ Unknowns stay NULL; `processed_messages` unique key; `overridden_fields`; review dedupe keys (R10, R11) |
| VII. Targeted Testing | Tests for matching, status, date boundaries, isolation; Playwright main journey; synthetic fixtures | ✅ | ✅ R14 and the fixture scenario list |

**Result**: PASS. One test-only mechanism is justified in Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/001-email-application-tracker/
├── plan.md              # This file
├── research.md          # Phase 0: decisions R1–R14
├── data-model.md        # Phase 1: tables, constraints, state transitions
├── quickstart.md        # Phase 1: run + validation checklist
├── contracts/
│   ├── http-api.md      # REST + auth redirect routes
│   └── gmail-fixtures.md# GmailClient protocol + synthetic fixture format
├── checklists/requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks; not created here)
```

### Source Code (repository root)

```text
backend/
├── pyproject.toml
├── alembic.ini
├── migrations/                  # Alembic env + versions/
├── app/
│   ├── main.py                  # app factory, routers, static SPA serving, worker startup
│   ├── config.py                # pydantic-settings; APP_ENV guards
│   ├── db.py                    # engine, session factory
│   ├── logging.py               # JSON logging + redaction filter
│   ├── models/                  # SQLAlchemy models (one module per table group)
│   ├── repositories/            # user-scoped data access (user_id required everywhere)
│   ├── auth/
│   │   ├── oidc.py              # Google sign-in (Authlib)
│   │   ├── gmail_oauth.py       # Gmail consent, scope check, account linking, revoke
│   │   ├── sessions.py          # server-side sessions, CSRF dependency
│   │   └── crypto.py            # MultiFernet token encryption
│   ├── gmail/
│   │   ├── client.py            # GmailClient protocol + error types
│   │   ├── google_client.py     # real REST client (httpx, retries, refresh)
│   │   └── parse.py             # MIME decode, HTML→text (in memory)
│   ├── pipeline/
│   │   ├── window.py            # date boundary → exact UTC window, Gmail query, segments
│   │   ├── retrieval.py         # list/paginate/screen/fetch with bounded concurrency
│   │   ├── screening.py         # metadata relevance scoring
│   │   ├── extraction/
│   │   │   ├── ats/             # greenhouse.py, lever.py, workday.py, ashby.py, icims.py, ...
│   │   │   ├── rules.py         # declarative phrase/pattern table
│   │   │   └── extract.py       # Extractor protocol + pipeline
│   │   ├── matching.py          # match() pure function + normalization
│   │   ├── status.py            # derive() pure function (status, date applied, conflicts)
│   │   └── apply.py             # persists results: events, applications, review items
│   ├── jobs/
│   │   ├── worker.py            # claim/heartbeat/reclaim loop; embedded or external
│   │   └── scan_job.py          # orchestrates one run, resumable by segment/page
│   ├── api/                     # routers: me, gmail, cycle, scans, applications, review, data
│   └── testing/                 # APP_ENV=test only: fixture client, /test routes
└── tests/
    ├── unit/
    ├── integration/
    └── fixtures/{gmail,mailboxes}/

frontend/
├── package.json, vite.config.ts  # dev proxy /api,/auth → :8000
├── src/
│   ├── main.tsx, App.tsx, routes.tsx
│   ├── api/                      # typed fetch client (CSRF header), TanStack Query hooks
│   ├── pages/                    # SignIn, ConnectGmail, Dashboard, Review, Settings
│   ├── components/               # ApplicationsTable, Filters, ScanProgress, StateBanners,
│   │                             # ApplicationDetailDrawer, ReviewItemCard, StartDatePicker
│   └── styles/
├── tests/                        # Vitest component tests
└── e2e/                          # Playwright specs + global setup (APP_ENV=test backend)

docker-compose.yml                # db (Postgres 16) only for local; optional app service
Dockerfile                        # multi-stage: build frontend → serve via FastAPI
.env.example                      # placeholders only
README.md                         # local startup + deployment instructions
docs/deployment.md                # free-tier deployment (allowlisted users)
```

**Structure Decision**: Web application with `backend/` (FastAPI) and `frontend/` (Vite React).
Pipeline stages live in separate modules under `backend/app/pipeline/` so retrieval, extraction,
matching, and status derivation can each be unit-tested in isolation (user requirement;
Constitution VII). In production, FastAPI serves the built frontend from a single origin.

## Milestones

Each milestone ends with something runnable and tested. Real Google and Gmail are wired in by M3,
and the finished app never relies on mock data.

| # | Milestone | Done when |
|---|---|---|
| M0 | **Scaffold**: repo layout, docker-compose Postgres, FastAPI app factory, config + `APP_ENV` guards, logging/redaction, Alembic baseline with all tables, Vite app shell, `.env.example`, `.gitignore`, README stub | `alembic upgrade head` works; `/api/health` OK; frontend renders; redaction unit test passes |
| M1 | **Google sign-in + sessions**: Authlib OIDC, server-side sessions, CSRF, allowlist, `/api/me`, sign-out | Real sign-in with the test account works locally; isolation and CSRF tests pass |
| M2 | **Gmail connect (real)**: consent explanation page, `gmail.readonly` flow, scope check, encrypted refresh token, `getProfile`, disconnect + revoke, denied/revoked states | Real consent → `connected`; untick → `denied`; disconnect deletes the token row |
| M3 | **Scan pipeline (real + fixtures)**: window math, job table + embedded worker, retrieval/screening/fetch with concurrency and retries, extraction rules + ATS parsers, matching, status derivation, idempotent persistence, progress API | All pipeline unit tests and fixture scenarios pass; a real scan of the test account completes; crash-resume and re-scan tests pass |
| M4 | **Dashboard**: table (4 columns), search/filter/sort, last sync time, progress, loading/empty/failed/reconnect states, Sync now | Story 1 and 2 acceptance scenarios pass in integration tests; UI inspected via Playwright MCP |
| M5 | **Detail, corrections, review, dismiss**: detail drawer with evidence and history, edits with overrides, review area + resolutions, Not an application + Dismissed view | Story 3 scenarios pass; manual-correction-then-sync and dismiss-then-sync pass |
| M6 | **Account and data controls**: start-date change preview/confirm, delete imported data, mailbox-mismatch guard | Story 5 scenarios pass |
| M7 | **E2E + hardening + docs**: Playwright main journey, accessibility pass, log/secret audit, README local startup, `docs/deployment.md`, manual real-Gmail checklist | Playwright suite green; quickstart manual checklist completed with the test account |

## Complexity Tracking

| Violation / risk | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| Test-only sign-in route and `FixtureGmailClient` (`APP_ENV=test`) | Constitution VII requires repeatable E2E with synthetic fixtures. Real Google sign-in can't be automated reliably. | A fake OIDC server is more code and still needs a Gmail fake. Using real Gmail in E2E violates VII and isn't repeatable. Mitigation: these are registered only when `APP_ENV=test`; startup refuses test mode unless the database name ends in `_test`; and a unit test asserts that the routes are absent in `development`/`production`. |
| Embedded worker thread inside the API process | Simplest reliable option for local no-cost operation | A separate worker plus Redis adds a service. `BackgroundTasks` isn't durable. The same loop can run as a separate process later (R6). |
