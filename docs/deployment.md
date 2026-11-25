# Deploying ApplyFlow (free tier, allowlisted test users)

ApplyFlow builds into **one Docker image**. FastAPI serves the API and the built React app from
the same origin, and the scan worker runs inside the same process (`WORKER_MODE=embedded`).
Everything persists in PostgreSQL, so restarts and free-tier sleeps are safe: an interrupted
scan resumes from its saved cursor.

> Free tiers change often. Check each provider's current limits and terms before relying on
> them. Some free tiers are non-commercial only.

## 1. Database

Create a free managed PostgreSQL 16+ database (for example **Neon** or **Supabase**). Copy its
connection string and convert it to the psycopg driver form:

```
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST/DBNAME?sslmode=require
```

Migrations run automatically on container start (`alembic upgrade head`).

## 2. Web service

Deploy the repository's `Dockerfile` to a free web host (for example **Render** → New Web
Service → Docker). The container listens on `$PORT`, or 8000 if that's unset.

Required environment variables:

| Variable | Value |
|---|---|
| `APP_ENV` | `production` (enables `Secure` cookies; refuses weak secrets) |
| `DATABASE_URL` | from step 1 |
| `APP_BASE_URL` | your public URL, e.g. `https://applyflow.onrender.com` |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | from Google Cloud |
| `SESSION_SECRET` | a long random string |
| `TOKEN_ENCRYPTION_KEYS` | a Fernet key (comma-separated, newest first, to rotate) |
| `ALLOWED_GOOGLE_EMAILS` | comma-separated emails of approved test users |
| `WORKER_MODE` | `embedded` (default). For a separate worker, set `external` and run `python -m app.jobs.worker` |
| `GMAIL_CONCURRENCY` | optional, default 8 |

Keep exactly **one** instance when `WORKER_MODE=embedded`. Scans are still safe with more,
because runs are claimed with `FOR UPDATE SKIP LOCKED`, but one instance is all this needs.

## 3. Google OAuth for the deployed URL

In Google Cloud → Credentials → your OAuth client, add these authorized redirect URIs:

- `https://YOUR-HOST/auth/callback`
- `https://YOUR-HOST/auth/gmail/callback`

On the OAuth consent screen, keep the publishing status **Testing** and add each approved user
under **Test users** (Google allows up to 100). Add the same addresses to
`ALLOWED_GOOGLE_EMAILS`. Both lists must include a user for sign-in to work.

## 4. Free-tier caveats

- **Sleep / cold start:** idle free services may sleep. The first request can be slow, and a
  scan interrupted by sleep resumes when the service wakes (heartbeat reclaim after 2 minutes).
- **Database pause:** some free databases pause after a period of inactivity. Wake it before a
  demo.
- **7-day Gmail access:** apps in Testing status get refresh tokens that expire after 7 days.
  Users see a "Reconnect Gmail" banner, and reconnecting is one click.

## 5. Going public

Opening ApplyFlow to the public requires Google's **restricted-scope verification** for
`gmail.readonly`, including an independent security assessment. That's out of scope for the
MVP.
