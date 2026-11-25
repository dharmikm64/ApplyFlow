<!--
Sync Impact Report
- Version change: (template, unversioned) → 1.0.0
- Modified principles: none (initial adoption; all placeholders replaced)
- Added principles:
  I. Complete Working Workflow
  II. Simplicity & MVP Discipline
  III. Per-User Privacy & Isolation
  IV. Read-Only Gmail & Secret Protection
  V. Email Content Is Untrusted Data
  VI. Factual Integrity, Evidence & Idempotency
  VII. Targeted Testing
- Added sections: Security & Data Handling Constraints; Development Workflow & Quality Gates;
  Governance
- Removed sections: none
- Templates:
  ✅ .specify/templates/plan-template.md — Constitution Check derives gates from this file;
     no edit needed
  ✅ .specify/templates/spec-template.md — no conflicting mandatory sections; no edit needed
  ✅ .specify/templates/tasks-template.md — "tests are OPTIONAL" note amended to reflect
     Principle VII mandatory test areas
  ✅ .specify/templates/checklist-template.md — no principle references; no edit needed
  ⚠ README.md / docs/quickstart.md — do not exist yet; reference principles when created
- Deferred TODOs: none
-->

# ApplyFlow Constitution

ApplyFlow is a hackathon-sized application that turns a user's recruiting emails into an
application tracker.

## Core Principles

### I. Complete Working Workflow

- The MVP MUST deliver one complete, working end-to-end workflow: sign in, connect Gmail via
  real OAuth, scan recruiting emails, extract applications, and view/correct them in a tracker.
- Integration with Gmail MUST be real in the delivered product; mocks and synthetic fixtures
  are permitted only in automated tests.
- A thin, fully working vertical slice takes priority over breadth. Features that do not
  advance the core workflow are deferred.

Rationale: A hackathon deliverable is judged by whether the workflow actually works on real
data, not by the number of partially built features.

### II. Simplicity & MVP Discipline

- Architecture MUST be the simplest that satisfies the MVP: a single deployable application,
  one datastore, and no speculative abstractions, services, queues, or plugin systems.
- Features outside the agreed MVP scope MUST NOT be built. Any scope addition MUST be agreed
  explicitly and recorded in the feature spec before implementation.
- Added complexity MUST be justified in the plan's Complexity Tracking table.
- Code MUST stay readable and maintainable: clear module boundaries (Gmail access,
  extraction, matching, persistence, UI) and no dead code.

Rationale: Limited time makes every extra moving part a risk to delivering the core workflow.

### III. Per-User Privacy & Isolation (NON-NEGOTIABLE)

- Every user's emails, OAuth credentials, extracted data, and applications MUST be accessible
  only to that user.
- Every data read and write MUST be scoped to the authenticated user on the server; client-
  supplied user identifiers MUST NOT be trusted.
- Requests for another user's resources MUST fail without revealing whether those resources
  exist.
- Email content MUST NOT be shared with any third party beyond what the user-facing workflow
  strictly requires.

Rationale: Recruiting emails contain sensitive personal and career information; one cross-user
leak is a total failure of the product.

### IV. Read-Only Gmail & Secret Protection (NON-NEGOTIABLE)

- The application MUST request only read-only Gmail scope (`gmail.readonly` or narrower).
  It MUST NEVER send, delete, label, archive, mark, or otherwise modify emails.
- OAuth client secrets, access tokens, and refresh tokens MUST stay on the server and MUST
  NEVER be exposed to the browser, URLs, or client-side storage.
- Stored tokens MUST be encrypted at rest with a key supplied via environment configuration.
- Secrets, tokens, and email bodies MUST NOT appear in logs, error messages, analytics, or
  version control. `.env` files and credential files MUST be git-ignored, and a
  `.env.example` with placeholder values MUST document required configuration.
- Users MUST be able to disconnect Gmail, which revokes and deletes their stored tokens.

Rationale: Least privilege limits the damage of any bug or breach; leaked tokens grant
direct access to a user's mailbox.

### V. Email Content Is Untrusted Data

- Email subjects, bodies, headers, and attachments MUST be treated as untrusted data and
  NEVER as instructions to the system or to any language model.
- When email content is passed to an LLM, it MUST be clearly delimited as data, the model
  MUST have no tools or actions it could be induced to take, and output MUST be validated
  against a strict schema before use.
- Email-derived content MUST be escaped or sanitized before rendering; raw email HTML MUST
  NOT be rendered unsanitized.

Rationale: Anyone can send a user an email; the content is attacker-controlled input.

### VI. Factual Integrity, Evidence & Idempotency

- The system MUST NEVER invent companies, positions, application dates, or statuses. Values
  not supported by an email MUST be left empty or marked unknown rather than guessed.
- Every extracted field and status change MUST retain a reference to its supporting
  evidence (source message ID and the relevant excerpt or reason) that the user can view.
- Users MUST be able to correct any extracted field, and user corrections MUST take
  precedence over, and not be overwritten by, later automated scans.
- Repeated scans MUST be idempotent: processing the same message again MUST NOT create
  duplicate applications or duplicate status events. Messages for an existing application
  MUST be matched to it rather than creating a new record.

Rationale: A tracker is only useful if its data can be trusted, verified, and fixed.

### VII. Targeted Testing

- Automated tests are REQUIRED for: application matching and deduplication, status updates
  and their ordering, date boundaries (scan windows, time zones, inclusive/exclusive edges),
  and user isolation.
- The main user journey MUST be covered by a Playwright end-to-end test.
- Automated tests MUST use synthetic email fixtures and MUST NOT depend on a real Gmail
  account, real tokens, or real personal data; tests MUST be repeatable and deterministic.
- Tests for other areas are added where they reduce real risk; full TDD is not mandated.

Rationale: These areas carry the highest risk of silent data corruption or privacy failure.

## Security & Data Handling Constraints

- Store only the data the workflow needs; prefer storing extracted fields and short evidence
  excerpts over full email bodies.
- Users MUST be able to delete their account data, including applications, evidence, and
  tokens.
- Session cookies MUST be HTTP-only and secure in production, and state-changing endpoints
  MUST be protected against CSRF. The OAuth flow MUST validate the `state` parameter.
- Dependencies MUST be limited to well-maintained packages needed for the MVP.

## Development Workflow & Quality Gates

- Each feature follows the Spec Kit flow: specify → plan → tasks → implement. Every plan MUST
  pass the Constitution Check before research and again after design.
- Before a feature is considered done: the required tests (Principle VII) pass, the Playwright
  main-journey test passes, and no secrets or email bodies appear in logs, diffs, or fixtures.
- Code review (self or peer) MUST verify user scoping on every new data access path and
  read-only Gmail usage on every new Gmail call.

## Governance

- This constitution supersedes other practices and guidance for ApplyFlow. Where a template
  or plan conflicts with it, the constitution wins.
- Amendments require updating this file with a Sync Impact Report, bumping the version, and
  propagating changes to dependent templates in `.specify/templates/`.
- Versioning follows semantic versioning: MAJOR for removing or redefining a principle, MINOR
  for adding a principle or materially expanding guidance, PATCH for clarifications.
- Every plan and review MUST check compliance; any violation MUST be justified in the plan's
  Complexity Tracking table or the work MUST be changed. Principles III and IV admit no
  exceptions.
- Runtime development guidance lives in `CLAUDE.md` and the current feature plan.

**Version**: 1.0.0 | **Ratified**: 2026-11-25 | **Last Amended**: 2026-11-25
