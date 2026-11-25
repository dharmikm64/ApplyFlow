# Data Model: Email-Driven Application Tracker

**Feature**: `001-email-application-tracker` | **Date**: 2026-11-25

PostgreSQL 16 with Alembic migrations. All IDs are UUIDs (`gen_random_uuid()`), and all
timestamps are `timestamptz` (UTC). **Every user-owned table has `user_id NOT NULL` and an
index leading with `user_id`.** Every query in the repository layer filters by the
session user's `user_id` (Constitution III; FR-040). Deleting a user cascades.

```text
users 1─1 recruiting_cycles
users 1─0..1 gmail_connections
users 1─* sessions
users 1─* scan_runs
users 1─* processed_messages
users 1─* applications 1─* application_events *─0..1 processed_messages
users 1─* review_items *─0..1 processed_messages, *─0..* applications (candidates)
```

---

## users

| Field | Type | Rules |
|---|---|---|
| id | uuid PK | |
| google_sub | text UNIQUE NOT NULL | OIDC `sub`; the identity key |
| email | text NOT NULL | from ID token; display only |
| display_name | text | |
| timezone | text NOT NULL default `'UTC'` | IANA name, validated with `zoneinfo` |
| created_at, updated_at | timestamptz | |

## sessions

| Field | Type | Rules |
|---|---|---|
| id_hash | bytea PK | SHA-256 of the cookie value; the raw ID is never stored |
| user_id | uuid FK → users ON DELETE CASCADE | |
| csrf_token | text NOT NULL | random, 32 bytes, url-safe |
| created_at, last_seen_at, expires_at | timestamptz | 14-day sliding expiry |

## gmail_connections (0..1 per user)

| Field | Type | Rules |
|---|---|---|
| user_id | uuid PK, FK → users ON DELETE CASCADE | one per user (FR-004) |
| gmail_address | text NOT NULL | from `users.getProfile` |
| status | enum `connected`, `revoked`, `denied` | `disconnected` = the row is deleted, except `denied`/`revoked` rows kept for UI state |
| refresh_token_ciphertext | bytea NULL | MultiFernet. Set to NULL when status ≠ `connected` |
| granted_scopes | text[] NOT NULL | must contain `gmail.readonly` for `connected` |
| connected_at, updated_at | timestamptz | |
| last_error | text NULL | user-safe code only (`invalid_grant`, `scope_missing`, `access_denied`) |

**Rules**: `status='connected'` ⇔ `refresh_token_ciphertext IS NOT NULL` (CHECK constraint).
Disconnect revokes at Google and then deletes the row (FR-041). If imported data's
`source_gmail_address` ≠ the new `gmail_address`, the connection is refused (spec edge case).

**States**: `(none) → connected` (consent OK) · `(none) → denied` (user cancelled or unticked
the scope) · `connected → revoked` (`invalid_grant` during a job) · `denied|revoked → connected`
(reconnect) · `any → (deleted)` (disconnect).

## recruiting_cycles (1 per user)

| Field | Type | Rules |
|---|---|---|
| user_id | uuid PK, FK → users ON DELETE CASCADE | one active cycle (FR-004) |
| start_date | date NOT NULL | inclusive (FR-006); not in the future |
| timezone | text NOT NULL | copied from the user setting when the date is set; used for boundary math |
| source_gmail_address | text NULL | mailbox the imported data came from; NULL when there is no data |
| covered_from_utc | timestamptz NULL | earliest boundary successfully scanned |
| covered_to_utc | timestamptz NULL | `window_end` of the last successful run = **last successful sync time** |
| updated_at | timestamptz | |

**Start-date change** (FR-043): moving it earlier sets `start_date` and the next sync covers
`[new_start, covered_from)` plus new mail. Moving it later sets `applications.before_cycle =
true` on rows whose evidence events all have `occurred_at < new_start` (nothing is deleted).
`GET /api/cycle/preview-change` returns the counts first.

## scan_runs

| Field | Type | Rules |
|---|---|---|
| id | uuid PK | |
| user_id | uuid FK → users ON DELETE CASCADE | |
| kind | enum `initial`, `sync` | |
| status | enum `queued`, `running`, `succeeded`, `failed` | |
| window_start_utc, window_end_utc | timestamptz NOT NULL | `end` = creation time (FR-007/008) |
| segments | jsonb NOT NULL | ordered list of `{from, to}` ranges to list (e.g. back-fill plus new mail) |
| segment_index | int default 0 | resume cursor |
| page_token | text NULL | resume cursor within the current segment |
| listed, screened, candidates, processed, created_apps, updated_apps, review_items | int default 0 | progress counters |
| estimated_total | int NULL | Gmail `resultSizeEstimate` sum; shown as approximate |
| worker_id | text NULL | |
| heartbeat_at, started_at, finished_at, created_at | timestamptz | |
| failure_code | text NULL | `reconnect_required`, `gmail_unavailable`, `internal_error` |
| attempt | int default 0 | incremented on reclaim; the run fails after 5 attempts |

**Constraints**: partial UNIQUE index `(user_id) WHERE status IN ('queued','running')`
(FR-009). Index `(status, heartbeat_at)` for claiming.

**States**: `queued → running → succeeded | failed`. A `running` run with a heartbeat older than
2 min is reclaimed (`attempt+1`). On `succeeded`, update `recruiting_cycles.covered_*` in the
same transaction. On `failed`, the covered range is unchanged (FR-011).

## processed_messages (the "Email Evidence" entity)

| Field | Type | Rules |
|---|---|---|
| id | uuid PK | |
| user_id | uuid FK → users ON DELETE CASCADE | |
| gmail_message_id | text NOT NULL | |
| gmail_thread_id | text NULL | supporting evidence only (FR-023) |
| internal_date | timestamptz NOT NULL | |
| classification | enum `not_recruiting`, `confirmation`, `progress`, `rejection`, `acknowledgment`, `offer`, `withdrawal`, `job_alert`, `marketing`, `invite_to_apply`, `unclear` | |
| sender | text NULL | NULL for `not_recruiting` |
| subject | text NULL | NULL for `not_recruiting` |
| excerpt | text NULL | ≤ 300 chars; NULL for `not_recruiting` (FR-044) |
| extracted | jsonb NULL | `{company, position, req_id, stated_applied_date, confidence}` |
| rule_id | text NULL | which rule or parser fired |
| dismissed | bool default false | set when the owning application is dismissed (FR-038a) |
| processed_at | timestamptz | |

**Constraints**: UNIQUE `(user_id, gmail_message_id)`. This is the idempotency key: an
existing row means the message is skipped on re-scan (FR-010).

## applications

| Field | Type | Rules |
|---|---|---|
| id | uuid PK | |
| user_id | uuid FK → users ON DELETE CASCADE | |
| company | text NULL | displayed "Unknown" when NULL (FR-020) |
| company_norm | text NULL | matching key (R10) |
| position | text NULL | |
| position_norm | text NULL | |
| req_id | text NULL | |
| status | enum `submitted`, `in_progress`, `rejected` NOT NULL | display: Submitted / In progress / Rejected (FR-027) |
| date_applied | date NULL | |
| date_applied_source | enum `stated`, `estimated`, `unknown`, `user` NOT NULL | |
| overridden_fields | text[] default `{}` | subset of `company, position, date_applied, status` (FR-036) |
| before_cycle | bool default false | FR-043 |
| dismissed_at | timestamptz NULL | non-NULL = "Not an application" (FR-038a); hidden from the main table |
| created_at, updated_at | timestamptz | |

**Indexes**: `(user_id, company_norm)`, `(user_id, req_id)`, `(user_id, dismissed_at)`.
Search uses `ILIKE` on `company`/`position`, scoped by `user_id`.

**Derived values**: `status`, `date_applied`, and `date_applied_source` are recomputed by
`derive()` (R11) from events after each change, except for fields in `overridden_fields`.

## application_events

| Field | Type | Rules |
|---|---|---|
| id | uuid PK | |
| user_id | uuid FK → users ON DELETE CASCADE | |
| application_id | uuid FK → applications ON DELETE CASCADE | |
| kind | enum `confirmation`, `progress`, `rejection`, `acknowledgment`, `offer`, `withdrawal`, `manual_edit`, `dismissed`, `restored`, `review_resolved` | |
| occurred_at | timestamptz NOT NULL | email `internalDate` or the time of the user action |
| message_id | uuid FK → processed_messages NULL | NULL for user actions |
| detail | jsonb NULL | e.g. `{field, from, to}` for `manual_edit` |
| created_at | timestamptz | |

**Constraints**: UNIQUE `(application_id, message_id) WHERE message_id IS NOT NULL`
(idempotent attach).

## review_items

| Field | Type | Rules |
|---|---|---|
| id | uuid PK | |
| user_id | uuid FK → users ON DELETE CASCADE | |
| type | enum `possible_application`, `ambiguous_match`, `offer_or_withdrawal`, `contradictory_update`, `manual_conflict`, `missing_field` | |
| message_id | uuid FK → processed_messages NULL | |
| application_id | uuid FK → applications ON DELETE CASCADE NULL | the subject application, if any |
| candidate_application_ids | uuid[] default `{}` | for `ambiguous_match` |
| suggestion | jsonb NOT NULL | e.g. `{action: "create", company, position, status}` or `{field, value}` |
| explanation | text NOT NULL | user-facing reason |
| state | enum `pending`, `resolved`, `dismissed` | |
| resolution | jsonb NULL | what the user chose |
| dedupe_key | text NOT NULL | `type:message_id[:application_id][:field]` |
| created_at, resolved_at | timestamptz | |

**Constraints**: UNIQUE `(user_id, dedupe_key)`. A resolved or dismissed item is never
recreated (FR-038).

**Resolutions** (FR-037): `create` (new application from the suggestion; the message becomes its
evidence) · `attach` (to a chosen application from `candidate_application_ids` or any of the
user's applications) · `apply` (accept the suggested field or status change) · `dismiss`.

---

## Validation rules (summary)

- The status enum is exactly three values. The API rejects anything else (FR-027/035).
- A manual edit of `date_applied` sets `date_applied_source='user'` and adds the field to
  `overridden_fields`.
- `start_date` ≤ today in the user's time zone. `timezone` must be a valid IANA name.
- Every repository method takes `user_id` as a required argument. There are no
  unscoped finders, and this is enforced by tests (SC-006).
- "Delete imported data" (FR-042) deletes the user's `applications`, `application_events`,
  `review_items`, `processed_messages`, and `scan_runs`, and resets the `recruiting_cycles`
  coverage and `source_gmail_address`. It keeps `users`, `sessions`, `gmail_connections`, and
  `start_date`.
