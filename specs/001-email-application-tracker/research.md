# Research: Email-Driven Application Tracker

**Feature**: `001-email-application-tracker` | **Date**: 2026-11-25

Each entry records a decision, the reason for it, and the alternatives considered. All
Technical Context unknowns are resolved here.

---

## R1. Stack

- **Decision**: Python 3.12 + FastAPI backend, SQLAlchemy 2.x (synchronous) + psycopg 3,
  Alembic migrations, PostgreSQL 16. Frontend: React 18 + TypeScript + Vite, React Router,
  TanStack Query. Node 22 LTS for tooling.
- **Rationale**: Specified by the user. Synchronous SQLAlchemy is simpler to reason about and
  test than async. The worker uses threads for bounded I/O concurrency (R6), so async database
  access isn't needed.
- **Alternatives**: Async SQLAlchemy (more moving parts with no benefit at this scale);
  SQLModel (thinner documentation for migrations).

## R2. Sign-in (OIDC) and Gmail authorization as separate flows

- **Decision**: Use **Authlib** (maintained, supports OIDC and Starlette) with two separate
  OAuth client registrations on the same Google Cloud OAuth client:
  1. **Sign-in**: scopes `openid email profile`, with PKCE, `state`, and `nonce` validated.
     Users are identified by the ID token's `sub` (stable Google account ID), never by email.
  2. **Gmail connect**: scope `https://www.googleapis.com/auth/gmail.readonly` only, with
     `access_type=offline`, `prompt=consent` (guarantees a refresh token), PKCE, and `state`.
     `include_granted_scopes` is not set, so sign-in and mail access stay separate grants.
- **Account linking**: The Gmail callback is accepted only when the server-side session belongs
  to a signed-in user and the `state` matches the one issued to that session. The connection is
  linked to that user. The connected mailbox address comes from Gmail `users.getProfile`
  (allowed under `gmail.readonly`). If imported data exists from a *different* mailbox address,
  the connection is refused until the user deletes imported data (spec edge case).
- **Granular consent**: Google lets users untick the Gmail box. The callback checks the granted
  `scope`. A missing `gmail.readonly` is treated as **denied** (FR-005).
- **Rationale**: Keeps sign-in usable without mailbox access (FR-001), keeps the requested
  scope minimal (Constitution IV), and links by `sub`, which is robust to email changes.
- **Alternatives**: A single combined consent (violates FR-001 and the user's instruction);
  google-auth-oauthlib (fine for flows, but no OIDC/Starlette session integration);
  FastAPI-Users (heavier, built around password accounts).

## R3. Sessions and CSRF

- **Decision**:
  - **App session**: opaque random ID (32 bytes) in cookie `af_session` (`HttpOnly`,
    `SameSite=Lax`, `Secure` outside local dev, path `/`). Server-side row in `sessions`
    stores the SHA-256 of the ID, `user_id`, `csrf_token`, `expires_at` (14 days, sliding), and
    `created_at`. The ID is rotated at sign-in, and sign-out deletes the row.
  - **OAuth transient state**: Starlette `SessionMiddleware` (signed cookie `af_oauth`,
    10-minute max age) holds only Authlib's `state`, `nonce`, and PKCE verifier. It holds no
    tokens or identity.
  - **CSRF**: Every state-changing `/api/*` request must send header `X-CSRF-Token` matching
    the session's token (returned by `GET /api/me`). Together with `SameSite=Lax`, this blocks
    cross-site form posts.
- **Rationale**: Server-managed sessions can be revoked and keep identity off the client
  (Constitution IV). Same-origin serving (R13) keeps cookies simple.
- **Alternatives**: JWT in localStorage (exposed to XSS; can't revoke); signed-cookie sessions
  only (can't be revoked server-side).

## R4. Token storage and encryption

- **Decision**: Store only the **refresh token**, encrypted with `cryptography`'s
  `MultiFernet` (AES-128-CBC + HMAC-SHA256) using keys from env `TOKEN_ENCRYPTION_KEYS`
  (comma-separated, newest first, to allow rotation). The key never lives in the database.
  Access tokens are obtained per job and held only in memory. On disconnect, call Google's
  revoke endpoint (`https://oauth2.googleapis.com/revoke`), then delete the ciphertext row even
  if revocation fails, and record the failure without the token. On `invalid_grant` during a
  job, mark the connection `revoked`, delete the ciphertext, and fail the run with reason
  `reconnect_required`.
- **Rationale**: Satisfies Constitution IV and FR-041/FR-045 with a well-reviewed primitive.
- **Alternatives**: pgcrypto (puts the key in SQL statements and logs); KMS (costs money and
  isn't available locally).

## R5. Date boundary → exact timestamp

- **Decision**: Store `start_date` (date) and `timezone` (IANA name; browser-detected and
  editable). Compute `window_start_utc = datetime.combine(start_date, time.min,
  ZoneInfo(tz)).astimezone(UTC)`. A run's `window_end_utc` is the moment the run was created.
  Inclusion test on Gmail `internalDate` (ms epoch): `window_start <= internalDate <
  window_end`.
- **Gmail query**: `after:{epoch(window_start) - 86400} before:{epoch(window_end) + 86400}`
  (epoch-second form, padded by a day). The exact boundary is then applied in code using
  `internalDate`. This avoids depending on Gmail's undocumented inclusive/exclusive semantics
  and time zone interpretation.
- **Spam/Trash**: `includeSpamTrash=false` (the default) excludes them. No `in:inbox`
  restriction, so archived mail is included.
- **DST**: `ZoneInfo` handles midnight in DST-shifting zones. Tests cover a spring-forward date
  and a start date in a UTC+ and a UTC− zone.
- **Alternatives**: Gmail `after:YYYY/MM/DD` (interpreted in an ambiguous zone, so not exact).

## R6. Background jobs: simplest reliable worker arrangement

- **Decision**: A **Postgres-backed job table** (`scan_runs`) plus a **worker loop** that runs
  in a background thread inside the API process by default (`WORKER_MODE=embedded`). The same
  loop can run as a separate process (`python -m app.jobs.worker`, `WORKER_MODE=external`)
  when deployed.
  - **Claim**: `SELECT … WHERE status IN ('queued') OR (status='running' AND heartbeat_at <
    now() - 2 min) ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1`, then set
    `status='running'`, `worker_id`, `heartbeat_at`.
  - **Heartbeat** every 15 s while running. A run with a stale heartbeat is reclaimed after a
    crash or restart (recovery after interruption).
  - **Resumable progress**: the run stores the Gmail `next_page_token` it is on and counters
    (`listed`, `screened`, `fetched`, `processed`, `candidates`). Already-processed messages are
    skipped via the `processed_messages` unique key, so a resumed run never duplicates work or
    rows (FR-010).
  - **One active run per user**: partial unique index on `scan_runs(user_id) WHERE status IN
    ('queued','running')` (FR-009).
  - **Bounded concurrency**: a `ThreadPoolExecutor(max_workers=GMAIL_CONCURRENCY, default 8)`
    fetches messages for a page, and processing happens sequentially in date order per page.
  - **Retries**: HTTP 429/5xx/timeouts are retried with exponential backoff and jitter
    (`tenacity`; 5 attempts, cap 60 s). 401 triggers one token refresh. `invalid_grant` fails
    with `reconnect_required`. Other unrecoverable errors fail the run with a user-safe reason,
    the last successful sync time is not advanced (FR-011), and the user can retry (a new run
    resumes via idempotency).
  - **Batching**: work is chunked per page (up to 500 IDs), with a database commit after each
    chunk, so an interruption loses at most one chunk of work.
- **Rationale**: Uses infrastructure we already have (Postgres), works locally with one command,
  survives restarts, and moves to a separate worker process later without code changes.
- **Alternatives**: Celery/RQ + Redis (extra service, extra free-tier dependency); FastAPI
  `BackgroundTasks` (not persisted, lost on restart); APScheduler (no persisted claiming).

## R7. Retrieval and relevance screening (no single narrow query)

- **Decision**: Two-stage retrieval across the **whole** date range:
  1. **List** all message IDs in the range (`users.messages.list`, `maxResults=500`, paginated
     with the R5 query and **no keyword filter**).
  2. **Screen** each message using `format=metadata` (headers `From`, `Subject`, `Date`,
     `List-Unsubscribe`, `Reply-To`, plus `snippet` and `labelIds`). This is cheap and returns
     no body. The deterministic screener scores recruiting relevance from: known
     applicant-tracking-system (ATS) sender domains (greenhouse.io, lever.co, myworkday.com,
     myworkdayjobs.com, ashbyhq.com, icims.com, smartrecruiters.com, jobvite.com, workable.com,
     taleo.net, successfactors, linkedin.com application notices, etc.), recruiting phrases in
     the subject or snippet, and `careers@`/`recruiting@`/`talent@`/`jobs@` style local parts.
     Messages scoring above a **deliberately low** threshold become candidates. Every screened
     message is counted, so progress reports "examined N emails, M looked recruiting-related."
  3. **Fetch** candidates with `format=full`. The body is parsed in memory and discarded after
     extraction.
- **Recall safeguard**: The screener is tuned to favor recall. The fixture suite includes
  recruiting emails with generic subjects ("Update from Acme") from non-ATS domains to prevent
  silent misses. Screened-out messages are recorded in `processed_messages` with
  `classification='not_recruiting'` and no excerpt, so they aren't re-screened and the screen
  decisions can be audited by count.
- **Quota**: `messages.list` = 5 units, `messages.get` = 5 units. The per-user limit is well
  above 8 concurrent requests. 3,000 metadata gets plus about 300 full gets complete in a few
  minutes (SC-002).
- **Alternatives**: A keyword-only Gmail search (rejected by the user: it misses applications
  silently); `format=full` for everything (pulls large newsletter bodies for no benefit); the
  Gmail History API for syncs (needs `historyId` bookkeeping and expires after about a week;
  date-window re-listing with idempotency is simpler and correct).

## R8. Deterministic extraction

- **Decision**: A pipeline of pure functions, each `(ParsedMessage) -> ExtractionResult | None`:
  1. **ATS-specific parsers** for known formats (Greenhouse, Lever, Workday, Ashby, iCIMS,
     SmartRecruiters, LinkedIn "application was sent to"), using sender and template phrase
     anchors to pull the company, position, and requisition ID.
  2. **Generic phrase rules** in a declarative table (`rules.py`) mapping phrase patterns to an
     event kind: `confirmation`, `progress`, `rejection`, `acknowledgment`, `offer`,
     `withdrawal`, `job_alert`, `marketing`, `invite_to_apply`. Extraction patterns such as
     "applying to {company} for (the)? {position} (role|position)", "Req(uisition)? ?(ID|#):?
     {id}", and "applied on {date}".
  3. **Noise rules** run first: `List-Unsubscribe` plus alert or marketing phrasing → ignored.
     "Apply now" or "jobs you may like" → `invite_to_apply`/`job_alert` (FR-016).
  - **Output**: `kind`, `company?`, `position?`, `req_id?`, `stated_applied_date?`,
    `confidence` (`high`/`low`), `rule_id`, and `excerpt` (the matched sentence plus a little
    context, ≤ 300 chars, whitespace-collapsed).
  - `low` confidence, missing company, or an unknown kind with recruiting signals →
    **review item** (FR-018). The company is the hiring company, never the ATS or job-board
    brand (spec edge case).
  - HTML is converted to text with BeautifulSoup (`html.parser`). The text is never rendered,
    only parsed.
- **Rationale**: Deterministic and fully testable (same input gives the same output), it costs
  nothing, and nothing leaves the server (FR-020a, Constitution V).
- **Alternatives**: An ML classifier (needs training data); an LLM (see R9).

## R9. Optional LLM fallback: proposal only, disabled, not part of the MVP

The clarification session (Q1) chose **rules only, with no third-party processing**. The fallback
below is documented so it can be adopted later through a spec amendment. It is **not
implemented** in the MVP. Only an interface seam (`Extractor` protocol) is kept, so adding it
later doesn't need a redesign.

- **Trigger**: only messages that passed screening and that the deterministic pipeline marked as
  recruiting-related but `low` confidence or missing company/position. The whole mailbox is
  never sent.
- **Payload minimization**: subject, sender domain (not the full address), date, and at most
  2,000 characters of whitespace-collapsed body text, with email addresses and phone numbers
  redacted. No user identity is sent.
- **Provider**: Anthropic Claude API with a small, fast model (for example
  `claude-haiku-5-5`) using structured output (a JSON schema matching `ExtractionResult`), with
  **no tools**. Email text is wrapped in delimiters and labeled as untrusted data
  (Constitution V). The output is schema-validated, and anything invalid → review item.
- **Cost**: Estimated volume is about 5–10% of candidates (about 15–30 messages per 3-month
  scan × about 1k tokens each). Exact cost **must be computed from the provider's published
  pricing at enablement time** and recorded in the spec amendment. Hard cap via env
  `AI_FALLBACK_MAX_MESSAGES_PER_RUN`.
- **Disclosure**: The consent explanation (FR-002) must add that excerpts of some ambiguous
  emails are sent to the named provider. This requires a per-user opt-in toggle, off by default.
- **Data handling**: Use the provider's API (not consumer apps); the API data-retention and
  no-training terms must be confirmed and cited at enablement. Requests and responses are not
  logged. The results are stored like any other extraction, with `rule_id='llm_fallback'`.
- **Enablement gate**: requires a spec amendment (reverting clarification Q1), constitution
  review (Principles III and V), the env flag `AI_FALLBACK_ENABLED=true`, and the user opt-in.

## R10. Application matching

- **Decision**: A pure function `match(extraction, user_applications) -> New | Existing(id) |
  Ambiguous(ids)`:
  - **Normalization**: company is lowercased and stripped of legal suffixes (inc, llc, ltd,
    corp, gmbh), punctuation, and "the". Position is lowercased with punctuation collapsed, and
    `sr`→`senior`, `jr`→`junior`, `swe`→`software engineer`, `eng`→`engineer`; requisition
    codes are removed from the title.
  - **Rules, in order**:
    1. Same normalized company and same req ID → Existing.
    2. Same normalized company, both have req IDs, and they differ → not this candidate.
    3. Same normalized company and equal normalized position → Existing, unless the email is a
       `confirmation` dated after a `rejection` on that candidate with no req ID to tell them
       apart → Ambiguous (possible re-application).
    4. Same company, position missing, exactly one non-dismissed candidate, and the same
       sender domain or the same Gmail thread as one of its evidence messages → Existing.
       Otherwise → Ambiguous.
    5. Same company, positions differ but are similar (token Jaccard ≥ 0.6 without being equal)
       → Ambiguous.
    6. No candidate → New (if company and position are known; otherwise review
       `missing_field`).
  - The Gmail thread is only **supporting** evidence in rule 4 and is never sufficient on its own
    (FR-023).
- **Dismissed applications** (FR-038a) are matched like any other application, so their new
  emails attach to the dismissed row instead of creating a new one.

## R11. Status and Date Applied calculation

- **Decision**: A pure function `derive(app_events, overrides) -> (status, date_applied,
  date_source, conflicts)`, recomputed from all events each time, so processing order doesn't
  matter (FR-028).
  - **Events are sorted** by `occurred_at` (email `internalDate`), with ties broken by rank.
    Rank: `confirmation`=1 (Submitted), `progress`=2 (In progress), `rejection`=3 (Rejected).
    `acknowledgment` has no effect on status.
  - **Status** = the status of the highest-ranked event, *but* a `progress` dated after a
    `rejection` → conflict (`contradictory_update`), and the status stays Rejected until it is
    resolved. A `confirmation` never lowers status.
  - `offer`/`withdrawal` events never change status → review item (FR-017).
  - **Date Applied**: the earliest `stated_applied_date` among confirmations → `stated`; else
    the earliest confirmation's `occurred_at` date in the user's time zone → `estimated`; else
    `null` → `unknown` (FR-025/026).
  - **Manual overrides** (FR-036): an overridden field keeps the user's value. If newly derived
    evidence would change that field, raise a `manual_conflict` review item (deduplicated per
    application, field, and source message).
- **Rationale**: Recomputing from events is idempotent and easy to unit-test against every
  ordering.

## R12. Data minimization and logging

- **Decision**: Persist message ID, thread ID, sender (display name plus address), subject,
  `internalDate`, classification, rule ID, and excerpt (≤ 300 chars) for recruiting messages
  only. For non-recruiting messages, persist only the message ID, date, and
  `classification='not_recruiting'`. Bodies are never written to disk or logs. Logging uses the
  standard library `logging` with JSON output and a redaction filter that drops any `body`,
  `token`, `authorization`, `refresh_token`, `code`, or `id_token` keys and masks `Bearer` or
  `ya29.` patterns. HTTP client debug logging is disabled. Excerpts are displayed with React's
  default escaping, and raw email HTML is never rendered (Constitution V).

## R13. Serving, local development, deployment

- **Local**: `docker compose up db` (Postgres 16; free), `uvicorn app.main:app --reload`
  (embedded worker), and `npm run dev` (Vite with `/api` and `/auth` proxied to FastAPI, so
  cookies are same-origin). The Google OAuth client is in **testing mode** with only the
  developer's Gmail as a test user. Redirect URIs are `http://localhost:5173/auth/callback` and
  `http://localhost:5173/auth/gmail/callback`, with requests reaching FastAPI through the
  Vite proxy.
- **Production build**: `vite build` → `frontend/dist`, served by FastAPI as static files with an
  SPA fallback. This gives a single origin and a single container.
- **Deployment (documented, not executed)**: one Docker image to a free web host (for example
  Render free web service) with a free managed Postgres (for example Neon). Use
  `WORKER_MODE=embedded` on a single instance, and set `ALLOWED_GOOGLE_EMAILS` to enforce the
  allowlist in-app in addition to Google testing mode. Free-tier limits (sleep, cold start) are
  covered by job recovery (R6). Provider terms must be checked at deploy time.

## R14. Testing strategy

- **Unit (pytest)**: screening, extraction (per-ATS and generic rules), matching, status/date
  derivation (all event orderings), date boundary math (time zones, DST, inclusive start,
  exclusive end), redaction filter.
- **Integration (pytest + real Postgres via docker compose, transactional per test)**: scan
  pipeline end-to-end using `FixtureGmailClient` over synthetic messages (the same interface as
  `GmailClient`). Idempotent re-scan, resume after a simulated crash mid-page, user isolation on
  every `/api` route (two synthetic users), disconnect/delete flows, manual-correction
  persistence. Scenario tests mirror each spec acceptance scenario.
- **Synthetic fixtures**: JSON files in Gmail API `users.messages.get` shape (base64url bodies,
  headers, `internalDate`, `labelIds`, `threadId`) under `backend/tests/fixtures/gmail/`. They
  are made-up companies and people only. Mailbox scenarios are composed in
  `backend/tests/fixtures/mailboxes/*.yaml`.
- **E2E (Playwright, `@playwright/test`)**: the main journey (sign in → connect → choose date →
  scan → table → detail → correct → sync → sign out/in). It runs against the backend started with
  `APP_ENV=test`, which swaps in `FixtureGmailClient` and enables a test-only sign-in route
  (see plan Complexity Tracking). The test route and fixture client are registered only when
  `APP_ENV=test`. In that mode, Google credentials are ignored, and startup refuses to run
  unless the database name ends in `_test`. The default `APP_ENV` is `development` and
  always uses real Google and Gmail.
- **Interactive inspection**: Playwright MCP is used during development to drive and inspect the
  running UI (states, layout, accessibility snapshot).
- **Real OAuth/Gmail verification**: a manual checklist in `quickstart.md`, run with the
  designated test account (the developer's allowlisted Gmail). It covers consent, scope
  untick/deny, scan, revoke from the Google account page, reconnect, and disconnect.
