# Quickstart & Validation Guide: Email-Driven Application Tracker

**Feature**: `001-email-application-tracker`

This guide covers running ApplyFlow locally at no cost and checking that it works. API shapes
are in [contracts/http-api.md](contracts/http-api.md), tables in
[data-model.md](data-model.md), and fixtures in
[contracts/gmail-fixtures.md](contracts/gmail-fixtures.md). The repository's `README.md`
(created during implementation) holds the full setup and deployment instructions. This file is
the validation checklist.

## Prerequisites

- Python 3.12, Node 22 LTS, Docker Desktop (for local Postgres), and a Google account with Gmail
  (the **designated test account**).
- A Google Cloud project (free) with:
  - Gmail API enabled.
  - OAuth consent screen: **External**, publishing status **Testing**, the test account added
    under *Test users*, and scopes `openid`, `email`, `profile`,
    `https://www.googleapis.com/auth/gmail.readonly`.
  - OAuth client (Web application). Authorized redirect URIs:
    `http://localhost:5173/auth/callback` and `http://localhost:5173/auth/gmail/callback`.

> **Weekly reconnect**: while the OAuth app is in **Testing** status, Google's refresh tokens for
> Gmail access expire after 7 days. Expect the reconnect banner about once a week. This is
> normal, and reconnecting takes one click.

## Setup

```bash
cp .env.example .env          # fill GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET,
                              # SESSION_SECRET, TOKEN_ENCRYPTION_KEYS, ALLOWED_GOOGLE_EMAILS
docker compose up -d db       # Postgres 16 on localhost:5432 (applyflow + applyflow_test DBs)
cd backend && python -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload --port 8000       # API + embedded scan worker
cd ../frontend && npm install && npm run dev    # http://localhost:5173
```

Generate keys: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.

## Automated validation (synthetic fixtures; no real Gmail)

| Command | Proves |
|---|---|
| `cd backend && pytest tests/unit` | screening, extraction, matching, status/date derivation, time zone boundaries, log redaction |
| `cd backend && pytest tests/integration` | every mailbox scenario in the fixtures contract, idempotent re-scan, crash-resume, revoke-mid-scan, user isolation on every route, disconnect and delete flows |
| `cd frontend && npm test` | component states (loading, empty, failed, reconnect, review count) |
| `cd frontend && npx playwright test` | main journey end-to-end against `APP_ENV=test` with the `core-journey` mailbox |

**Expected**: all pass. The `core-journey` E2E ends with exactly 3 rows (Acme Robotics/Software
Engineer = Rejected; Acme Robotics/Product Manager = Submitted; Globex/Data Analyst = Rejected
with Date Applied "Unknown") and 1 pending review item (offer). Running the scan again leaves
3 rows. Signing out and back in shows the same table.

## Interactive inspection (Playwright MCP)

With the dev servers running, use Playwright MCP to open `http://localhost:5173` and inspect:
the consent explanation screen, scan progress updates, the empty state, the failed-scan state,
the reconnect state, the search/filter/sort controls, the detail view (evidence, history, Date
Applied explanation), the review area, and the Dismissed view. Check the accessibility snapshot
for labeled controls and table headers.

## Manual real-Gmail verification (designated test account)

Run with `APP_ENV=development` (real Google). Tick each item:

0. [ ] **Onboarding time (SC-001)**: start a timer at the first visit and stop it when the scan
       starts. Record the time (target: under 5 minutes, excluding the scan itself).
1. [ ] Sign in with Google. Only `openid email profile` is requested, and the dashboard shows
       "Connect Gmail".
2. [ ] Connect Gmail. ApplyFlow's explanation appears first. Google's consent lists **only**
       "Read your email messages and settings" (read-only). The "unverified app" warning is
       expected in testing mode.
3. [ ] Repeat the connection but untick the Gmail box. The app shows the **denied** state with
       "Try again".
4. [ ] Choose a start date about 1–3 months back and click **Scan emails**. Progress updates,
       and the run succeeds. Real recruiting emails produce sensible rows, and job alerts don't.
5. [ ] Open a row. The evidence excerpts and Date Applied explanation are present, and no raw
       HTML is rendered.
6. [ ] Correct a field, click **Sync now**, and confirm the correction persists. The last
       successful sync time updates.
7. [ ] In the Google Account → Security → Third-party connections page, remove ApplyFlow's
       access. Click **Sync now**, and the **reconnect** state appears with rows intact.
       Reconnect and sync successfully.
8. [ ] Disconnect Gmail in ApplyFlow. The table remains, and scanning is unavailable. In the
       database, `gmail_connections` has no row for the user.
9. [ ] `grep -riE "ya29\.|refresh_token|BEGIN" logs/ backend/*.log` finds nothing. The server
       output contains no email bodies.
10. [ ] Delete imported data. The table is empty, and the Gmail connection is unchanged.
11. [ ] Start a scan, then disconnect while it runs. The run fails with "Gmail disconnected",
        saved rows remain, and the server log shows no Gmail request after the disconnect.
12. [ ] Delete account in Settings. You're signed out, and signing in again shows a fresh
        onboarding with no data. In the database, no rows remain for the old user.
13. [ ] Confirm that Gmail itself is unchanged: no messages read/unread-toggled, labeled,
        archived, or deleted.
