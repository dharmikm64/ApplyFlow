"""Scan runs: start "Scan emails" / "Sync now" and read progress (FR-007..FR-011)."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from app import clock
from app.api.errors import ApiError
from app.auth.sessions import CurrentSession, get_current
from app.db import get_db
from app.jobs.scan_job import create_run
from app.models import GmailConnection, RecruitingCycle, ScanRun
from app.pipeline.window import segments_for_run

router = APIRouter(prefix="/api/scans", tags=["scans"])


class ScanBody(BaseModel):
    kind: Literal["initial", "sync"] = "sync"


def run_payload(run: ScanRun) -> dict:
    iso = lambda d: d.isoformat() if d else None  # noqa: E731
    return {
        "id": str(run.id),
        "kind": run.kind,
        "status": run.status,
        "windowStart": iso(run.window_start_utc),
        "windowEnd": iso(run.window_end_utc),
        "progress": {
            "listed": run.listed,
            "estimatedTotal": run.estimated_total,
            "screened": run.screened,
            "candidates": run.candidates,
            "processed": run.processed,
        },
        "results": {
            "createdApps": run.created_apps,
            "updatedApps": run.updated_apps,
            "reviewItems": run.review_items,
        },
        "failureCode": run.failure_code,
        "startedAt": iso(run.started_at),
        "finishedAt": iso(run.finished_at),
    }


@router.post("", status_code=202)
def start_scan(
    body: ScanBody, current: CurrentSession = Depends(get_current), db: DbSession = Depends(get_db)
) -> dict:
    user_id = current.user.id
    conn = db.get(GmailConnection, user_id)
    if conn is None or conn.status != "connected":
        raise ApiError(409, "gmail_not_connected", "Connect Gmail before scanning.")
    cycle = db.get(RecruitingCycle, user_id)
    if cycle is None:
        raise ApiError(409, "no_start_date", "Choose your recruiting start date first.")
    segments = segments_for_run(
        start_date=cycle.start_date,
        tz=cycle.timezone,
        covered_from=cycle.covered_from_utc,
        covered_to=cycle.covered_to_utc,
        now=clock.now(),
        kind=body.kind,
    )
    try:
        with db.begin_nested():
            run = create_run(db, user_id, body.kind, segments)
    except IntegrityError as exc:
        raise ApiError(409, "scan_in_progress", "A scan is already running.") from exc
    return run_payload(run)


@router.get("/current")
def current_scan(current: CurrentSession = Depends(get_current), db: DbSession = Depends(get_db)):
    run = db.execute(
        select(ScanRun)
        .where(ScanRun.user_id == current.user.id)
        .order_by(ScanRun.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if run is None:
        return Response(status_code=204)
    return run_payload(run)
