# Contract: Gmail Client Interface and Synthetic Fixtures

**Feature**: `001-email-application-tracker`

## GmailClient interface (backend/app/gmail/client.py)

The pipeline depends only on this protocol. `GoogleGmailClient` (real HTTP) is used in
development and production. `FixtureGmailClient` exists only in tests and `APP_ENV=test`.

```python
class GmailClient(Protocol):
    def get_profile(self) -> Profile: ...                       # emailAddress
    def list_message_ids(self, query: str, page_token: str | None,
                         max_results: int = 500) -> ListPage: ...  # ids, next_page_token, result_size_estimate
    def get_metadata(self, message_id: str) -> MessageMeta: ...  # id, thread_id, internal_date, label_ids,
                                                                 # snippet, headers{From,Subject,Date,
                                                                 # List-Unsubscribe,Reply-To}
    def get_full(self, message_id: str) -> MessageFull: ...      # MessageMeta + decoded text/plain and
                                                                 # text/html parts (in memory only)
```

Errors are raised as `GmailAuthError` (invalid_grant or revoked → reconnect),
`GmailRateLimited` (429/403 rateLimitExceeded → retry), and `GmailUnavailable` (5xx or timeout →
retry, then fail).

`FixtureGmailClient` must apply the same `after:`/`before:` epoch filtering semantics, the
Spam/Trash exclusion (messages with `SPAM`/`TRASH` labels are never listed), and paging
(configurable small page size in tests to exercise resume).

## Fixture message format

`backend/tests/fixtures/gmail/<id>.json`, the same shape as Gmail `users.messages.get` with
`format=full`:

```json
{
  "id": "fx-acme-swe-confirm",
  "threadId": "th-acme-1",
  "internalDate": "1757001600000",
  "labelIds": ["INBOX"],
  "snippet": "Thank you for applying to Acme Robotics for the Software Engineer role...",
  "payload": {
    "mimeType": "multipart/alternative",
    "headers": [
      {"name": "From", "value": "Acme Robotics <no-reply@us.greenhouse-mail.io>"},
      {"name": "Subject", "value": "Thank you for applying to Acme Robotics"},
      {"name": "Date", "value": "Thu, 4 Sep 2026 16:00:00 +0000"}
    ],
    "parts": [
      {"mimeType": "text/plain", "body": {"data": "<base64url>"}},
      {"mimeType": "text/html", "body": {"data": "<base64url>"}}
    ]
  }
}
```

Rules: companies, people, addresses, and IDs are **fictional** (use `.example`, `.test`, or
clearly invented names on real ATS sender domains only where needed to exercise parsers). No real
personal data.

## Mailbox scenarios

`backend/tests/fixtures/mailboxes/<name>.yaml` lists message IDs plus the expected outcome. The
same file drives integration tests and E2E.

```yaml
name: core-journey
timezone: America/New_York
start_date: 2026-09-01
messages: [fx-acme-swe-confirm, fx-acme-swe-interview, fx-acme-swe-reject,
           fx-acme-pm-confirm, fx-globex-reject-only, fx-jobalert-1, fx-ad-1,
           fx-initech-offer, fx-before-start-boundary, fx-at-start-boundary, fx-spam-confirm]
expected:
  applications:
    - {company: Acme Robotics, position: Software Engineer, status: rejected,
       date_applied: 2026-09-04, date_source: estimated}
    - {company: Acme Robotics, position: Product Manager, status: submitted}
    - {company: Globex, position: Data Analyst, status: rejected, date_applied: null}
  review_items: [{type: offer_or_withdrawal, message: fx-initech-offer}]
  ignored: [fx-jobalert-1, fx-ad-1, fx-before-start-boundary, fx-spam-confirm]
```

Required scenario coverage (each maps to a spec acceptance scenario or edge case):
`core-journey`, `same-company-two-positions`, `rescan-idempotent`, `ads-and-alerts`,
`rejection-only`, `stated-vs-estimated-date`, `out-of-order-confirmation`,
`ack-after-interview`, `progress-after-rejection`, `shared-thread-two-positions`,
`req-id-split`, `reapply-after-rejection`, `ambiguous-company-only`, `ats-platform-company`,
`generic-subject-recruiting` (recall guard), `prompt-injection-text`, `tz-boundaries`
(UTC−, UTC+, DST), `two-users-isolation`, `manual-correction-then-sync`, `dismiss-then-sync`,
`revoked-mid-scan`, `crash-mid-page-resume`.
