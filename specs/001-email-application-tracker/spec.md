# Feature Specification: Email-Driven Application Tracker

**Feature Branch**: `001-email-application-tracker`

**Created**: 2026-11-25

**Status**: Draft

**Input**: User description: "Build ApplyFlow, a web application for people who struggle to track
applications during a recruiting cycle. Turn recruiting emails into a persistent, accurate
application table without requiring users to enter every application manually." (full
description: sign in with Google, connect Gmail read-only, pick a recruiting start date, scan
emails, see a saved dashboard with Company / Position / Date Applied / Application Status,
sync on demand, review and correct results, disconnect Gmail and delete data.)

## Clarifications

### Session 2026-11-25

- Q: How should ApplyFlow classify emails and extract company, position, and dates? → A: Rules
  only (sender/subject filtering, phrase matching, text patterns); no language model and no
  third-party processing of email content. Uncertain results go to review.
- Q: Can users add an application to the table by hand? → A: No. Rows come only from email
  evidence or from accepting a review item; missed applications stay missing in the MVP.
- Q: Who should be able to sign in to the MVP? → A: Local only, at no cost. ApplyFlow runs on
  the developer's machine, with Google sign-in in testing mode and only the developer's own
  Gmail allowlisted. It must remain deployable online later (allowlisted test users, free tiers)
  without redesign.
- Q: How should a user get rid of a row that isn't a real application? → A: Mark it "Not an
  application". The row leaves the table, its emails stay dismissed on later syncs, and it can be
  restored from a dismissed list.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Connect Gmail and build the application table (Priority: P1)

A job seeker signs into ApplyFlow with Google. ApplyFlow explains in plain language what it will
read, what it will store, and that it can never send, delete, or change emails. The user approves
read-only Gmail access, picks the start date of their recruiting cycle, and clicks "Scan emails."
A progress indicator shows the scan advancing. When it finishes, the dashboard lists one row per
application found, with Company, Position, Date Applied, and Application Status.

**Why this priority**: This is the whole product promise. Without it there is nothing to view,
correct, or sync.

**Independent Test**: Sign in with a test account whose mailbox holds a known set of synthetic
recruiting emails, connect it, choose a start date, and scan. Check that the table contains
exactly the expected applications with the expected values.

**Acceptance Scenarios**:

1. **Given** a signed-in user who has not connected Gmail, **When** they open the connect step,
   **Then** they see an explanation of what will be read (sender, subject, date, and message
   text of emails in the chosen date range), what will be stored (extracted application details
   and short supporting excerpts), that access is read-only, and that email content is analyzed
   only within ApplyFlow and never shared with third parties, before Google's consent screen
   appears.
2. **Given** a connected user who has chosen a start date, **When** they click "Scan emails,"
   **Then** a progress indicator appears, and when the scan finishes the dashboard shows the
   applications that were found plus the time of the last successful sync.
3. **Given** a mailbox with a confirmation, an interview invitation, and a rejection for the same
   position, **When** the scan finishes, **Then** exactly one row exists for that position and
   its status is Rejected.
4. **Given** a mailbox with confirmations for two different positions at the same company,
   **When** the scan finishes, **Then** two separate rows exist.
5. **Given** a mailbox containing an unrelated job advertisement, a job alert, and an invitation
   to apply, **When** the scan finishes, **Then** none of them creates an application.
6. **Given** a mailbox with a rejection email but no confirmation for that position, **When** the
   scan finishes, **Then** the row shows status Rejected and Date Applied as unknown.
7. **Given** a confirmation email that states an explicit application date, **When** the scan
   finishes, **Then** Date Applied equals the stated date. **Given** a confirmation without a
   stated date, **Then** Date Applied equals the email's date, and the detail view marks it as
   an estimate and explains why.
8. **Given** a scan that finds no recognizable recruiting emails, **When** it finishes, **Then**
   the dashboard shows an empty state explaining that only applications with recognizable email
   evidence can be imported.
9. **Given** the completed scan results, **When** the user views the dashboard, **Then** nothing
   on the screen claims that every application was found.

---

### User Story 2 - Return later and sync updates (Priority: P1)

The user signs out, comes back days later, signs in, and finds the same table. They click
"Sync now." ApplyFlow checks for new emails since the last successful sync and updates the
existing rows (for example, Submitted → In progress after an interview invitation) without
creating duplicates.

**Why this priority**: A tracker that is lost on sign-out, or that duplicates rows on every sync,
is worse than a spreadsheet. Persistence and idempotent syncing are core to the promise.

**Independent Test**: Complete a scan, sign out, sign back in, and check that the table is
identical. Add a new synthetic interview email, click "Sync now," and check that the matching
row's status changes and that no row is duplicated.

**Acceptance Scenarios**:

1. **Given** a user with a saved table, **When** they sign out and sign back in, **Then** the same
   rows, values, start date, and last successful sync time are shown.
2. **Given** a completed scan, **When** the same scan runs again with no new emails, **Then** the
   number of rows and events is unchanged.
3. **Given** an existing Submitted row, **When** a sync finds an interview invitation for that
   application, **Then** the row's status becomes In progress and the email is added to its
   event history.
4. **Given** a row whose status is Rejected, **When** a sync finds an older confirmation for that
   application, **Then** the status stays Rejected and the confirmation is added to the history.
5. **Given** a row whose status is In progress, **When** a later generic acknowledgment ("we
   received your message") arrives, **Then** the status stays In progress.
6. **Given** a sync in progress, **When** the user views the dashboard, **Then** they see the
   sync's progress and cannot start a second scan or sync at the same time.

---

### User Story 3 - Review evidence and correct results (Priority: P2)

The user clicks a row to see why ApplyFlow believes what it shows: the supporting emails (sender,
subject, date, short excerpt), the event history in date order, and how Date Applied was
derived. They fix a wrong company name or status. Uncertain findings (possible applications,
ambiguous matches, offers, withdrawals, contradictory updates) appear in a separate review area,
where the user can accept, assign, or dismiss each one.

**Why this priority**: Automated extraction will sometimes be wrong or unsure. Showing the
evidence and allowing corrections keeps the table trustworthy, but the table already delivers
value without this.

**Independent Test**: Scan synthetic fixtures that include an offer email, an ambiguous match,
and a misread company name. Check that the first two appear in the review area and not as table
statuses, correct the company name, run a sync, and check that the correction persists.

**Acceptance Scenarios**:

1. **Given** a row, **When** the user clicks it, **Then** a detail view shows each supporting
   email's sender, subject, date, and relevant excerpt, the dated event history, and the source
   of Date Applied (stated in email, estimated from confirmation date, unknown, or set by the
   user).
2. **Given** a detail view, **When** the user edits company, position, Date Applied, or status and
   saves, **Then** the table shows the new values and the history records the manual change.
3. **Given** a manually corrected field, **When** a later sync finds evidence that conflicts with
   it, **Then** the corrected value is kept and the conflicting evidence appears in the review
   area.
4. **Given** an offer or withdrawal email for a known application, **When** a scan processes it,
   **Then** the row's status is not changed and a review item explains that the email does not
   fit Submitted / In progress / Rejected.
5. **Given** an email that could belong to more than one existing application (for example, same
   company, no position or requisition ID), **When** a scan processes it, **Then** it is not
   merged automatically and appears in the review area with the candidate applications.
6. **Given** contradictory updates (for example, an interview invitation dated after a
   rejection), **When** a scan processes them, **Then** a review item is created instead of
   silently picking one.
7. **Given** a review item, **When** the user resolves it (create a new application, attach it to
   a chosen application, apply its suggested status, or dismiss it), **Then** the table updates
   accordingly and the item does not reappear on later syncs.
8. **Given** a row created from a misrecognized email, **When** the user marks it "Not an
   application," **Then** it disappears from the table, does not return after the next sync,
   and can be restored from the Dismissed view.
9. **Given** review items exist, **When** the user views the dashboard, **Then** the review area
   shows how many are pending, and Application Status still has only the three allowed values.

---

### User Story 4 - Find applications quickly (Priority: P2)

The user searches by company or position, filters by status, and sorts by Date Applied to see
where they stand.

**Why this priority**: Useful once the table has more than a handful of rows, but not required
for the core workflow.

**Independent Test**: With a table of known rows, apply each search, filter, and sort, and check
the visible rows and their order.

**Acceptance Scenarios**:

1. **Given** a table of applications, **When** the user types part of a company or position name,
   **Then** only rows whose company or position contains that text (case-insensitive) are shown.
2. **Given** a table, **When** the user filters by one or more statuses, **Then** only rows with
   those statuses are shown.
3. **Given** a table, **When** the user sorts by Date Applied ascending or descending, **Then**
   rows are ordered by date and rows with unknown dates appear after all dated rows.
4. **Given** search and filter combined with no matches, **When** applied, **Then** a "no
   matching applications" message appears with a way to clear the filters.

---

### User Story 5 - Control access and data (Priority: P2)

The user can disconnect Gmail, which immediately stops access and removes stored Gmail
credentials, while keeping their table. Separately, they can delete all imported data, or delete
their whole ApplyFlow account. If they
change the recruiting start date, ApplyFlow explains the effect on existing rows before applying
it. If Gmail access is denied or revoked, the app shows a clear way to reconnect.

**Why this priority**: Required for privacy and trust, and required by the project constitution,
but it is not on the main happy path.

**Independent Test**: Disconnect and check that the table remains, syncing is unavailable, and
the stored credentials are gone. Delete imported data and check that the table is empty. Revoke
access from the Google account and check that "Sync now" leads to a reconnect state.

**Acceptance Scenarios**:

1. **Given** a connected user, **When** they disconnect Gmail and confirm, **Then** Gmail access is
   revoked, stored Gmail credentials are deleted, the table remains visible, and scanning or
   syncing is unavailable until they reconnect.
2. **Given** a user with imported data, **When** they choose "Delete imported data" and confirm,
   **Then** all applications, events, evidence, and review items are permanently removed, and
   the Gmail connection is left as it was.
3. **Given** a user who declines Gmail consent, **When** they return to ApplyFlow, **Then** they
   see that access was not granted, what that means, and a button to try again.
4. **Given** a user whose Gmail access was revoked outside ApplyFlow, **When** they click "Sync
   now," **Then** the sync stops without losing existing rows, and the dashboard shows a
   reconnect state.
5. **Given** a user with existing rows, **When** they move the start date earlier, **Then** they
   are told that the next sync will also scan the added earlier period and that existing rows
   are kept. **When** they move it later, **Then** they are told that existing rows are kept
   (none are deleted) and that rows whose evidence is all before the new date will be labeled
   "before current cycle," which they can delete if they choose.
6. **Given** two different users, **When** one tries to view, edit, or resolve the other's
   applications or review items by any means, **Then** the attempt is refused and reveals
   nothing about whether the records exist.
7. **Given** a signed-in user, **When** they choose "Delete account" and confirm, **Then** Gmail
   access is revoked, every record belonging to them (account, sessions, connection, start date,
   applications, events, evidence, review items, scan history) is permanently removed, and
   they are signed out. Signing in again starts as a brand-new user.
8. **Given** a connected user with a scan running, **When** they disconnect Gmail, **Then** the
   scan stops before reading any further email, keeps the rows saved so far, and makes no
   further Gmail requests.

---

### Edge Cases

- **Start-date boundary**: an email received at 00:00 on the start date in the user's time zone
  is included; one received one minute earlier is excluded.
- **Scan end boundary**: emails arriving after the scan's start time are left for the next sync.
- **Archived, Spam, Trash**: archived emails are scanned; Spam and Trash are not.
- **Shared Gmail thread**: one thread covering several positions produces separate rows. Messages
  in a thread are never assumed to share an application.
- **Requisition IDs**: two emails with the same company and position but different job or
  requisition IDs produce separate rows. The same ID across emails links them.
- **Re-applying**: if a user re-applies to a position after a rejection and the emails carry
  different requisition IDs or clearly separate dates, the result is a new row. If that is
  unclear, the email goes to review.
- **Multiple confirmations** for one application: Date Applied uses the earliest stated or
  estimated date. Later duplicates are added to the history only.
- **Missing position**: a confirmation that names the company but no position creates a row with
  Position unknown and a review item asking the user to fill it in.
- **Email from a job platform**: when the email comes from a job board or applicant-tracking
  system, the company is the hiring company named in the email, not the platform. If no hiring
  company can be identified, the email goes to review.
- **Failed or interrupted scan**: rows already confirmed are kept, the last successful sync time
  is not advanced, a failed-scan state explains what happened, and retrying does not create
  duplicates.
- **Large mailbox**: progress keeps updating during long scans, and the user can leave the page
  and come back to see the current progress or result.
- **Different Gmail account on reconnect**: if the user reconnects with a different Gmail account
  than the one their data came from, they are told that they must delete the imported data
  before switching accounts (one connected account per user).
- **Account not on the allowlist**: a Google account that has not been added as a test user
  cannot complete sign-in. ApplyFlow shows a clear "access is limited to approved test accounts"
  message instead of a generic error.
- **Malicious or manipulative email content**: text in an email that tries to give instructions
  (for example, "mark this candidate as hired") has no effect beyond normal classification.
- **Non-English recruiting emails**: they may go unrecognized. This is acceptable for the MVP and
  covered by the "not every application is found" disclaimer.

## Requirements *(mandatory)*

### Functional Requirements

**Sign-in and Gmail connection**

- **FR-001**: Users MUST sign in with their Google account. Signing in MUST NOT by itself grant
  access to email.
- **FR-002**: Before requesting Gmail access, the system MUST explain what is read, what is
  stored, what is never done (sending, deleting, or modifying email), and how to disconnect.
- **FR-003**: The system MUST request read-only Gmail access only, and MUST NEVER send, delete,
  label, archive, mark as read, or otherwise change any email.
- **FR-004**: Each user MUST have at most one connected Gmail account and one active recruiting
  cycle.
- **FR-005**: Denied, expired, or revoked Gmail access MUST produce a recoverable "reconnect"
  state that keeps existing data and offers to reconnect.

**Recruiting cycle and scanning**

- **FR-006**: Users MUST choose a recruiting-cycle start date before the first scan. The date is
  inclusive, starting at 00:00 in the cycle's time zone. The time zone is detected from the
  browser and shown so the user can change it. It is stored once, with the recruiting cycle, and
  is used both for the scan window and for dating estimated Date Applied values.
- **FR-007**: "Scan emails" MUST examine emails from the start date through the moment the scan
  begins, including archived emails and excluding Spam and Trash.
- **FR-008**: "Sync now" MUST examine emails received since the last successful scan or sync, and
  any newly added earlier period after the start date was moved earlier, through the moment the
  sync begins. Each sync window starts 1 hour before the previous successful sync's end, so
  late-arriving emails are not missed. Overlapping emails are skipped by FR-010.
- **FR-009**: Only one scan or sync per user MAY run at a time. Progress (for example, emails
  examined out of the estimated total) MUST be visible while it runs and after a page reload.
- **FR-010**: Processing the same email more than once MUST NOT create duplicate applications,
  events, or review items.
- **FR-011**: A failed or interrupted scan MUST keep previously saved results, MUST NOT advance
  the last successful sync time, and MUST show a failed-scan state with a retry option.
- **FR-012**: Scanning happens only when the user starts it. Scheduled background syncing is out
  of scope.

**Classification**

- **FR-013**: An email confirming that an application was received MUST be classified as a
  Submitted event.
- **FR-014**: An email about an assessment, interview, screening, or explicit advancement for an
  application MUST be classified as an In progress event.
- **FR-015**: An email explicitly stating that the candidate will not proceed MUST be classified
  as a Rejected event.
- **FR-016**: Job alerts, marketing, newsletters, and invitations to apply MUST NOT create
  applications or events.
- **FR-017**: Offer and withdrawal emails MUST NOT change an application's status. They MUST
  create a review item explaining why.
- **FR-018**: Emails the system cannot classify confidently MUST go to the review area rather
  than the table.
- **FR-019**: Email content MUST be treated only as data to classify. Instructions inside emails
  MUST have no effect on system behavior.
- **FR-020**: The system MUST NEVER invent a company, position, date, or status. Values not
  supported by evidence MUST be shown as unknown.
- **FR-020a**: Classification and extraction MUST be deterministic and rule-based (sender and
  subject filtering, phrase matching, text patterns): the same email always yields the same
  result. No language model is used, and email content MUST NOT be sent to any third-party
  service for analysis.

**Application identity**

- **FR-021**: Each row MUST represent one application (one candidate's application to one
  position at one company), not one email.
- **FR-022**: Emails about the same application MUST update the same row. Applications for
  different positions at the same company MUST stay separate rows.
- **FR-023**: Matching MUST use job or requisition IDs when available, together with company,
  position, sender, and dates. Gmail thread membership alone MUST NOT be treated as proof that
  messages share an application.
- **FR-024**: When an email plausibly matches more than one application, or it is unclear whether
  it belongs to an existing application, it MUST NOT be merged automatically. It MUST go to the
  review area with the candidate matches.

**Dates and status**

- **FR-025**: Date Applied MUST be the application date stated in an email when one is present.
  Otherwise it MUST be the date of the earliest confirmation email, marked as an estimate with an
  explanation in the detail view.
- **FR-026**: If an application has only progress or rejection emails, Date Applied MUST be
  unknown. Those emails' dates MUST NOT be used as the application date.
- **FR-027**: Application Status MUST be exactly one of: Submitted, In progress, Rejected.
- **FR-028**: Status MUST follow the chronology (email dates) and meaning of events, regardless
  of the order in which emails are processed. A Submitted event MUST NOT replace In progress or
  Rejected. A generic acknowledgment MUST NOT replace In progress.
- **FR-029**: Contradictory or unclear updates (for example, an advancement dated after a
  rejection) MUST create a review item, and the status MUST stay at its current value until the
  user resolves it.

**Dashboard**

- **FR-030**: The main table MUST show exactly four data columns: Company, Position, Date Applied,
  and Application Status.
- **FR-031**: Users MUST be able to search by company or position (case-insensitive substring),
  filter by one or more statuses, and sort by Date Applied in both directions, with unknown dates
  sorted last.
- **FR-032**: The dashboard MUST show the last successful sync time, scan progress while running,
  and distinct loading, empty (no scan yet), empty (scan found nothing), failed-scan, and
  reconnect states.
- **FR-033**: The dashboard MUST state that only applications with available, recognizable email
  evidence can be imported, and MUST NOT claim that all applications were found.

**Review and corrections**

- **FR-034**: Selecting a row MUST open a detail view with each supporting email (sender,
  subject, date, short excerpt), the event history in chronological order, and the source of Date
  Applied.
- **FR-035**: Users MUST be able to edit company, position, Date Applied, and status. Status edits
  are limited to the three allowed values, and every edit MUST be recorded in the history.
- **FR-036**: Manual corrections MUST be preserved across scans and syncs. New evidence that
  conflicts with a manual correction MUST create a review item instead of overwriting it.
- **FR-037**: Uncertain results MUST appear in a review area separate from the main table, with
  a pending count. Users MUST be able to create an application from an item, attach it to a
  chosen application, apply its suggested change, or dismiss it.
- **FR-038**: Resolved or dismissed review items MUST NOT reappear on later scans or syncs of the
  same emails.
- **FR-038a**: Users MUST be able to mark a row "Not an application". The row is removed from the
  main table, its supporting emails are remembered as dismissed so later scans and syncs do not
  recreate it, and the action is recorded in its history. Dismissed rows MUST be listed in a
  "Dismissed" view, from which the user can restore them to the table unchanged.

**Privacy, persistence, and account controls**

- **FR-039**: The system MUST persist each user's start date, time zone, applications, events,
  supporting evidence, corrections, review items, and last successful sync time across sessions.
- **FR-040**: Each user's emails, credentials, applications, evidence, and review items MUST be
  accessible only to that user. Attempts to access another user's records MUST be refused
  without revealing whether those records exist.
- **FR-041**: Users MUST be able to disconnect Gmail, which revokes access and deletes stored
  Gmail credentials but keeps imported data. Disconnecting cancels any queued or running scan,
  and no Gmail request is made after the disconnect completes.
- **FR-042**: Users MUST be able to delete all imported data (applications, events, evidence,
  review items) separately from disconnecting, after an explicit confirmation.
- **FR-042a**: Users MUST be able to delete their ApplyFlow account after an explicit
  confirmation. This revokes Gmail access and permanently removes every record belonging to the
  user (account, sessions, Gmail connection, recruiting cycle, scan runs, and all imported data),
  then signs them out.
- **FR-043**: Changing the start date MUST show its effect on existing rows before it is applied,
  and MUST NEVER delete records automatically. Rows whose evidence is entirely before a new later
  start date MUST be labeled "before current cycle" and kept until the user deletes them.
- **FR-044**: The system MUST store only the email information needed for the tracker (message
  identifiers, sender, subject, date, and short evidence excerpts). Full email bodies MUST NOT be
  stored.
- **FR-045**: Stored Gmail credentials MUST be kept server-side, protected at rest, and never
  exposed to the browser. Credentials and email content MUST NOT appear in logs.

**Out of scope (MVP)**

- **FR-046**: The MVP MUST NOT include resume tools, auto-applying, sending email, billing,
  scheduled syncing, multiple Gmail accounts or cycles per user, email providers other than
  Gmail, or manually creating applications. Every application MUST originate from email
  evidence, either directly or by the user accepting a review item.

### Key Entities

- **User**: A person signed in with Google. Has one recruiting cycle and at most one Gmail
  connection. Owns all other records.
- **Gmail Connection**: The user's read-only Gmail authorization. Includes the connected address,
  connection status (connected, denied, revoked, or disconnected, where expired access is
  treated as revoked), and protected credentials. Credentials are removed on disconnect.
- **Recruiting Cycle**: The user's active cycle. Includes the inclusive start date, the user's
  time zone (the only stored time zone), and the covered date range.
- **Scan Run**: One "Scan emails" or "Sync now" execution. Includes type, time window, status
  (running, succeeded, failed), progress counts, start and finish times, and a user-safe failure
  reason. The last succeeded run gives the last successful sync time.
- **Application**: One application to one position at one company. Includes company, position,
  optional job/requisition ID, Date Applied with its source (stated, estimated, unknown, or set
  by user), current status (Submitted, In progress, Rejected), which fields were manually
  corrected, an optional "before current cycle" label, and whether it is dismissed as "Not an
  application".
- **Application Event**: A dated occurrence in an application's history, such as a confirmation,
  progress update, rejection, generic acknowledgment, offer or withdrawal notice, or manual
  edit. Links to its supporting email evidence when it came from an email.
- **Email Evidence** (stored as "processed messages" in the data model): The minimal record of a
  processed email: message identifier, sender,
  subject, received date, classification, and short excerpt. Each email is processed at most
  once per user, which keeps scans idempotent.
- **Review Item**: An uncertain finding awaiting the user's decision. Types: possible new
  application, ambiguous match, offer/withdrawal, contradictory update, conflict with a manual
  correction, missing field. Includes candidate applications, a suggested action, and status
  (pending, resolved, dismissed).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A new user can go from first visit to a populated application table in under 5
  minutes for a mailbox with about 3 months of email (excluding the scan's own running time).
- **SC-002**: A scan covering 3 months of a typical job seeker's mailbox (about 3,000 emails)
  completes within 10 minutes, with progress visibly updating at least every 10 seconds.
- **SC-003**: On a labeled synthetic test mailbox, 100% of the listed acceptance scenarios pass,
  and at least 90% of the applications that have a confirmation email are imported with the
  correct company, position, and status.
- **SC-004**: On the labeled synthetic test mailbox, 0 job advertisements, alerts, or
  invitations to apply become applications, and 0 offers or withdrawals change a status.
- **SC-005**: Running the same scan any number of times produces 0 duplicate rows, events, or
  review items.
- **SC-006**: In isolation tests, 100% of attempts by one user to read or change another user's
  records are refused.
- **SC-007**: A returning user sees their saved table within 3 seconds of signing in.
- **SC-008**: After disconnecting, 0 Gmail credentials remain stored for that user, and no
  further email access occurs.
- **SC-009**: 100% of manual corrections survive later syncs unchanged.
- **SC-010**: In usability testing, at least 80% of users correctly explain why a given row has
  its status and Date Applied after opening its detail view.

## Assumptions

- Users have a Google account with Gmail, and the recruiting emails they care about are in that
  mailbox.
- The ApplyFlow sign-in Google account and the connected Gmail account are usually the same, but
  they may differ. Only one Gmail account can be connected at a time.
- Recruiting emails are mostly in English. Other languages may not be recognized in the MVP.
- Rule-based analysis (FR-020a) recognizes common applicant-tracking-system senders and standard
  English recruiting phrasing. Unusually worded emails may be missed or routed to review. This
  tradeoff is accepted in exchange for zero per-scan cost and no third-party sharing of email
  content.
- Evidence excerpts are short (a few sentences) and are kept only as long as the related
  application data exists.
- Status precedence for events with the same date: Rejected outranks In progress, which outranks
  Submitted. Any genuinely conflicting combination goes to review.
- Subsequent syncs scan only new emails. Already-processed emails are not re-classified unless
  the user deletes imported data and scans again.
- Automated tests use synthetic email fixtures instead of real mailboxes. The delivered product
  uses real Google sign-in and Gmail.
- Desktop web browsers are the primary target. Mobile layouts only need to remain usable.
- **Deployment (MVP)**: ApplyFlow runs locally on the developer's machine at no cost. Google
  sign-in runs in testing mode with only the developer's own Gmail account allowlisted. Google
  app verification is not pursued, so the "unverified app" warning is expected.
- **Weekly reconnect in testing mode**: Google issues refresh tokens that expire after 7 days to
  apps in "Testing" status that request Gmail access. In the MVP, the user should expect to
  reconnect Gmail about once a week. The reconnect state (FR-005) explains this in plain
  language. It goes away once the app is verified and published.
- **Future deployment**: Moving to an online deployment for a small allowlist of test users on
  free hosting tiers is a likely next step. The MVP MUST NOT block it: environment-specific
  values (addresses, credentials, allowed accounts) come from configuration, and long scans
  run as resumable batches rather than one long request.
- Multi-user behavior (FR-040, SC-006) is still required and is verified with multiple
  synthetic users in automated tests, even though only one real account is used locally.
- All tooling and services used in the MVP MUST be free.
