# ApplyFlow

ApplyFlow turns your recruiting emails into an application tracker. You sign in with Google,
grant **read-only** Gmail access, choose the start date of your recruiting cycle, and scan. Each
application becomes one row with Company, Position, Date Applied, and Application Status
(Submitted / In progress / Rejected). Click "Sync now" later to pick up new emails.

- Spec: [specs/001-email-application-tracker/spec.md](specs/001-email-application-tracker/spec.md)
- Plan and design: [plan.md](specs/001-email-application-tracker/plan.md) ·
  [research.md](specs/001-email-application-tracker/research.md) ·
  [data-model.md](specs/001-email-application-tracker/data-model.md)
- Validation guide: [quickstart.md](specs/001-email-application-tracker/quickstart.md)
- Security checklist: [docs/security-checklist.md](docs/security-checklist.md)

**How it works:** a background job lists every email in your date range (Spam and Trash
excluded, archived included) and screens headers for recruiting signals. It reads likely
recruiting emails in memory, and deterministic rules extract company, position, dates, and
the type of update. No language model is used and nothing is sent to third parties. Only short
evidence excerpts are stored, never full emails. Anything uncertain goes to a **Review** area
instead of being guessed.

## Local setup

Everything runs locally at no cost.

**Prerequisites:** Python 3.12+, Node 22+, PostgreSQL 16+ (Homebrew, Postgres.app, or
`docker compose up -d db`), and a Google account with Gmail.

### 1. Google Cloud (free, one time)

1. Create a project at <https://console.cloud.google.com/> and **enable the Gmail API**.
2. **OAuth consent screen:** choose *External* and leave the publishing status as **Testing**.
   Add your Gmail address under **Test users**. Add the scopes `openid`, `email`, `profile`,
   and `https://www.googleapis.com/auth/gmail.readonly`.
3. **Credentials → Create OAuth client ID → Web application.** Add these authorized redirect
   URIs:
   - `http://localhost:5173/auth/callback`
   - `http://localhost:5173/auth/gmail/callback`

In Testing status Google shows an "unverified app" warning, and Gmail access expires after
**7 days**, so you'll reconnect about weekly. That's expected.

### 2. Configure

```bash
cp .env.example .env
# Fill in GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, and ALLOWED_GOOGLE_EMAILS (your Gmail).
python3 -c "import secrets; print(secrets.token_urlsafe(48))"                            # SESSION_SECRET
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"  # TOKEN_ENCRYPTION_KEYS
```

Set `DATABASE_URL` / `TEST_DATABASE_URL` for your Postgres. With a local Homebrew Postgres:
`postgresql+psycopg://localhost:5432/applyflow` and `.../applyflow_test`. The test database
name **must** end in `_test`.

### 3. Database

```bash
createdb applyflow && createdb applyflow_test     # or: docker compose up -d db
```

### 4. Backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate   # or: uv venv --python 3.12 .venv
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload --port 8000            # API + embedded scan worker
```

### 5. Frontend

```bash
cd frontend
npm install
npm run dev                                          # http://localhost:5173
```

Open <http://localhost:5173>, sign in, connect Gmail, choose a start date, and click
**Scan emails**.

## Running tests

All automated tests use synthetic email fixtures. They never touch a real Gmail account.

```bash
cd backend && .venv/bin/python -m pytest          # unit + integration (needs the *_test DB)
cd frontend && npm test                           # component tests (Vitest)
cd frontend && npx playwright install chromium    # first time only
cd frontend && npx playwright test                # end-to-end, APP_ENV=test on ports 8001/5174
```

- **Fixtures:** test emails are authored in
  `backend/tests/fixtures/sources/messages.yaml`. Regenerate the Gmail-shaped JSON with
  `python tests/fixtures/build_fixtures.py`.
- **Scenarios:** mailbox scenarios and their expected rows are in
  `backend/tests/fixtures/mailboxes/`.
- **Real Gmail:** the manual check against real Gmail is in
  [quickstart.md](specs/001-email-application-tracker/quickstart.md#manual-real-gmail-verification-designated-test-account).

## Deployment

ApplyFlow ships as one container: FastAPI serves the built React app from a single origin. See
[docs/deployment.md](docs/deployment.md) for a free-tier setup for a small allowlist of test
users.
