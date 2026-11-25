# HTTP API Contract

**Feature**: `001-email-application-tracker`

Same-origin JSON API served by FastAPI. FastAPI also generates the OpenAPI document at
`/api/openapi.json`, which is the machine-readable source of truth once implemented.

**Conventions**

- Auth: `af_session` cookie. Unauthenticated → `401 {"error":"unauthenticated"}`.
- State-changing requests (`POST`/`PATCH`/`PUT`/`DELETE` under `/api`) require header
  `X-CSRF-Token`. A missing or wrong token → `403 {"error":"csrf"}`.
- Another user's resource, or a nonexistent one → `404 {"error":"not_found"}` (identical
  responses; FR-040).
- Errors: `{"error": "<code>", "message": "<user-safe text>"}`. Responses never include tokens,
  email bodies, or internal exceptions.
- Dates are `YYYY-MM-DD`. Timestamps are ISO-8601 UTC. Status values are `submitted` |
  `in_progress` | `rejected`, labeled in the UI as Submitted / In progress / Rejected.

---

## Browser redirect routes (not JSON)

| Route | Purpose |
|---|---|
| `GET /auth/login` | Starts Google OIDC sign-in (scopes `openid email profile`, PKCE, state, nonce). |
| `GET /auth/callback` | Validates state, nonce, and ID token, upserts the user by `sub`, rotates the session, redirects to `/`. Not allowlisted → `/?error=not_allowed`. |
| `POST /auth/logout` | CSRF-protected. Deletes the session and clears the cookie. |
| `GET /auth/gmail/connect` | Requires a session. Starts the Gmail consent flow (`gmail.readonly`, offline, `prompt=consent`, PKCE, state, `login_hint`). |
| `GET /auth/gmail/callback` | Requires the same session and a valid state. On success it stores the encrypted refresh token and redirects `/?gmail=connected`. On deny or unticked scope it records `denied` and redirects `/?gmail=denied`. On a different mailbox while data exists it redirects `/?gmail=mailbox_mismatch` and stores nothing. |

## JSON endpoints

### Session and settings

`GET /api/me` → `200`

```json
{
  "user": {"email": "string", "displayName": "string", "timezone": "America/New_York"},
  "csrfToken": "string",
  "gmail": {"status": "not_connected|connected|denied|revoked", "address": "string|null"},
  "cycle": {"startDate": "2026-09-01|null", "timezone": "string|null",
            "lastSuccessfulSyncAt": "timestamp|null"}
}
```

`PATCH /api/me` `{ "timezone": "Europe/London" }` → `200` (same shape). `422` for an invalid
IANA name.

### Gmail connection

`DELETE /api/gmail` → `204`. Revokes at Google, deletes stored tokens (FR-041), and keeps
imported data.

### Recruiting cycle

`PUT /api/cycle` `{ "startDate": "2026-09-01", "timezone": "America/New_York" }` → `200`
`cycle` object. When imported data exists and the date changes, the request must include
`"confirm": true` after the preview, otherwise → `409 {"error":"confirm_required"}`.

`GET /api/cycle/preview-change?startDate=YYYY-MM-DD` → `200`

```json
{"direction": "earlier|later|same", "rowsMarkedBeforeCycle": 3,
 "rowsDeleted": 0, "willScanAddedPeriod": true, "message": "string"}
```

### Scans

`POST /api/scans` `{ "kind": "initial|sync" }` → `202` run. `409 {"error":"scan_in_progress"}`
if one is active (FR-009). `409 {"error":"no_start_date"}` or `409
{"error":"gmail_not_connected"}` when not ready.

`GET /api/scans/current` → `200` latest run, or `204` if none ever ran.

```json
{"id": "uuid", "kind": "initial|sync", "status": "queued|running|succeeded|failed",
 "windowStart": "ts", "windowEnd": "ts",
 "progress": {"listed": 0, "estimatedTotal": 0, "screened": 0, "candidates": 0,
              "processed": 0},
 "results": {"createdApps": 0, "updatedApps": 0, "reviewItems": 0},
 "failureCode": "reconnect_required|gmail_unavailable|internal_error|null",
 "startedAt": "ts|null", "finishedAt": "ts|null"}
```

The client polls every 2 s while the run is `queued` or `running` (FR-009, SC-002).

### Applications

`GET /api/applications?q=&status=submitted&status=in_progress&sort=date_applied&order=desc&view=active|dismissed`
→ `200`

```json
{"items": [{"id": "uuid", "company": "string|null", "position": "string|null",
            "dateApplied": "YYYY-MM-DD|null",
            "dateAppliedSource": "stated|estimated|unknown|user",
            "status": "submitted|in_progress|rejected",
            "beforeCycle": false, "pendingReview": true}],
 "total": 0}
```

`q` is a case-insensitive substring match on company or position. Unknown dates always sort last
(FR-031).

`GET /api/applications/{id}` → `200`

```json
{"application": {"...": "list item fields", "reqId": "string|null",
                 "overriddenFields": ["company"], "dismissedAt": "ts|null"},
 "dateAppliedExplanation": "Estimated from the confirmation email received 2026-09-03.",
 "events": [{"id": "uuid", "kind": "confirmation", "occurredAt": "ts",
             "evidence": {"sender": "string", "subject": "string", "date": "ts",
                          "excerpt": "string"} ,
             "detail": {}}],
 "reviewItems": [{"id": "uuid", "type": "string", "explanation": "string"}]}
```

`PATCH /api/applications/{id}`
`{ "company"?: "string", "position"?: "string", "dateApplied"?: "YYYY-MM-DD|null", "status"?: "submitted|in_progress|rejected" }`
→ `200` detail. Each changed field is added to `overriddenFields` and recorded as a `manual_edit`
event (FR-035/036). Any other status value → `422`.

`POST /api/applications/{id}/dismiss` → `200` ("Not an application", FR-038a).
`POST /api/applications/{id}/restore` → `200`.

### Review area

`GET /api/review-items?state=pending` → `200`

```json
{"items": [{"id": "uuid", "type": "possible_application|ambiguous_match|offer_or_withdrawal|contradictory_update|manual_conflict|missing_field",
            "explanation": "string",
            "evidence": {"sender": "string", "subject": "string", "date": "ts", "excerpt": "string"},
            "application": {"id": "uuid", "company": "string", "position": "string"} ,
            "candidates": [{"id": "uuid", "company": "string", "position": "string"}],
            "suggestion": {}}],
 "pendingCount": 0}
```

`POST /api/review-items/{id}/resolve`
`{ "action": "create|attach|apply|dismiss", "applicationId"?: "uuid", "fields"?: {"company":"", "position":""} }`
→ `200`. `409` if the item has already been resolved.

### Data controls

`DELETE /api/data` `{ "confirm": "DELETE" }` → `204`. Deletes all imported data (FR-042). The
Gmail connection and start date are kept. `409` while a scan is running.

## Test-only routes (`APP_ENV=test` only; not registered otherwise)

| Route | Purpose |
|---|---|
| `POST /test/login` `{ "sub": "...", "email": "..." }` | Creates a session for a synthetic user. |
| `POST /test/gmail/connect` `{ "mailbox": "<fixture name>" }` | Connects the user to a fixture mailbox. |
| `POST /test/gmail/append` `{ "mailbox": "...", "messages": ["<fixture id>"] }` | Adds fixture messages to simulate new mail before "Sync now". |
| `POST /test/gmail/revoke` | Makes the next fixture call return `invalid_grant`. |
