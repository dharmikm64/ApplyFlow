"""Recruiting cycle: start date + time zone, with change preview (FR-006, FR-043)."""

from __future__ import annotations

from datetime import date
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import exists, func, select, update
from sqlalchemy.orm import Session as DbSession

from app import clock
from app.api.errors import ApiError
from app.api.me import cycle_payload
from app.auth.sessions import CurrentSession, get_current
from app.db import get_db
from app.models import Application, ApplicationEvent, RecruitingCycle
from app.pipeline.window import window_start_utc

router = APIRouter(prefix="/api/cycle", tags=["cycle"])


class CycleBody(BaseModel):
    startDate: date
    timezone: str
    confirm: bool = False


def _validate(start: date, tz: str) -> None:
    try:
        zone = ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ApiError(422, "invalid_timezone", "Unknown time zone.") from exc
    if start > clock.now().astimezone(zone).date():
        raise ApiError(422, "start_date_in_future", "The start date can't be in the future.")


def _has_data(db: DbSession, user_id) -> bool:
    return bool(db.execute(select(exists().where(Application.user_id == user_id))).scalar())


def _before_cycle_ids(db: DbSession, user_id, start: date, tz: str) -> list:
    """Applications whose email evidence is ALL before the new start (never deleted)."""
    boundary = window_start_utc(start, tz)
    last_evidence = (
        select(ApplicationEvent.application_id, func.max(ApplicationEvent.occurred_at).label("last"))
        .where(ApplicationEvent.user_id == user_id, ApplicationEvent.message_id.is_not(None))
        .group_by(ApplicationEvent.application_id)
        .subquery()
    )
    rows = db.execute(
        select(last_evidence.c.application_id).where(last_evidence.c.last < boundary)
    ).scalars()
    return list(rows)


def _preview(db: DbSession, user_id, cycle: RecruitingCycle | None, start: date, tz: str) -> dict:
    if cycle is None:
        return {"direction": "same", "rowsMarkedBeforeCycle": 0, "rowsDeleted": 0,
                "willScanAddedPeriod": False, "message": "This sets your recruiting start date."}
    old = window_start_utc(cycle.start_date, cycle.timezone)
    new = window_start_utc(start, tz)
    if new < old:
        return {
            "direction": "earlier", "rowsMarkedBeforeCycle": 0, "rowsDeleted": 0,
            "willScanAddedPeriod": cycle.covered_from_utc is not None,
            "message": "Your existing rows are kept. The next sync will also scan the added "
                       "earlier period.",
        }
    if new > old:
        n = len(_before_cycle_ids(db, user_id, start, tz))
        return {
            "direction": "later", "rowsMarkedBeforeCycle": n, "rowsDeleted": 0,
            "willScanAddedPeriod": False,
            "message": f"No rows are deleted. {n} row(s) whose emails are all before the new "
                       "date will be labeled \"Before current cycle\"; you can delete them if "
                       "you choose.",
        }
    return {"direction": "same", "rowsMarkedBeforeCycle": 0, "rowsDeleted": 0,
            "willScanAddedPeriod": False, "message": "Nothing changes."}


@router.get("/preview-change")
def preview_change(
    startDate: date,
    timezone: str | None = None,
    current: CurrentSession = Depends(get_current),
    db: DbSession = Depends(get_db),
) -> dict:
    cycle = db.get(RecruitingCycle, current.user.id)
    tz = timezone or (cycle.timezone if cycle else "UTC")
    _validate(startDate, tz)
    return _preview(db, current.user.id, cycle, startDate, tz)


@router.put("")
def put_cycle(
    body: CycleBody, current: CurrentSession = Depends(get_current), db: DbSession = Depends(get_db)
) -> dict:
    user_id = current.user.id
    _validate(body.startDate, body.timezone)
    cycle = db.get(RecruitingCycle, user_id)
    if cycle is None:
        cycle = RecruitingCycle(user_id=user_id, start_date=body.startDate, timezone=body.timezone)
        db.add(cycle)
        db.flush()
        return cycle_payload(cycle)

    changed = cycle.start_date != body.startDate or cycle.timezone != body.timezone
    if changed and _has_data(db, user_id) and not body.confirm:
        raise ApiError(409, "confirm_required",
                       "Review how this change affects your rows, then confirm.")
    if changed:
        cycle.start_date = body.startDate
        cycle.timezone = body.timezone
        before = set(_before_cycle_ids(db, user_id, body.startDate, body.timezone))
        db.execute(
            update(Application)
            .where(Application.user_id == user_id)
            .values(before_cycle=Application.id.in_(before) if before else False)
        )
        db.flush()
    return cycle_payload(cycle)
