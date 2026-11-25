# Security checklist (T104)

Audit of the MVP against the constitution (Principles III, IV, V and the Security & Data
Handling section). Automated checks are referenced; re-run them before every release.

| Check | Result | How it's verified |
|---|---|---|
| Only `gmail.readonly` is requested | ✅ | `app/auth/google.py`; `tests/integration/test_gmail_connect.py::test_connect_requests_only_gmail_readonly` |
| Only read-only Gmail API calls (GET); the one POST is the OAuth token refresh | ✅ | `tests/integration/test_csrf_all_routes.py::test_gmail_client_only_uses_read_only_get_requests` |
| Refresh tokens encrypted at rest with an env key (MultiFernet); access tokens never stored | ✅ | `app/auth/crypto.py`; `test_gmail_connect.py::test_granted_scope_stores_encrypted_token` |
| Tokens never sent to the browser | ✅ | `/api/me` returns only status + address; no endpoint serializes `GmailConnection` tokens |
| Disconnect revokes at Google, deletes credentials, cancels scans, no further Gmail calls | ✅ | `test_account_controls.py` |
| Delete account removes every row for the user | ✅ | `test_account_deletion.py` |
| Server-side sessions; cookie `HttpOnly`, `SameSite=Lax`, `Secure` in production | ✅ | `app/auth/sessions.py`; `test_csrf_all_routes.py::test_session_cookie_flags` |
| CSRF header required on every mutating route | ✅ | `test_csrf_all_routes.py::test_every_mutating_route_rejects_missing_csrf` (enumerates all routes) |
| OAuth `state`, `nonce`, PKCE validated (Authlib); session rotated at sign-in | ✅ | `app/auth/oidc.py`, `app/auth/gmail_oauth.py`; `test_gmail_connect.py::test_mismatched_state_is_rejected` |
| Allowlist enforced in-app (in addition to Google testing mode) | ✅ | `test_sessions_csrf.py::test_callback_rejects_account_not_on_allowlist` |
| Every query scoped by `user_id`; other users' resources return the same 404 as missing ones | ✅ | `app/repositories/base.py`; `test_isolation.py` |
| Logs never contain tokens, email bodies, or excerpts | ✅ | `app/logging.py` redaction filter; `tests/unit/test_logging_redaction.py`; `grep -rnE "log\.\w+\(.*(token\|body\|excerpt)" backend/app` finds only fixed message strings |
| Full email bodies never persisted; only sender/subject/date/≤300-char excerpt for recruiting mail | ✅ | `app/pipeline/apply.py::record_message`; data-model.md |
| Email content treated as data only; rendered as escaped text | ✅ | deterministic rules only (no LLM); `prompt-injection-text` fixture; `frontend/tests/DetailAndReview.test.tsx` (HTML in excerpt renders as text) |
| Test-only routes and fixture Gmail absent outside `APP_ENV=test`; test mode refuses a non-`_test` database | ✅ | `tests/unit/test_test_mode_guard.py` |
| `.env` and credential files git-ignored; `.env.example` has placeholders only | ✅ | `.gitignore`; `git check-ignore .env` |
| Production refuses default `SESSION_SECRET` / missing `TOKEN_ENCRYPTION_KEYS` | ✅ | `app/config.py::Settings.validate_runtime` |
