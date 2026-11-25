"""Review area: uncertain results kept out of the main table (FR-037, FR-038)."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from app.api.applications import _tz, apply_manual_edit, evidence_payload
from app.api.errors import ApiError
from app.auth.sessions import CurrentSession, get_current
from app.db import get_db
from app.models import Application, ApplicationEvent, ProcessedMessage, ReviewItem
from app.pipeline.apply import attach_and_recompute, recompute
from app.pipeline.matching import normalize_company, normalize_position
from app.repositories.base import get_owned

router = APIRouter(prefix="/api/review-items", tags=["review"])

EVENT_FOR_CLASSIFICATION = {
    "confirmation": "confirmation",
    "progress": "progress",
    "rejection": "rejection",
    "acknowledgment": "acknowledgment",
    "offer": "offer",
    "withdrawal": "withdrawal",
}
EVENT_FOR_STATUS = {"submitted": "confirmation", "in_progress": "progress", "rejected": "rejection"}


def _ref(app: Application | None) -> dict | None:
    if app is None:
        return None
    return {"id": str(app.id), "company": app.company, "position": app.position}


def item_payload(db: DbSession, item: ReviewItem) -> dict:
    pm = db.get(ProcessedMessage, item.message_id) if item.message_id else None
    app = db.get(Application, item.application_id) if item.application_id else None
    cands = []
    if item.candidate_application_ids:
        cands = list(
            db.execute(
                select(Application).where(
                    Application.user_id == item.user_id,
                    Application.id.in_(item.candidate_application_ids),
                )
            ).scalars()
        )
    return {
        "id": str(item.id),
        "type": item.type,
        "explanation": item.explanation,
        "evidence": evidence_payload(pm),
        "application": _ref(app),
        "candidates": [_ref(c) for c in cands],
        "suggestion": item.suggestion,
    }


@router.get("")
def list_review_items(
    state: Literal["pending", "resolved", "dismissed"] = "pending",
    current: CurrentSession = Depends(get_current),
    db: DbSession = Depends(get_db),
) -> dict:
    user_id = current.user.id
    items = list(
        db.execute(
            select(ReviewItem)
            .where(ReviewItem.user_id == user_id, ReviewItem.state == state)
            .order_by(ReviewItem.created_at.asc())
        ).scalars()
    )
    pending = db.execute(
        select(func.count()).select_from(ReviewItem).where(
            ReviewItem.user_id == user_id, ReviewItem.state == "pending"
        )
    ).scalar_one()
    return {"items": [item_payload(db, i) for i in items], "pendingCount": pending}


class ResolveBody(BaseModel):
    action: Literal["create", "attach", "apply", "dismiss"]
    applicationId: uuid.UUID | None = None
    fields: dict[str, str | None] | None = None


def _event_kind(pm: ProcessedMessage | None, status_hint: str | None) -> str:
    if pm is not None and pm.classification in EVENT_FOR_CLASSIFICATION:
        return EVENT_FOR_CLASSIFICATION[pm.classification]
    return EVENT_FOR_STATUS.get(status_hint or "", "confirmation")


@router.post("/{item_id}/resolve")
def resolve(
    item_id: str,
    body: ResolveBody,
    current: CurrentSession = Depends(get_current),
    db: DbSession = Depends(get_db),
) -> dict:
    user_id = current.user.id
    item = get_owned(db, ReviewItem, item_id, user_id=user_id)
    if item.state != "pending":
        raise ApiError(409, "already_resolved", "This item was already resolved.")
    tz = _tz(db, user_id)
    now = datetime.now(UTC)
    pm = db.get(ProcessedMessage, item.message_id) if item.message_id else None
    s = item.suggestion or {}
    fields = body.fields or {}
    target: Application | None = None

    if body.action == "dismiss":
        item.state = "dismissed"
    elif body.action == "create":
        if item.type not in ("possible_application", "ambiguous_match"):
            raise ApiError(422, "invalid_action", "This item can't create an application.")
        company = (fields.get("company") or s.get("company") or "").strip() or None
        position = (fields.get("position") or s.get("position") or "").strip() or None
        if company is None:
            raise ApiError(422, "company_required", "Enter the company name.")
        status = s.get("status") if s.get("status") in EVENT_FOR_STATUS else "submitted"
        target = Application(
            user_id=user_id, company=company, company_norm=normalize_company(company),
            position=position, position_norm=normalize_position(position),
            status=status, date_applied_source="unknown", overridden_fields=[],
        )
        db.add(target)
        db.flush()
        if pm is not None:
            attach_and_recompute(db, target, _event_kind(pm, status), pm.id, pm.internal_date, tz)
        item.state = "resolved"
    elif body.action == "attach":
        if body.applicationId is None:
            raise ApiError(422, "application_required", "Choose an application.")
        target = get_owned(db, Application, body.applicationId, user_id=user_id)
        if pm is not None:
            attach_and_recompute(db, target, _event_kind(pm, s.get("status")), pm.id, pm.internal_date, tz)
        item.state = "resolved"
    elif body.action == "apply":
        if item.application_id is None:
            raise ApiError(422, "invalid_action", "Nothing to apply.")
        target = get_owned(db, Application, item.application_id, user_id=user_id)
        if item.type == "missing_field":
            field = s.get("field") or "position"
            value = (fields.get(field) or "").strip() or None
            if value is None:
                raise ApiError(422, "value_required", "Enter a value.")
            apply_manual_edit(db, target, field, value, at=now)
        else:
            field = s.get("field") or "status"
            value = s.get("value")
            if field == "date_applied" and isinstance(value, str):
                value = date.fromisoformat(value)
            if field == "status" and value not in EVENT_FOR_STATUS:
                raise ApiError(422, "invalid_action", "Nothing to apply.")
            apply_manual_edit(db, target, field, value, at=now)
        db.flush()
        recompute(db, target, tz)
        item.state = "resolved"

    item.resolved_at = now
    item.resolution = {
        "action": body.action,
        "applicationId": str(target.id) if target else None,
    }
    app_for_event = target or (db.get(Application, item.application_id) if item.application_id else None)
    if app_for_event is not None:
        db.add(
            ApplicationEvent(
                user_id=user_id, application_id=app_for_event.id, kind="review_resolved",
                occurred_at=now, detail={"type": item.type, "action": body.action},
            )
        )
    db.flush()
    return {"id": str(item.id), "state": item.state, "applicationId": str(target.id) if target else None}
