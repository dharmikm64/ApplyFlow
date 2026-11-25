---

description: "Task list for ApplyFlow: Email-Driven Application Tracker"
---

# Tasks: Email-Driven Application Tracker

**Input**: Design documents from `specs/001-email-application-tracker/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/http-api.md,
contracts/gmail-fixtures.md, quickstart.md

**Tests**: Required by Constitution Principle VII for matching, status updates, date boundaries,
user isolation, and the Playwright main journey. All automated tests use synthetic fixtures
(`backend/tests/fixtures/`) and never use real Gmail. Write each story's test tasks first and
confirm they fail before implementing.

**Organization**: Tasks are grouped by user story (spec.md US1–US5) so each story can be
implemented and tested independently.

**References**: "R#" means a decision in research.md. "FR-###" means a spec requirement. Table
and field names follow data-model.md, and endpoint shapes follow contracts/http-api.md.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: User story label (US1–US5); omitted for Setup, Foundational, and Polish

## Path Conventions

- Backend: `backend/app/`, `backend/tests/`, `backend/migrations/`
- Frontend: `frontend/src/`, `frontend/tests/`, `frontend/e2e/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and tooling

- [ ] T001 Create the directory layout from plan.md "Source Code" (backend/app/{models,repositories,auth,gmail,pipeline/extraction/ats,jobs,api,testing}, backend/tests/{unit,integration,fixtures/gmail,fixtures/mailboxes}, backend/migrations, frontend/src/{api,pages,components,styles}, frontend/tests, frontend/e2e, docs/) with `__init__.py` files in each backend package
- [ ] T002 Create backend/pyproject.toml (Python 3.12; deps: fastapi, uvicorn[standard], sqlalchemy>=2, psycopg[binary]>=3, alembic, authlib, httpx, itsdangerous, cryptography, tenacity, beautifulsoup4, pydantic-settings, python-dateutil, pyyaml; dev extras: pytest, pytest-cov, ruff, mypy) and configure ruff + pytest sections
- [ ] T003 [P] Scaffold the Vite React TypeScript app in frontend/ (package.json, tsconfig.json, index.html, src/main.tsx) and add react-router-dom, @tanstack/react-query, vitest, @testing-library/react, @testing-library/jest-dom, jsdom, @playwright/test, eslint, prettier
- [ ] T004 [P] Configure frontend/vite.config.ts with a dev server on port 5173 that proxies `/api`, `/auth`, and `/test` to http://localhost:8000 (keeps cookies same-origin, R13) and Vitest with a jsdom environment
- [ ] T005 [P] Create docker-compose.yml with a `db` service (postgres:16, port 5432, volume) and an init script docker/initdb/01-create-test-db.sql that creates the `applyflow_test` database alongside `applyflow`
- [ ] T006 [P] Create .env.example listing every setting with placeholders only: APP_ENV=development, DATABASE_URL, TEST_DATABASE_URL, APP_BASE_URL=http://localhost:5173, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, SESSION_SECRET, TOKEN_ENCRYPTION_KEYS, ALLOWED_GOOGLE_EMAILS, WORKER_MODE=embedded, GMAIL_CONCURRENCY=8, LOG_LEVEL=INFO (comment each one; no real values)
- [ ] T007 [P] Create README.md stub with sections "Local setup", "Running tests", and "Deployment" (filled in T106/T107), linking to specs/001-email-application-tracker/quickstart.md

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Config, database, security primitives, sign-in, Gmail client seam, and test harness
that every story needs

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

### Core backend

- [ ] T008 Implement settings in backend/app/config.py using pydantic-settings: all .env.example keys, `APP_ENV` in {development, test, production}, `TOKEN_ENCRYPTION_KEYS` parsed as a list, `ALLOWED_GOOGLE_EMAILS` parsed as a lowercase set, and `secure_cookies = APP_ENV == "production"`. When APP_ENV=test, refuse to start unless the database name ends in `_test` (plan Complexity Tracking)
- [ ] T009 Implement backend/app/db.py: a SQLAlchemy 2 engine from DATABASE_URL (psycopg 3), `SessionLocal`, a `get_db` FastAPI dependency (commit/rollback per request), and a `Base` declarative class with a UUID primary-key mixin and created_at/updated_at mixins
- [ ] T010 [P] Implement JSON logging with a redaction filter in backend/app/logging.py: drop keys body/token/access_token/refresh_token/authorization/code/id_token/excerpt, mask `Bearer …` and `ya29.…` patterns in messages, and silence httpx/httpcore/authlib debug loggers (R12)
- [ ] T011 [P] Implement token encryption in backend/app/auth/crypto.py: `encrypt(str)->bytes` and `decrypt(bytes)->str` using cryptography MultiFernet built from settings.TOKEN_ENCRYPTION_KEYS, newest key first (R4)

### Data model and migrations

- [ ] T012 [P] Create the User, Session, and GmailConnection models in backend/app/models/account.py per data-model.md (google_sub unique; sessions.id_hash bytea PK; gmail_connections status enum, CHECK that status='connected' ⇔ refresh_token_ciphertext IS NOT NULL)
- [ ] T013 [P] Create the RecruitingCycle and ScanRun models in backend/app/models/scan.py per data-model.md, including the partial unique index `(user_id) WHERE status IN ('queued','running')` and the index `(status, heartbeat_at)`
- [ ] T014 [P] Create the ProcessedMessage, Application, ApplicationEvent, and ReviewItem models in backend/app/models/tracker.py per data-model.md, with unique (user_id, gmail_message_id), unique (application_id, message_id) WHERE message_id IS NOT NULL, unique (user_id, dedupe_key), and all user_id-leading indexes
- [ ] T015 Set up Alembic (backend/alembic.ini, backend/migrations/env.py reading settings.DATABASE_URL and importing all models) and generate the initial migration backend/migrations/versions/0001_initial.py, enabling the `pgcrypto` extension for gen_random_uuid(). Verify `alembic upgrade head` and `alembic downgrade base` against the docker db

### Sessions, repositories, and Gmail client seam

- [ ] T016 Implement server-side sessions in backend/app/auth/sessions.py: `create_session(db, user_id)` (32-byte random ID; store sha256; csrf_token; 14-day sliding expiry), `get_current_user` dependency reading the `af_session` cookie (HttpOnly, SameSite=Lax, Secure when settings.secure_cookies), `require_csrf` dependency checking the `X-CSRF-Token` header on POST/PATCH/PUT/DELETE, and `destroy_session` (R3)
- [ ] T017 Create user-scoped repositories in backend/app/repositories/users.py (`get_or_create_by_sub`) and backend/app/repositories/base.py (a helper that requires `user_id` on every query; no unscoped finders) per data-model.md "Validation rules"
- [ ] T018 [P] Define the GmailClient protocol, dataclasses (Profile, ListPage, MessageMeta, MessageFull), and errors (GmailAuthError, GmailRateLimited, GmailUnavailable) in backend/app/gmail/client.py per contracts/gmail-fixtures.md
- [ ] T019 [P] Implement MIME parsing in backend/app/gmail/parse.py: walk the payload parts, base64url-decode text/plain and text/html, convert HTML to text with BeautifulSoup (html.parser, strip script/style), collapse whitespace, and return header lookups. This runs in memory only and never persists anything

### Test-only harness (APP_ENV=test)

- [ ] T020 Implement FixtureGmailClient in backend/app/testing/fixture_gmail.py: load backend/tests/fixtures/gmail/*.json and mailboxes/*.yaml, apply the same epoch `after:`/`before:` filtering on internalDate, never list SPAM/TRASH-labeled messages, support a configurable page size, `append(messages)`, and a `revoke()` switch that raises GmailAuthError (contracts/gmail-fixtures.md)
- [ ] T021 Implement test-only routes in backend/app/testing/routes.py (`POST /test/login`, `/test/gmail/connect`, `/test/gmail/append`, `/test/gmail/revoke`) per contracts/http-api.md, and a `get_gmail_client(user)` provider in backend/app/gmail/__init__.py that returns FixtureGmailClient only when APP_ENV=test and GoogleGmailClient otherwise (import GoogleGmailClient lazily; it is implemented in T042)

### Sign-in and app wiring

- [ ] T022 Implement Google OIDC sign-in in backend/app/auth/oidc.py with Authlib's Starlette client: register `google` (server metadata https://accounts.google.com/.well-known/openid-configuration, scope "openid email profile", PKCE S256); routes `GET /auth/login`, `GET /auth/callback` (validate state and nonce, read sub/email/name, reject emails not in ALLOWED_GOOGLE_EMAILS → redirect `/?error=not_allowed`, upsert the user by sub, rotate the session), and `POST /auth/logout` (CSRF-protected) per contracts/http-api.md
- [ ] T023 Implement backend/app/main.py app factory: configure logging, add Starlette SessionMiddleware (cookie `af_oauth`, max_age 600, used only for OAuth state/nonce/PKCE), mount auth and `/api` routers, `GET /api/health`, a uniform error handler that returns `{"error","message"}` and never leaks exceptions, register `app/testing` routes only when APP_ENV=test, and serve `frontend/dist` with an SPA fallback when the directory exists (R13)
- [ ] T024 Implement `GET /api/me` in backend/app/api/me.py, returning the user (email, displayName), csrfToken, gmail status, and cycle (startDate, timezone, lastSuccessfulSyncAt) per contracts/http-api.md. There is no user-level time zone; the cycle's time zone is the only one

### Test setup and foundation tests

- [ ] T025 Create backend/tests/conftest.py: point settings at TEST_DATABASE_URL, run `alembic upgrade head` once per session, wrap each test in a transaction rollback, and provide fixtures `client` (FastAPI TestClient with APP_ENV=test), `make_user(sub,email)`, and `login(client,user)` (via /test/login, returning the csrf token)
- [ ] T026 [P] Unit test in backend/tests/unit/test_logging_redaction.py: records containing tokens, `Bearer`/`ya29.` strings, body, and excerpt keys are redacted
- [ ] T027 [P] Unit test in backend/tests/unit/test_test_mode_guard.py: with APP_ENV=development and production, `/test/*` routes are absent (404) and get_gmail_client never returns FixtureGmailClient; APP_ENV=test with a non-`_test` database refuses to start
- [ ] T028 [P] Integration test in backend/tests/integration/test_sessions_csrf.py: /api/me returns 401 without a session; POST without X-CSRF-Token returns 403; logout invalidates the session; an allowlist rejection redirects to `/?error=not_allowed` (OIDC callback with a stubbed Authlib token)

### Frontend foundation

- [ ] T029 [P] Implement a typed API client in frontend/src/api/client.ts (fetch with `credentials: "same-origin"`, attaches X-CSRF-Token from the cached /api/me, maps `{error,message}` to a typed ApiError) and TypeScript types for every contract shape in frontend/src/api/types.ts
- [ ] T030 [P] Implement the useMe query hook in frontend/src/api/hooks.ts and the app shell in frontend/src/App.tsx + frontend/src/routes.tsx (QueryClientProvider; routes `/` → Dashboard or SignIn based on /api/me, `/connect`, `/review`, `/settings`; header with user email and Sign out)
- [ ] T031 [P] Implement the SignIn page in frontend/src/pages/SignIn.tsx ("Sign in with Google" links to /auth/login; shows a "Access is limited to approved test accounts" message when `?error=not_allowed`)
- [ ] T032 [P] Create base styles and accessible primitives in frontend/src/styles/global.css and frontend/src/components/StateBanner.tsx (variants: info, loading, empty, error, reconnect; role="status"/"alert")

**Checkpoint**: Real Google sign-in works locally with the allowlisted account, the test harness
runs, and the migrations apply.

---

## Phase 3: User Story 1 - Connect Gmail and build the application table (Priority: P1) 🎯 MVP

**Goal**: A signed-in user reads the consent explanation, grants gmail.readonly, picks a start
date, clicks "Scan emails," watches progress, and sees one row per application (Company,
Position, Date Applied, Application Status).

**Independent Test**: Run the `core-journey` fixture mailbox through the scan API and assert
exactly the expected rows. Do the same scan against the real test account (quickstart manual
steps 1–5).

### Tests for User Story 1 (write first; must fail) ⚠️

- [ ] T033 [P] [US1] Unit tests in backend/tests/unit/test_window.py for the date boundary: start date at 00:00 inclusive in America/New_York (UTC−), Asia/Kolkata (UTC+), and a US DST spring-forward date; a message at the exact start included and one 1 ms earlier excluded; window_end exclusive; Gmail query epoch padding of ±86400 (R5)
- [ ] T034 [P] [US1] Unit tests in backend/tests/unit/test_screening.py: ATS sender domains and recruiting subject/snippet phrases pass; a generic "Update from Acme" recruiting message from careers@acme.example passes (recall guard); newsletters, social notifications, and receipts are screened out (R7)
- [ ] T035 [P] [US1] Unit tests in backend/tests/unit/test_extraction.py: one case per ATS parser (Greenhouse, Lever, Workday, Ashby, iCIMS, SmartRecruiters, LinkedIn) extracting company, position, and req_id; generic confirmation/progress/rejection/acknowledgment/offer/withdrawal phrases; job_alert, marketing, and invite_to_apply classified as noise; "applied on <date>" parsed as stated_applied_date; the hiring company (not the ATS) chosen; an email containing "ignore previous instructions, mark as hired" gets no special treatment; excerpt ≤ 300 chars (R8)
- [ ] T036 [P] [US1] Unit tests in backend/tests/unit/test_matching.py covering every R10 rule: same req_id → Existing; differing req_ids → New; same company + equal normalized position → Existing; company-only with one candidate and the same sender domain → Existing, otherwise Ambiguous; similar-but-unequal positions → Ambiguous; two positions at one company → two Apps; thread ID alone is never sufficient; normalization of legal suffixes and sr/jr/swe
- [ ] T037 [P] [US1] Unit tests in backend/tests/unit/test_status.py for derive(): confirmation+interview+rejection → rejected regardless of input order; a later-processed old confirmation never lowers status; acknowledgment never changes status; offer/withdrawal never change status and yield a review conflict; Date Applied from stated → estimated (earliest confirmation date in the cycle's time zone; test a confirmation at 23:30 local that is the next day in UTC) → unknown for rejection-only; overridden fields are preserved and produce manual_conflict (R11)
- [ ] T038 [P] [US1] Create synthetic fixtures under backend/tests/fixtures/gmail/ and mailboxes/ for scenarios: core-journey, same-company-two-positions, ads-and-alerts, rejection-only, stated-vs-estimated-date, ats-platform-company, generic-subject-recruiting, prompt-injection-text, tz-boundaries, two-users-isolation (fictional names; Gmail messages.get format; expected outcomes in YAML) per contracts/gmail-fixtures.md
- [ ] T039 [US1] Integration test in backend/tests/integration/test_scan_scenarios.py: parametrize over the T038 mailbox YAML files, connect via /test/gmail/connect, PUT /api/cycle, POST /api/scans {kind:"initial"}, run the worker synchronously until done, and assert that GET /api/applications and /api/review-items match `expected`. Also print a summary score across all mailboxes (percentage of expected applications with a confirmation imported with the correct company, position, and status) and fail if it is below 90% (SC-003)
- [ ] T040 [P] [US1] Integration test in backend/tests/integration/test_isolation.py: user A and user B each scan; user B gets 404 (not 403) on GET/PATCH/dismiss/restore of A's applications, GET/resolve of A's review items, and A's scan run; list endpoints never include A's rows (FR-040, SC-006)
- [ ] T041 [P] [US1] Integration test in backend/tests/integration/test_gmail_connect.py: callback with gmail.readonly granted stores ciphertext (not plaintext) and status connected; callback without the scope → status denied and no token; callback with mismatched state → rejected; callback without a session → rejected (Authlib token exchange stubbed)

### Implementation for User Story 1

- [ ] T042 [US1] Implement GoogleGmailClient in backend/app/gmail/google_client.py: httpx client against https://gmail.googleapis.com/gmail/v1/users/me; refresh access tokens with Authlib's OAuth2 client from the decrypted refresh token (in memory only); `get_profile`, `list_message_ids` (q, pageToken, maxResults=500, includeSpamTrash=false), `get_metadata` (format=metadata with the R7 metadataHeaders), and `get_full`; tenacity retry with exponential backoff and jitter (5 attempts, cap 60 s) on 429/5xx/timeouts; one refresh on 401; invalid_grant → GmailAuthError. Only GET requests, never a modify/send endpoint
- [ ] T043 [US1] Implement the Gmail connect flow in backend/app/auth/gmail_oauth.py: `GET /auth/gmail/connect` (requires a session; scope gmail.readonly only, access_type=offline, prompt=consent, PKCE, state, login_hint=user email) and `GET /auth/gmail/callback` (same session + valid state; error=access_denied or missing scope → upsert status denied and redirect `/?gmail=denied`; otherwise getProfile, encrypt the refresh token, upsert status connected with granted_scopes, redirect `/?gmail=connected`) per R2
- [ ] T044 [US1] Implement the cycle repository and `PUT /api/cycle` (first-time set only in this story; validates start_date ≤ today in TZ and an IANA timezone) in backend/app/repositories/cycles.py and backend/app/api/cycle.py
- [ ] T045 [P] [US1] Implement backend/app/pipeline/window.py: `window_start_utc(start_date, tz)`, `gmail_query(from_utc, to_utc)` with ±1-day epoch padding, `in_window(internal_date_ms, from, to)`, and `segments_for_run(cycle, now, kind)` returning `[{from,to}]` (initial: [start, now)) (R5)
- [ ] T046 [P] [US1] Implement backend/app/pipeline/screening.py: `screen(meta) -> (is_candidate, signals)` using the R7 candidate rule. A message is a candidate if it has ANY one of: (a) a sender domain on the ATS list; (b) a recruiting local part (careers, recruiting, recruiter, talent, jobs, hr, hiring, people); (c) a subject/snippet match on the R7 recruiting phrase list. Excluded only when none match. Noise is left to extraction
- [ ] T047 [P] [US1] Implement the declarative phrase and pattern table in backend/app/pipeline/extraction/rules.py (event-kind phrases, noise phrases, company/position/req_id/applied-date regexes) and the generic extractor in backend/app/pipeline/extraction/extract.py: the `Extractor` protocol, an `ExtractionResult` dataclass (kind, company, position, req_id, stated_applied_date, confidence, rule_id, excerpt ≤ 300 chars), and a pipeline that runs noise rules → ATS parsers → generic rules (R8)
- [ ] T048 [P] [US1] Implement ATS parsers in backend/app/pipeline/extraction/ats/ (greenhouse.py, lever.py, workday.py, ashby.py, icims.py, smartrecruiters.py, linkedin.py), each `parse(msg) -> ExtractionResult | None` using sender and template anchors, always returning the hiring company (not the platform)
- [ ] T049 [P] [US1] Implement backend/app/pipeline/matching.py: `normalize_company`, `normalize_position`, and `match(extraction, candidates) -> New | Existing(id) | Ambiguous(ids)` implementing the R10 rules in order
- [ ] T050 [P] [US1] Implement backend/app/pipeline/status.py: `derive(events, application, cycle_tz) -> Derived(status, date_applied, date_source, conflicts)` per R11 (pure function, no database access)
- [ ] T051 [US1] Implement backend/app/pipeline/apply.py: `apply_extraction(db, user, processed_message, extraction)` that inserts processed_messages (ON CONFLICT (user_id, gmail_message_id) DO NOTHING → skip), runs match(), creates or updates applications and application_events (idempotent attach), calls derive() and writes non-overridden fields, and creates review_items with dedupe_key ON CONFLICT DO NOTHING for possible_application, ambiguous_match, offer_or_withdrawal, contradictory_update, missing_field (FR-016–FR-029). Also sets recruiting_cycles.source_gmail_address on the first import
- [ ] T052 [US1] Implement backend/app/pipeline/retrieval.py: for each segment, page through list_message_ids, skip IDs already in processed_messages, fetch metadata with ThreadPoolExecutor(max_workers=settings.GMAIL_CONCURRENCY), apply in_window (out-of-window messages from the ±1-day padding are skipped WITHOUT inserting a processed_messages row, so a later back-fill still sees them), screen, fetch full for candidates, and yield (meta, full|None) in internal_date order per page. Non-candidates are recorded as `not_recruiting` with no sender/subject/excerpt (FR-044)
- [ ] T053 [US1] Implement backend/app/jobs/scan_job.py: `run_scan(db, run)` that iterates segments from segment_index/page_token, calls retrieval + extraction + apply per page, commits after each page with updated counters (listed, screened, candidates, processed, created_apps, updated_apps, review_items) and the page_token cursor, heartbeats every 15 s, re-reads gmail_connections before each page (if it is missing or not connected → stop immediately with failure_code gmail_disconnected, or reconnect_required, discard the access token, and make no further Gmail request), and on success marks the run succeeded and sets cycle covered_from/covered_to in the same transaction. GmailAuthError → mark the connection revoked, delete the ciphertext, failure_code reconnect_required. Exhausted retries → gmail_unavailable. Other errors → internal_error with no email content in logs
- [ ] T054 [US1] Implement backend/app/jobs/worker.py: the claim query (queued, or running with heartbeat older than 2 min; FOR UPDATE SKIP LOCKED; attempt+1; fail after 5 attempts), a loop with a 1 s idle sleep, `start_embedded_worker()` thread started from main.py lifespan when WORKER_MODE=embedded, a `python -m app.jobs.worker` entry point for external mode, and a `run_until_idle()` helper for tests (R6)
- [ ] T055 [US1] Implement scans endpoints in backend/app/api/scans.py: `POST /api/scans` (requires connected Gmail and a start date; 409 scan_in_progress via the partial unique index; window_end = now) and `GET /api/scans/current` (progress, results, failureCode; 204 if none) per contracts/http-api.md
- [ ] T056 [US1] Implement the applications repository and `GET /api/applications` (active, non-dismissed rows for the session user; default sort date_applied desc, nulls last; includes dateAppliedSource, beforeCycle, pendingReview) in backend/app/repositories/applications.py and backend/app/api/applications.py
- [ ] T057 [P] [US1] Implement the ConnectGmail page in frontend/src/pages/ConnectGmail.tsx: plain-language explanation of what is read (sender, subject, date, message text in the chosen range), what is stored (extracted details + short excerpts), that it's read-only, that content is analyzed only within ApplyFlow and never shared with third parties, and how to disconnect; a "Continue to Google" button → /auth/gmail/connect (FR-002)
- [ ] T058 [P] [US1] Implement the StartDatePicker component in frontend/src/components/StartDatePicker.tsx (date input max=today, detected timezone shown and editable via a select of Intl.supportedValuesOf('timeZone'), "inclusive from 00:00" helper text) calling PUT /api/cycle
- [ ] T059 [P] [US1] Implement the ScanProgress component in frontend/src/components/ScanProgress.tsx and a useCurrentScan hook in frontend/src/api/hooks.ts that polls GET /api/scans/current every 2 s while queued or running (examined N of ~estimate, M recruiting-related, processed count; aria-live="polite")
- [ ] T060 [P] [US1] Implement the ApplicationsTable component in frontend/src/components/ApplicationsTable.tsx with exactly four data columns (Company, Position, Date Applied, Application Status). Unknown values render as "Unknown", estimated dates carry an "est." marker with a tooltip, and status labels read Submitted / In progress / Rejected
- [ ] T061 [US1] Implement the Dashboard page in frontend/src/pages/Dashboard.tsx composing the onboarding steps (connect → start date → "Scan emails"), ScanProgress, ApplicationsTable, last successful sync time, the persistent disclaimer "Only applications with recognizable email evidence can be imported" (FR-033), and states: loading, empty-no-scan, empty-scan-found-nothing, failed-scan with Retry (FR-032)
- [ ] T062 [P] [US1] Vitest component tests in frontend/tests/Dashboard.test.tsx for the loading, empty-no-scan, empty-found-nothing, failed-scan, and populated states, and check that the table has exactly four column headers

**Checkpoint**: US1 is fully functional. Fixture scenarios pass, and a real scan of the test
account produces rows.

---

## Phase 4: User Story 2 - Return later and sync updates (Priority: P1)

**Goal**: The table persists across sessions. "Sync now" processes only new mail since the last
successful sync and updates existing rows without duplicates. Interrupted scans resume safely.

**Independent Test**: Scan `core-journey`, sign out and in (same table), append a new interview
fixture, run Sync now, and see the status change with the same row count. Re-running gives
identical counts.

### Tests for User Story 2 (write first; must fail) ⚠️

- [ ] T063 [P] [US2] Create fixtures and mailboxes for rescan-idempotent, out-of-order-confirmation, ack-after-interview, progress-after-rejection, crash-mid-page-resume, and sync-new-mail (with append sets) in backend/tests/fixtures/
- [ ] T064 [US2] Integration test in backend/tests/integration/test_sync.py: (a) running the same initial scan twice leaves identical application/event/review counts (SC-005); (b) appending an interview message then sync moves Submitted → In progress; (c) an old confirmation appended after a rejection keeps Rejected; (d) an acknowledgment after an interview keeps In progress; (e) progress after a rejection creates a contradictory_update review item and keeps Rejected; (f) a sync window starts 1 hour before the previous covered_to, and a message in that overlap that was already processed creates nothing new while one that wasn't is processed
- [ ] T065 [P] [US2] Integration test in backend/tests/integration/test_resume.py: page size 2, simulate a worker crash after the first page (abort in the test hook), set heartbeat_at stale, and run the worker again; the run resumes from the stored page_token, succeeds, and there are no duplicates. A failed run leaves covered_to unchanged (FR-011)
- [ ] T066 [P] [US2] Integration test in backend/tests/integration/test_persistence.py: logout, then login with the same sub, and the table, start date, and lastSuccessfulSyncAt are unchanged; a second concurrent POST /api/scans → 409 scan_in_progress

### Implementation for User Story 2

- [ ] T067 [US2] Extend `segments_for_run` in backend/app/pipeline/window.py for kind=sync: `[covered_to − 1 hour, now)` (overlap so late-listed mail isn't missed; duplicates are skipped by processed_messages) plus `[start, covered_from)` when the start date was moved earlier (FR-008)
- [ ] T068 [US2] Make the scan_job failure handling in backend/app/jobs/scan_job.py preserve the cursor, leave covered_* unchanged, and allow a new run to reuse processed_messages idempotency; add a test hook (APP_ENV=test only) to abort after N pages for T065
- [ ] T069 [US2] Add the "Sync now" button (disabled while a run is active or Gmail isn't connected) and "Last synced <relative time> (<local timestamp>)" to frontend/src/pages/Dashboard.tsx, invalidating the applications query when a run finishes
- [ ] T070 [P] [US2] Vitest test in frontend/tests/SyncNow.test.tsx: the button is disabled during a run, the poll stops after success, and the table refetches

**Checkpoint**: US1 + US2 make up the full P1 MVP: persistent, idempotent, resumable syncing.

---

## Phase 5: User Story 3 - Review evidence and correct results (Priority: P2)

**Goal**: A detail view shows evidence, event history, and the Date Applied explanation. Users
edit fields (overrides persist), resolve review items, and dismiss or restore "Not an
application" rows.

**Independent Test**: Scan fixtures with an offer, an ambiguous match, and a misread company;
the offer and the ambiguous match appear only in review. Correct the company, sync, and the
correction persists. Dismiss a row, sync, and it stays gone; restore it from Dismissed.

### Tests for User Story 3 (write first; must fail) ⚠️

- [ ] T071 [P] [US3] Create fixtures and mailboxes for ambiguous-company-only, shared-thread-two-positions, req-id-split, reapply-after-rejection, missing-position, manual-correction-then-sync, and dismiss-then-sync in backend/tests/fixtures/
- [ ] T072 [US3] Integration test in backend/tests/integration/test_review_and_corrections.py: GET detail returns events in chronological order with evidence and dateAppliedExplanation; PATCH company/position/dateApplied/status records manual_edit events and overriddenFields; status outside the 3 values → 422; a later conflicting email creates manual_conflict and keeps the user value (SC-009); resolve actions create/attach/apply/dismiss work and items never reappear after re-sync (FR-038); a resolved item → 409
- [ ] T073 [P] [US3] Integration test in backend/tests/integration/test_dismiss.py: dismissing hides the row from the active list and shows it in view=dismissed; new emails for it attach to the dismissed row (no new row); restore returns it unchanged (FR-038a)

### Implementation for User Story 3

- [ ] T074 [US3] Implement `GET /api/applications/{id}` in backend/app/api/applications.py with events joined to processed_messages evidence and a dateAppliedExplanation string per date_applied_source
- [ ] T075 [US3] Implement `PATCH /api/applications/{id}` in backend/app/api/applications.py + backend/app/repositories/applications.py: validate the fields, add them to overridden_fields, write a manual_edit event with {field, from, to}, set date_applied_source='user' for date edits, and re-run derive() for the other fields
- [ ] T076 [US3] Implement `POST /api/applications/{id}/dismiss` and `/restore` in backend/app/api/applications.py (set/clear dismissed_at, mark the linked processed_messages dismissed, write dismissed/restored events) and the `view=dismissed` list support
- [ ] T077 [US3] Implement the review repository and endpoints in backend/app/repositories/review.py and backend/app/api/review.py: `GET /api/review-items?state=pending` (evidence, application, candidates, pendingCount) and `POST /api/review-items/{id}/resolve` with create/attach/apply/dismiss, each writing a review_resolved event and re-deriving affected applications
- [ ] T078 [US3] Update backend/app/pipeline/apply.py so manual overrides raise manual_conflict review items (dedupe per application, field, and message) instead of overwriting (FR-036)
- [ ] T079 [P] [US3] Implement the ApplicationDetailDrawer in frontend/src/components/ApplicationDetailDrawer.tsx: fields with inline edit (status select limited to 3 values), the Date Applied explanation, the chronological event history with evidence (sender, subject, date, excerpt rendered as escaped text only), pending review items, and a "Not an application" button
- [ ] T080 [P] [US3] Implement the Review page in frontend/src/pages/Review.tsx and ReviewItemCard in frontend/src/components/ReviewItemCard.tsx (explanation, evidence, candidate list for attach, prefilled create form, apply and dismiss buttons); show the pending count badge in the header nav
- [ ] T081 [P] [US3] Add a Dismissed view (tab or toggle) to frontend/src/pages/Dashboard.tsx listing dismissed rows with Restore
- [ ] T082 [P] [US3] Vitest tests in frontend/tests/DetailAndReview.test.tsx: editing a field calls PATCH and updates the row; HTML in an excerpt renders as literal text; review resolve removes the card and decrements the badge

**Checkpoint**: US3 works on top of US1 data.

---

## Phase 6: User Story 4 - Find applications quickly (Priority: P2)

**Goal**: Search company/position, filter by status, and sort by Date Applied (unknown last).

**Independent Test**: With a known fixture table, each search, filter, and sort combination
returns the expected rows and order. No matches → "No matching applications" with Clear.

### Tests for User Story 4 (write first; must fail) ⚠️

- [ ] T083 [P] [US4] Integration test in backend/tests/integration/test_list_filters.py: q is a case-insensitive substring on company or position; multiple status params; sort asc/desc with null dates last in both; combined q+status; results always user-scoped

### Implementation for User Story 4

- [ ] T084 [US4] Add the q (ILIKE, escaped wildcards), status (repeatable, validated enum), sort=date_applied, and order params to `GET /api/applications` in backend/app/api/applications.py and backend/app/repositories/applications.py (NULLS LAST for both orders)
- [ ] T085 [P] [US4] Implement the Filters component in frontend/src/components/Filters.tsx (debounced search input, status multi-select checkboxes, sortable Date Applied header with aria-sort) synced to URL query params, and wire it into frontend/src/pages/Dashboard.tsx with a "No matching applications" + "Clear filters" state
- [ ] T086 [P] [US4] Vitest test in frontend/tests/Filters.test.tsx: typing updates the query param after the debounce, status toggles update the request, and the clear button resets everything

**Checkpoint**: US4 works independently on any populated table.

---

## Phase 7: User Story 5 - Control access and data (Priority: P2)

**Goal**: Disconnect Gmail (revoke + delete tokens, keep the table), delete imported data
separately, preview and confirm start-date changes (never silently delete), handle
denied/revoked access with recoverable reconnect states, guard against a mailbox mismatch, and
let the user delete their whole account.

**Independent Test**: Disconnect → table kept, no token row, scan disabled. Delete data → empty
table, connection kept. /test/gmail/revoke then Sync → reconnect state with rows intact. Move
the start date later → preview counts, confirm → rows labeled "before current cycle," none
deleted. Delete account → signed out, and no rows remain for the user.

### Tests for User Story 5 (write first; must fail) ⚠️

- [ ] T087 [P] [US5] Integration test in backend/tests/integration/test_account_controls.py: DELETE /api/gmail removes the gmail_connections row, calls revoke (stubbed), keeps applications, and POST /api/scans → 409 gmail_not_connected; DELETE /api/data requires confirm "DELETE", removes applications/events/review_items/processed_messages/scan_runs, keeps the connection and start_date, and returns 409 while a scan runs; disconnecting while a run is in progress fails it with gmail_disconnected, and the fixture client records zero calls after the disconnect (FR-041/042, SC-008)
- [ ] T088 [P] [US5] Integration test in backend/tests/integration/test_revoked_and_denied.py: revoke mid-scan (revoked-mid-scan fixture) → run failed with reconnect_required, connection status revoked, ciphertext NULL, rows intact, covered_to unchanged; a denied callback → /api/me gmail.status denied; reconnecting with a different mailbox while data exists → mailbox_mismatch and nothing stored
- [ ] T089 [P] [US5] Integration test in backend/tests/integration/test_cycle_change.py: preview earlier → willScanAddedPeriod true and rowsDeleted 0; preview later → rowsMarkedBeforeCycle equals the count of rows whose events all fall before the new date; PUT without confirm when data exists → 409 confirm_required; after confirm, rows are flagged before_cycle and none deleted; the next sync covers the added earlier period, including messages that an earlier scan saw only via the ±1-day padding (they must not have been recorded) (FR-043)
- [ ] T090 [P] [US5] Integration test in backend/tests/integration/test_account_deletion.py: DELETE /api/account without confirm "DELETE" → 422; with confirm, revoke is called (stubbed), any running scan is failed, every table has zero rows for the user (users, sessions, gmail_connections, recruiting_cycles, scan_runs, processed_messages, applications, application_events, review_items), the session cookie is cleared, another user's data is untouched, and a fresh sign-in with the same sub creates a new empty user (FR-042a)

### Implementation for User Story 5

- [ ] T091 [US5] Implement `DELETE /api/gmail` in backend/app/api/gmail.py: POST https://oauth2.googleapis.com/revoke with the decrypted refresh token (log only the outcome code), first mark any queued or running scan failed with gmail_disconnected, then revoke, then delete the gmail_connections row regardless of the revoke result (FR-041)
- [ ] T092 [US5] Add the mailbox-mismatch guard to backend/app/auth/gmail_oauth.py callback: if recruiting_cycles.source_gmail_address is set and differs from getProfile emailAddress, store nothing and redirect `/?gmail=mailbox_mismatch`
- [ ] T093 [US5] Implement `GET /api/cycle/preview-change` and confirm-gated date changes in `PUT /api/cycle` in backend/app/api/cycle.py + backend/app/repositories/cycles.py (later → set before_cycle on qualifying applications; earlier → keep covered_from so the next sync back-fills; never delete)
- [ ] T094 [US5] Implement `DELETE /api/data` in backend/app/api/data.py with confirm "DELETE", deleting the user's tracker tables and scan_runs in one transaction and resetting cycle coverage and source_gmail_address (FR-042)
- [ ] T095 [US5] Implement `DELETE /api/account` in backend/app/api/account.py: require confirm "DELETE" (422 otherwise) and CSRF; fail any queued or running scan; revoke Gmail at Google if connected (log outcome code only); delete the users row (ON DELETE CASCADE removes everything else) in one transaction; clear the af_session cookie (FR-042a)
- [ ] T096 [P] [US5] Implement the Settings page in frontend/src/pages/Settings.tsx: Gmail status with address, a Disconnect button with a confirm dialog explaining the effects, a "Delete imported data" button with a type-DELETE confirmation, a start-date change that shows the preview message before Confirm, and a "Delete account" button with a type-DELETE confirmation explaining that everything is removed and they will be signed out (FR-042a)
- [ ] T097 [P] [US5] Add the reconnect and denied states to frontend/src/pages/Dashboard.tsx and frontend/src/components/StateBanner.tsx: read `?gmail=denied|connected|mailbox_mismatch` and gmail.status revoked/denied, show the user-safe explanation (for revoked access, include "Google limits apps in testing to 7 days of access; reconnect to continue") and a "Reconnect Gmail" action, and keep the table visible (FR-005)
- [ ] T098 [P] [US5] Show a "Before current cycle" badge in frontend/src/components/ApplicationsTable.tsx for beforeCycle rows
- [ ] T099 [P] [US5] Vitest test in frontend/tests/Settings.test.tsx: the disconnect confirm flow, delete-data and delete-account both requiring the typed DELETE, delete account redirecting to sign-in, and the start-date preview shown before confirm

**Checkpoint**: All five user stories are independently functional.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: E2E, hardening, docs, deployment readiness

- [ ] T100 Create the Playwright config in frontend/playwright.config.ts with webServer entries that start the backend (`APP_ENV=test`, TEST_DATABASE_URL, `alembic upgrade head`, uvicorn :8000) and Vite (:5173), plus global setup resetting the test database
- [ ] T101 Write the main-journey E2E in frontend/e2e/main-journey.spec.ts using the core-journey fixture: test login → Connect page explanation visible → test connect → set start date → Scan emails → progress → exactly 3 rows with expected values → open detail (evidence + estimated date explanation) → correct company → Sync now with appended mail → status updated, no duplicates → sign out → sign in → same table
- [ ] T102 [P] Write E2E edge flows in frontend/e2e/states.spec.ts: revoked during sync → reconnect banner with rows intact; empty mailbox → empty-found-nothing state; review item resolve; dismiss and restore
- [ ] T103 [P] Accessibility pass across frontend/src/components/ and frontend/src/pages/: labeled inputs, table caption and scope headers, focus management in the drawer and dialogs, visible focus, color contrast. Verify with a Playwright MCP accessibility snapshot of each page
- [ ] T104 Security audit tasks recorded in docs/security-checklist.md: grep for logging of tokens or bodies across backend/app/, confirm only GET Gmail endpoints are used in backend/app/gmail/google_client.py, confirm cookie flags, confirm CSRF on every mutating route (a test in backend/tests/integration/test_csrf_all_routes.py enumerates the app routes and asserts 403 without the header)
- [ ] T105 [P] Create a multi-stage Dockerfile (node build of frontend/dist → python:3.12-slim with backend; runs `alembic upgrade head && uvicorn app.main:app`) and .dockerignore
- [ ] T106 Complete README.md "Local setup" and "Running tests": Google Cloud project + OAuth consent in Testing mode with the developer's Gmail as the only test user, redirect URIs, key generation, docker compose, alembic, uvicorn, npm run dev, pytest, vitest, Playwright
- [ ] T107 [P] Write docs/deployment.md: free-tier deployment of the single container (e.g. Render free web service + Neon free Postgres), required env vars, production redirect URIs, adding allowlisted test users in both Google and ALLOWED_GOOGLE_EMAILS, WORKER_MODE options, free-tier caveats (sleep, cold start, terms check), and a note that public launch requires Google restricted-scope verification
- [ ] T108 Run the full automated suite (pytest unit + integration, vitest, Playwright) and fix failures
- [ ] T109 Run the quickstart.md manual real-Gmail checklist (steps 0–13, including the SC-001 onboarding timing in step 0) with the designated test account and record the results in specs/001-email-application-tracker/checklists/manual-gmail-verification.md
- [ ] T110 Performance check against SC-002/SC-007: time a scan of the real test account (or a 3,000-message synthetic mailbox via FixtureGmailClient with simulated latency) and the dashboard load after sign-in; record the results in the same checklist and tune GMAIL_CONCURRENCY if needed

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: none
- **Foundational (Phase 2)**: depends on Setup. **Blocks all stories**
- **US1 (Phase 3)**: depends on Foundational
- **US2 (Phase 4)**: depends on US1 (extends the scan job and window segments)
- **US3 (Phase 5)**: depends on US1 (needs applications, events, review items from scans)
- **US4 (Phase 6)**: depends on US1 (list endpoint). Independent of US2/US3
- **US5 (Phase 7)**: depends on US1 (connection, cycle, scans). Independent of US3/US4
- **Polish (Phase 8)**: depends on all stories

### User Story Dependencies

```text
Setup → Foundational → US1 ─┬─> US2
                            ├─> US3
                            ├─> US4
                            └─> US5
                                  └─> Polish (after all)
```

US2–US5 can proceed in parallel once US1 is complete.

### Within Each User Story

- Tests and fixtures first, confirmed failing
- Pure pipeline modules (window, screening, extraction, matching, status) before apply/job
- Repositories before endpoints, endpoints before UI
- Story checkpoint before moving on

### Parallel Opportunities

- Setup: T003–T007 in parallel after T001/T002
- Foundational: T010, T011, T012–T014, T018, T019, T026–T028, T029–T032 in parallel (different
  files)
- US1: tests T033–T038, T040, T041 in parallel; pure modules T045–T050 in parallel; frontend
  T057–T060 in parallel with backend T051–T056
- US3/US4/US5 frontend tasks marked [P] in parallel with their backend tasks once endpoint
  shapes (contracts/http-api.md) are fixed
- After US1: US2, US3, US4, US5 in parallel by different developers

---

## Parallel Example: User Story 1

```bash
# Tests and fixtures together:
Task: "Unit tests for date boundary in backend/tests/unit/test_window.py"
Task: "Unit tests for screening in backend/tests/unit/test_screening.py"
Task: "Unit tests for extraction in backend/tests/unit/test_extraction.py"
Task: "Unit tests for matching in backend/tests/unit/test_matching.py"
Task: "Unit tests for derive() in backend/tests/unit/test_status.py"
Task: "Synthetic fixtures in backend/tests/fixtures/"

# Pure pipeline modules together:
Task: "window.py", "screening.py", "extraction rules + ATS parsers", "matching.py", "status.py"

# Frontend alongside backend apply/job work:
Task: "ConnectGmail.tsx", "StartDatePicker.tsx", "ScanProgress.tsx", "ApplicationsTable.tsx"
```

---

## Implementation Strategy

### MVP First (P1 = US1 + US2)

1. Phase 1 Setup → Phase 2 Foundational (real Google sign-in working)
2. Phase 3 US1 → **validate**: fixture scenarios pass, real scan of the test account works
3. Phase 4 US2 → **validate**: sync, idempotency, resume, persistence
4. Demo-ready MVP with real Gmail data and no mock data in the running app

### Incremental Delivery

1. + US3 (evidence, corrections, review, dismiss) → validate → demo
2. + US4 (search/filter/sort) → validate
3. + US5 (disconnect, delete, start-date change, reconnect) → validate
4. Polish: E2E, accessibility, security audit, docs, deployment readiness

Plan milestone mapping: M0 = Phase 1 + T008–T015, T018–T021; M1 = T016, T017, T022–T032; M2 = T041–T043;
M3 = T033–T039, T044–T055; M4 = T056–T062, T067–T070, T083–T086; M5 = Phase 5; M6 = Phase 7;
M7 = Phase 8.

---

## Notes

- [P] tasks touch different files and have no dependencies on incomplete tasks
- Never add mock data to the running app. FixtureGmailClient and /test routes exist only when
  APP_ENV=test
- Never log or persist email bodies, tokens, or secrets. Never call a Gmail endpoint other than
  read-only GETs
- Commit after each task or logical group (no Claude co-author lines)
- Stop at any checkpoint to validate a story independently
