"""Account and data controls: disconnect Gmail, delete imported data, delete account
(FR-041, FR-042, FR-042a, SC-008)."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session as DbSession

from app.api.errors import ApiError
from app.auth import crypto
from app.auth.google import REVOKE_URL
from app.auth.sessions import CurrentSession, clear_session_cookie, get_current
from app.config import get_settings
from app.db import get_db
from app.models import (
    Application,
    GmailConnection,
    ProcessedMessage,
    RecruitingCycle,
    ReviewItem,
    ScanRun,
    User,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["account"])


class ConfirmBody(BaseModel):
    confirm: str = ""


def cancel_active_runs(db: DbSession, user_id: uuid.UUID, code: str = "gmail_disconnected") -> None:
    """Fail queued/running runs; the job re-checks the connection before every page."""
    db.execute(
        update(ScanRun)
        .where(ScanRun.user_id == user_id, ScanRun.status.in_(("queued", "running")))
        .values(status="failed", failure_code=code, finished_at=datetime.now(UTC))
    )


def revoke_at_google(conn: GmailConnection) -> str:
    """Best-effort revocation. Returns an outcome code (never the token)."""
    if conn.refresh_token_ciphertext is None:
        return "no_token"
    if get_settings().APP_ENV == "test":
        from app.testing import fixture_gmail

        fixture_gmail.drop_state(conn.user_id)
        return "revoked"
    try:
        token = crypto.decrypt(conn.refresh_token_ciphertext)
        resp = httpx.post(REVOKE_URL, data={"token": token}, timeout=10)
        return "revoked" if resp.status_code == 200 else f"http_{resp.status_code}"
    except Exception as exc:  # deletion proceeds regardless
        return f"error_{type(exc).__name__}"


def _has_active_run(db: DbSession, user_id: uuid.UUID) -> bool:
    return (
        db.execute(
            select(ScanRun.id).where(
                ScanRun.user_id == user_id, ScanRun.status.in_(("queued", "running"))
            )
        ).first()
        is not None
    )


@router.delete("/gmail", status_code=204)
def disconnect_gmail(
    current: CurrentSession = Depends(get_current), db: DbSession = Depends(get_db)
) -> Response:
    user_id = current.user.id
    cancel_active_runs(db, user_id)
    conn = db.get(GmailConnection, user_id)
    if conn is not None:
        outcome = revoke_at_google(conn)
        log.info("gmail disconnected", extra={"revoke_outcome": outcome})
        db.delete(conn)
    db.flush()
    return Response(status_code=204)


@router.delete("/data", status_code=204)
def delete_imported_data(
    body: ConfirmBody, current: CurrentSession = Depends(get_current), db: DbSession = Depends(get_db)
) -> Response:
    if body.confirm != "DELETE":
        raise ApiError(422, "confirm_required", 'Type "DELETE" to confirm.')
    user_id = current.user.id
    if _has_active_run(db, user_id):
        raise ApiError(409, "scan_in_progress", "Wait for the current scan to finish.")
    for model in (ReviewItem, Application, ProcessedMessage, ScanRun):
        db.execute(delete(model).where(model.user_id == user_id))  # events cascade
    cycle = db.get(RecruitingCycle, user_id)
    if cycle is not None:
        cycle.covered_from_utc = None
        cycle.covered_to_utc = None
        cycle.source_gmail_address = None
    db.flush()
    return Response(status_code=204)


@router.delete("/account", status_code=204)
def delete_account(
    body: ConfirmBody,
    request: Request,
    current: CurrentSession = Depends(get_current),
    db: DbSession = Depends(get_db),
) -> Response:
    if body.confirm != "DELETE":
        raise ApiError(422, "confirm_required", 'Type "DELETE" to confirm.')
    user_id = current.user.id
    cancel_active_runs(db, user_id)
    conn = db.get(GmailConnection, user_id)
    if conn is not None:
        log.info("account deletion: gmail revoke", extra={"revoke_outcome": revoke_at_google(conn)})
    db.execute(delete(User).where(User.id == user_id))  # ON DELETE CASCADE removes the rest
    db.flush()
    response = Response(status_code=204)
    clear_session_cookie(response)
    return response
