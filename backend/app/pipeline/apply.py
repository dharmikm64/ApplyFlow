"""Persist extraction results: evidence, applications, events, review items (FR-010..FR-038a).

Idempotent by construction:
  * processed_messages UNIQUE (user_id, gmail_message_id): a message is applied at most once;
  * application_events UNIQUE (application_id, message_id);
  * review_items UNIQUE (user_id, dedupe_key): resolved/dismissed items are never recreated.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session as DbSession

from app.models import Application, ApplicationEvent, ProcessedMessage, ReviewItem
from app.pipeline.extraction.extract import APP_KINDS, NOISE_KINDS, ExtractionResult, ParsedMessage
from app.pipeline.matching import (
    Candidate,
    Incoming,
    MatchResult,
    match,
    normalize_company,
    normalize_position,
)
from app.pipeline.screening import domain_of
from app.pipeline.status import EventIn, derive

STATUS_LABEL = {"submitted": "Submitted", "in_progress": "In progress", "rejected": "Rejected"}
KIND_STATUS = {"confirmation": "submitted", "progress": "in_progress", "rejection": "rejected"}


@dataclass
class ApplyOutcome:
    skipped: bool = False
    created_app: bool = False
    updated_app: bool = False
    review_items: int = 0


# --- processed messages -----------------------------------------------------------------------
def record_message(
    db: DbSession, user_id: uuid.UUID, msg: ParsedMessage | None, *, gmail_id: str,
    thread_id: str | None, internal_date, result: ExtractionResult | None,
) -> uuid.UUID | None:
    """Insert the evidence row. Returns its id, or None if this message was already processed."""
    keep_details = result is not None and result.kind not in ("not_recruiting", *NOISE_KINDS)
    values = {
        "user_id": user_id,
        "gmail_message_id": gmail_id,
        "gmail_thread_id": thread_id,
        "internal_date": internal_date,
        "classification": result.kind if result else "not_recruiting",
        "sender": (f"{msg.sender_name} <{msg.sender_addr}>".strip() if msg and keep_details else None),
        "subject": msg.subject if msg and keep_details else None,
        "excerpt": result.excerpt if keep_details and result else None,
        "extracted": result.to_json() if keep_details and result else None,
        "rule_id": result.rule_id if result else None,
    }
    stmt = (
        insert(ProcessedMessage)
        .values(**values)
        .on_conflict_do_nothing(constraint="uq_processed_user_message")
        .returning(ProcessedMessage.id)
    )
    return db.execute(stmt).scalar_one_or_none()


def already_processed(db: DbSession, user_id: uuid.UUID, gmail_ids: list[str]) -> set[str]:
    if not gmail_ids:
        return set()
    rows = db.execute(
        select(ProcessedMessage.gmail_message_id).where(
            ProcessedMessage.user_id == user_id, ProcessedMessage.gmail_message_id.in_(gmail_ids)
        )
    ).scalars()
    return set(rows)


# --- review items -------------------------------------------------------------------------------
def add_review(
    db: DbSession, user_id: uuid.UUID, *, type: str, dedupe_key: str, explanation: str,
    suggestion: dict, message_id: uuid.UUID | None = None,
    application_id: uuid.UUID | None = None, candidates: list[uuid.UUID] | None = None,
) -> bool:
    stmt = (
        insert(ReviewItem)
        .values(
            user_id=user_id,
            type=type,
            message_id=message_id,
            application_id=application_id,
            candidate_application_ids=candidates or [],
            suggestion=suggestion,
            explanation=explanation,
            state="pending",
            dedupe_key=dedupe_key,
        )
        .on_conflict_do_nothing(constraint="uq_review_user_dedupe")
        .returning(ReviewItem.id)
    )
    return db.execute(stmt).scalar_one_or_none() is not None


# --- candidates ----------------------------------------------------------------------------------
def load_candidates(db: DbSession, user_id: uuid.UUID, company: str | None) -> list[Candidate]:
    q = select(Application).where(Application.user_id == user_id)
    norm = normalize_company(company)
    if norm is not None:
        q = q.where(Application.company_norm == norm)
    apps = list(db.execute(q).scalars())
    if not apps:
        return []
    ids = [a.id for a in apps]
    rows = db.execute(
        select(
            ApplicationEvent.application_id,
            ApplicationEvent.kind,
            ApplicationEvent.occurred_at,
            ProcessedMessage.sender,
            ProcessedMessage.gmail_thread_id,
        )
        .join(ProcessedMessage, ProcessedMessage.id == ApplicationEvent.message_id)
        .where(ApplicationEvent.user_id == user_id, ApplicationEvent.application_id.in_(ids))
    ).all()
    by_app: dict[uuid.UUID, Candidate] = {
        a.id: Candidate(a.id, a.company_norm, a.position_norm, a.req_id) for a in apps
    }
    for app_id, kind, occurred_at, sender, thread in rows:
        c = by_app[app_id]
        if sender:
            addr = sender.rsplit("<", 1)[-1].rstrip(">").strip().lower()
            if dom := domain_of(addr):
                c.sender_domains.add(dom)
        if thread:
            c.thread_ids.add(thread)
        if kind == "rejection" and (c.rejected_at is None or occurred_at > c.rejected_at):
            c.rejected_at = occurred_at
    return list(by_app.values())


# --- recompute ----------------------------------------------------------------------------------
def events_for(db: DbSession, app: Application) -> list[EventIn]:
    rows = db.execute(
        select(ApplicationEvent.kind, ApplicationEvent.occurred_at, ApplicationEvent.message_id,
               ProcessedMessage.extracted)
        .outerjoin(ProcessedMessage, ProcessedMessage.id == ApplicationEvent.message_id)
        .where(ApplicationEvent.user_id == app.user_id, ApplicationEvent.application_id == app.id)
    ).all()
    out = []
    for kind, occurred_at, message_id, extracted in rows:
        stated = None
        if extracted and extracted.get("stated_applied_date"):
            stated = date.fromisoformat(extracted["stated_applied_date"])
        out.append(EventIn(kind=kind, occurred_at=occurred_at, stated_applied_date=stated,
                           message_id=message_id))
    return out


def recompute(db: DbSession, app: Application, tz: str):
    """Re-derive status and Date Applied from all events, honoring manual overrides."""
    derived = derive(events_for(db, app), tz)
    if "status" not in app.overridden_fields and derived.status is not None:
        app.status = derived.status
    if "date_applied" not in app.overridden_fields:
        app.date_applied = derived.date_applied
        app.date_applied_source = derived.date_source
    return derived


def _attach(db: DbSession, app: Application, kind: str, msg_row_id: uuid.UUID, occurred_at) -> bool:
    exists = db.execute(
        select(func.count()).select_from(ApplicationEvent).where(
            ApplicationEvent.application_id == app.id, ApplicationEvent.message_id == msg_row_id
        )
    ).scalar_one()
    if exists:
        return False
    db.add(ApplicationEvent(user_id=app.user_id, application_id=app.id, kind=kind,
                            occurred_at=occurred_at, message_id=msg_row_id))
    db.flush()
    return True


def attach_and_recompute(
    db: DbSession, app: Application, kind: str, msg_row_id: uuid.UUID, occurred_at, tz: str
) -> int:
    """Attach an email event to an application; returns the number of review items created."""
    before = derive(events_for(db, app), tz)
    if not _attach(db, app, kind, msg_row_id, occurred_at):
        return 0
    if app.dismissed_at is not None:
        db.execute(
            ProcessedMessage.__table__.update()
            .where(ProcessedMessage.id == msg_row_id)
            .values(dismissed=True)
        )
    derived = recompute(db, app, tz)
    if app.dismissed_at is not None:
        return 0  # "Not an application": keep evidence, never nag about it
    created = 0
    # Manual overrides win; conflicting new evidence goes to review (FR-036).
    checks = {
        "status": (before.status, derived.status, app.status, lambda v: STATUS_LABEL.get(v, v)),
        "date_applied": (before.date_applied, derived.date_applied, app.date_applied,
                         lambda v: v.isoformat() if v else "unknown"),
    }
    for field, (old, new, current, fmt) in checks.items():
        if field in app.overridden_fields and new != old and new != current:
            created += add_review(
                db, app.user_id, type="manual_conflict",
                dedupe_key=f"manual_conflict:{msg_row_id}:{app.id}:{field}",
                explanation=(
                    f"You set {field.replace('_', ' ')} to {fmt(current)}, but a newer email "
                    f"suggests {fmt(new)}. Your value is kept unless you apply the suggestion."
                ),
                suggestion={"action": "apply", "field": field,
                            "value": new.isoformat() if hasattr(new, "isoformat") else new},
                message_id=msg_row_id, application_id=app.id,
            )
    for conflict in derived.conflicts:
        if conflict.message_id is None:
            continue
        created += add_review(
            db, app.user_id, type="contradictory_update",
            dedupe_key=f"contradictory_update:{conflict.message_id}:{app.id}",
            explanation=conflict.explanation,
            suggestion={"action": "apply", "field": "status", "value": "in_progress"},
            message_id=conflict.message_id, application_id=app.id,
        )
    return created


def create_application(db: DbSession, user_id: uuid.UUID, r: ExtractionResult, kind: str) -> Application:
    app = Application(
        user_id=user_id,
        company=r.company,
        company_norm=normalize_company(r.company),
        position=r.position,
        position_norm=normalize_position(r.position),
        req_id=r.req_id,
        status=KIND_STATUS[kind],
        date_applied=None,
        date_applied_source="unknown",
        overridden_fields=[],
    )
    db.add(app)
    db.flush()
    return app


def _suggest_create(r: ExtractionResult, kind: str | None) -> dict:
    return {
        "action": "create",
        "company": r.company,
        "position": r.position,
        "status": KIND_STATUS.get(kind or "", "submitted"),
    }


# --- entry point ---------------------------------------------------------------------------------
def apply_extraction(
    db: DbSession, user_id: uuid.UUID, msg: ParsedMessage, r: ExtractionResult, tz: str
) -> ApplyOutcome:
    row_id = record_message(
        db, user_id, msg, gmail_id=msg.id, thread_id=msg.thread_id,
        internal_date=msg.internal_date, result=r,
    )
    if row_id is None:
        return ApplyOutcome(skipped=True)
    out = ApplyOutcome()
    kind = r.kind
    if kind in ("not_recruiting", *NOISE_KINDS):
        return out

    inc = Incoming(kind=kind, company=r.company, position=r.position, req_id=r.req_id,
                   occurred_at=msg.internal_date, sender_domain=msg.sender_domain,
                   thread_id=msg.thread_id)
    result: MatchResult = match(inc, load_candidates(db, user_id, r.company))

    def by_id(app_id: uuid.UUID) -> Application:
        return db.get(Application, app_id)  # type: ignore[return-value]

    if kind == "unclear":
        if result.outcome == "existing":
            return out  # recorded as evidence only; nothing to change
        out.review_items += add_review(
            db, user_id, type="possible_application", dedupe_key=f"possible_application:{row_id}",
            explanation="This email looks recruiting-related, but ApplyFlow couldn't tell what "
                        "kind of update it is. Create an application from it, attach it, or dismiss it.",
            suggestion=_suggest_create(r, None), message_id=row_id, candidates=result.candidates,
        )
        return out

    if kind == "acknowledgment":
        if result.outcome == "existing":
            app = by_id(result.application_id)  # type: ignore[arg-type]
            out.review_items += attach_and_recompute(db, app, "acknowledgment", row_id, msg.internal_date, tz)
            out.updated_app = True
        return out

    if kind in ("offer", "withdrawal"):
        label = "an offer" if kind == "offer" else "a withdrawal"
        app_id = result.application_id if result.outcome == "existing" else None
        if app_id:
            app = by_id(app_id)
            attach_and_recompute(db, app, kind, row_id, msg.internal_date, tz)
            out.updated_app = True
            if app.dismissed_at is not None:
                return out
        out.review_items += add_review(
            db, user_id, type="offer_or_withdrawal", dedupe_key=f"offer_or_withdrawal:{row_id}",
            explanation=f"This email looks like {label}. Offers and withdrawals don't fit "
                        "Submitted / In progress / Rejected, so the status was not changed.",
            suggestion={"action": "dismiss"}, message_id=row_id, application_id=app_id,
            candidates=result.candidates,
        )
        return out

    assert kind in APP_KINDS
    if result.outcome == "existing":
        app = by_id(result.application_id)  # type: ignore[arg-type]
        if app.req_id is None and r.req_id:
            app.req_id = r.req_id
        out.review_items += attach_and_recompute(db, app, kind, row_id, msg.internal_date, tz)
        out.updated_app = True
        return out
    if result.outcome == "ambiguous":
        out.review_items += add_review(
            db, user_id, type="ambiguous_match", dedupe_key=f"ambiguous_match:{row_id}",
            explanation=f"This email could belong to more than one application ({result.reason}). "
                        "Choose the application it belongs to, or create a new one.",
            suggestion=_suggest_create(r, kind), message_id=row_id, candidates=result.candidates,
        )
        return out
    if result.outcome == "unmatchable" or r.confidence == "low":
        out.review_items += add_review(
            db, user_id, type="possible_application", dedupe_key=f"possible_application:{row_id}",
            explanation="This looks like an application update, but the company couldn't be "
                        "identified. Fill it in to create the application, or dismiss it.",
            suggestion=_suggest_create(r, kind), message_id=row_id,
        )
        return out

    app = create_application(db, user_id, r, kind)
    out.created_app = True
    out.review_items += attach_and_recompute(db, app, kind, row_id, msg.internal_date, tz)
    if app.position is None:
        out.review_items += add_review(
            db, user_id, type="missing_field", dedupe_key=f"missing_field:{row_id}:{app.id}:position",
            explanation="The email names the company but not the position. Add the position if you know it.",
            suggestion={"action": "apply", "field": "position", "value": None},
            message_id=row_id, application_id=app.id,
        )
    return out
