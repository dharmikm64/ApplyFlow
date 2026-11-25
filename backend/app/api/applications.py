"""Applications: list with search/filter/sort (FR-030/031)."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session as DbSession

from app.auth.sessions import CurrentSession, get_current
from app.db import get_db
from app.models import Application, ReviewItem
from app.models.tracker import APP_STATUSES

router = APIRouter(prefix="/api/applications", tags=["applications"])

StatusParam = Literal["submitted", "in_progress", "rejected"]


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def row_payload(app: Application, pending_review: bool) -> dict:
    return {
        "id": str(app.id),
        "company": app.company,
        "position": app.position,
        "dateApplied": app.date_applied.isoformat() if app.date_applied else None,
        "dateAppliedSource": app.date_applied_source,
        "status": app.status,
        "beforeCycle": app.before_cycle,
        "pendingReview": pending_review,
    }


@router.get("")
def list_applications(
    q: str | None = Query(default=None, max_length=200),
    status: list[StatusParam] = Query(default=[]),
    sort: Literal["date_applied"] = "date_applied",
    order: Literal["asc", "desc"] = "desc",
    view: Literal["active", "dismissed"] = "active",
    current: CurrentSession = Depends(get_current),
    db: DbSession = Depends(get_db),
) -> dict:
    user_id = current.user.id
    pending = (
        exists()
        .where(
            ReviewItem.user_id == user_id,
            ReviewItem.application_id == Application.id,
            ReviewItem.state == "pending",
        )
        .label("pending")
    )
    stmt = select(Application, pending).where(Application.user_id == user_id)
    stmt = stmt.where(
        Application.dismissed_at.is_(None)
        if view == "active"
        else Application.dismissed_at.is_not(None)
    )
    if q and q.strip():
        like = f"%{_escape_like(q.strip())}%"
        stmt = stmt.where(
            Application.company.ilike(like, escape="\\") | Application.position.ilike(like, escape="\\")
        )
    if status:
        stmt = stmt.where(Application.status.in_([s for s in status if s in APP_STATUSES]))
    date_col = Application.date_applied.asc() if order == "asc" else Application.date_applied.desc()
    stmt = stmt.order_by(
        date_col.nulls_last(), func.lower(Application.company).asc(), Application.created_at.asc()
    )
    rows = db.execute(stmt).all()
    return {"items": [row_payload(a, bool(p)) for a, p in rows], "total": len(rows)}


# --- detail, corrections, dismiss/restore (US3) -------------------------------------------
from datetime import UTC, date, datetime  # noqa: E402

from pydantic import BaseModel  # noqa: E402
from sqlalchemy import update  # noqa: E402

from app.models import ApplicationEvent, ProcessedMessage, RecruitingCycle  # noqa: E402
from app.pipeline.apply import recompute  # noqa: E402
from app.pipeline.matching import normalize_company, normalize_position  # noqa: E402
from app.pipeline.status import explain_date  # noqa: E402
from app.repositories.base import get_owned  # noqa: E402


def evidence_payload(pm: ProcessedMessage | None) -> dict | None:
    if pm is None:
        return None
    return {
        "sender": pm.sender,
        "subject": pm.subject,
        "date": pm.internal_date.isoformat(),
        "excerpt": pm.excerpt,
    }


def _tz(db: DbSession, user_id) -> str:
    cycle = db.get(RecruitingCycle, user_id)
    return cycle.timezone if cycle else "UTC"


def detail_payload(db: DbSession, app: Application) -> dict:
    user_id = app.user_id
    rows = db.execute(
        select(ApplicationEvent, ProcessedMessage)
        .outerjoin(ProcessedMessage, ProcessedMessage.id == ApplicationEvent.message_id)
        .where(ApplicationEvent.user_id == user_id, ApplicationEvent.application_id == app.id)
        .order_by(ApplicationEvent.occurred_at.asc(), ApplicationEvent.created_at.asc())
    ).all()
    first_conf = min(
        (ev.occurred_at for ev, _ in rows if ev.kind == "confirmation"), default=None
    )
    pending = list(
        db.execute(
            select(ReviewItem).where(
                ReviewItem.user_id == user_id,
                ReviewItem.application_id == app.id,
                ReviewItem.state == "pending",
            )
        ).scalars()
    )
    base = row_payload(app, bool(pending))
    base.update(
        reqId=app.req_id,
        overriddenFields=list(app.overridden_fields),
        dismissedAt=app.dismissed_at.isoformat() if app.dismissed_at else None,
    )
    return {
        "application": base,
        "dateAppliedExplanation": explain_date(
            app.date_applied_source, app.date_applied, first_conf, _tz(db, user_id)
        ),
        "events": [
            {
                "id": str(ev.id),
                "kind": ev.kind,
                "occurredAt": ev.occurred_at.isoformat(),
                "evidence": evidence_payload(pm),
                "detail": ev.detail,
            }
            for ev, pm in rows
        ],
        "reviewItems": [
            {"id": str(r.id), "type": r.type, "explanation": r.explanation} for r in pending
        ],
    }


@router.get("/{app_id}")
def get_application(
    app_id: str, current: CurrentSession = Depends(get_current), db: DbSession = Depends(get_db)
) -> dict:
    app = get_owned(db, Application, app_id, user_id=current.user.id)
    return detail_payload(db, app)


class PatchBody(BaseModel):
    company: str | None = None
    position: str | None = None
    dateApplied: date | None = None
    status: StatusParam | None = None


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value[:200] or None


def apply_manual_edit(db: DbSession, app: Application, field: str, value, *, at: datetime) -> None:
    """Set a field as a manual override and record it in the history (FR-035/036)."""
    old = getattr(app, field)
    if field == "company":
        app.company, app.company_norm = value, normalize_company(value)
    elif field == "position":
        app.position, app.position_norm = value, normalize_position(value)
    elif field == "date_applied":
        app.date_applied = value
        app.date_applied_source = "user"
    elif field == "status":
        app.status = value
    if field not in app.overridden_fields:
        app.overridden_fields = [*app.overridden_fields, field]
    fmt = lambda v: v.isoformat() if isinstance(v, date) else v  # noqa: E731
    db.add(
        ApplicationEvent(
            user_id=app.user_id, application_id=app.id, kind="manual_edit", occurred_at=at,
            detail={"field": field, "from": fmt(old), "to": fmt(value)},
        )
    )


@router.patch("/{app_id}")
def patch_application(
    app_id: str,
    body: PatchBody,
    current: CurrentSession = Depends(get_current),
    db: DbSession = Depends(get_db),
) -> dict:
    app = get_owned(db, Application, app_id, user_id=current.user.id)
    provided = body.model_fields_set
    if "status" in provided and body.status is None:
        from app.api.errors import ApiError

        raise ApiError(422, "validation", "Status must be Submitted, In progress, or Rejected.")
    now = datetime.now(UTC)
    mapping = {
        "company": ("company", _clean(body.company)),
        "position": ("position", _clean(body.position)),
        "dateApplied": ("date_applied", body.dateApplied),
        "status": ("status", body.status),
    }
    for key in ("company", "position", "dateApplied", "status"):
        if key in provided:
            field, value = mapping[key]
            if getattr(app, field) != value or field not in app.overridden_fields:
                apply_manual_edit(db, app, field, value, at=now)
    db.flush()
    recompute(db, app, _tz(db, app.user_id))
    db.flush()
    return detail_payload(db, app)


def _linked_message_ids(db: DbSession, app: Application) -> list:
    return list(
        db.execute(
            select(ApplicationEvent.message_id).where(
                ApplicationEvent.user_id == app.user_id,
                ApplicationEvent.application_id == app.id,
                ApplicationEvent.message_id.is_not(None),
            )
        ).scalars()
    )


@router.post("/{app_id}/dismiss")
def dismiss_application(
    app_id: str, current: CurrentSession = Depends(get_current), db: DbSession = Depends(get_db)
) -> dict:
    """'Not an application' (FR-038a): hidden, remembered, restorable."""
    app = get_owned(db, Application, app_id, user_id=current.user.id)
    if app.dismissed_at is None:
        now = datetime.now(UTC)
        app.dismissed_at = now
        ids = _linked_message_ids(db, app)
        if ids:
            db.execute(update(ProcessedMessage).where(ProcessedMessage.id.in_(ids)).values(dismissed=True))
        db.execute(
            update(ReviewItem)
            .where(ReviewItem.user_id == app.user_id, ReviewItem.application_id == app.id,
                   ReviewItem.state == "pending")
            .values(state="dismissed", resolved_at=now, resolution={"reason": "application dismissed"})
        )
        db.add(ApplicationEvent(user_id=app.user_id, application_id=app.id, kind="dismissed", occurred_at=now))
        db.flush()
    return detail_payload(db, app)


@router.post("/{app_id}/restore")
def restore_application(
    app_id: str, current: CurrentSession = Depends(get_current), db: DbSession = Depends(get_db)
) -> dict:
    app = get_owned(db, Application, app_id, user_id=current.user.id)
    if app.dismissed_at is not None:
        now = datetime.now(UTC)
        app.dismissed_at = None
        ids = _linked_message_ids(db, app)
        if ids:
            db.execute(update(ProcessedMessage).where(ProcessedMessage.id.in_(ids)).values(dismissed=False))
        db.add(ApplicationEvent(user_id=app.user_id, application_id=app.id, kind="restored", occurred_at=now))
        db.flush()
    return detail_payload(db, app)
