"""Test-only routes, registered ONLY when APP_ENV=test (plan Complexity Tracking).

They let automated tests and Playwright sign in as synthetic users and attach synthetic
mailboxes, without real Google sign-in or real Gmail.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session as DbSession

from app.api.errors import ApiError
from app.auth import crypto
from app.auth.sessions import (
    CurrentSession,
    create_session,
    get_current,
    load_session,
    set_session_cookie,
)
from app.db import get_db
from app.models import GmailConnection, RecruitingCycle
from app.repositories.users import get_or_create_by_sub
from app.testing import fixture_gmail

router = APIRouter(prefix="/test", tags=["test-only"])

GMAIL_READONLY = "https://www.googleapis.com/auth/gmail.readonly"


class LoginBody(BaseModel):
    sub: str
    email: str
    display_name: str | None = None


class ConnectBody(BaseModel):
    mailbox: str


class AppendBody(BaseModel):
    messages: list[str]


class AbortBody(BaseModel):
    after_pages: int | None


class ClockBody(BaseModel):
    now: datetime | None


@router.post("/login")
def test_login(body: LoginBody, response: Response, db: DbSession = Depends(get_db)) -> dict:
    user = get_or_create_by_sub(db, sub=body.sub, email=body.email, display_name=body.display_name)
    raw = create_session(db, user.id)
    set_session_cookie(response, raw)
    current = load_session(db, raw)
    assert current is not None
    return {"csrfToken": current.session.csrf_token, "userId": str(user.id)}


@router.post("/gmail/connect")
def test_gmail_connect(
    body: ConnectBody,
    current: CurrentSession = Depends(get_current),
    db: DbSession = Depends(get_db),
) -> dict:
    try:
        state = fixture_gmail.connect_mailbox(current.user.id, body.mailbox)
    except KeyError as exc:
        raise ApiError(404, "unknown_mailbox", str(exc)) from exc
    cycle = db.get(RecruitingCycle, current.user.id)
    if cycle and cycle.source_gmail_address and cycle.source_gmail_address != state.address:
        fixture_gmail.drop_state(current.user.id)
        raise ApiError(409, "mailbox_mismatch", "Delete imported data before switching mailboxes.")
    conn = db.get(GmailConnection, current.user.id)
    if conn is None:
        conn = GmailConnection(user_id=current.user.id)
        db.add(conn)
    conn.gmail_address = state.address
    conn.status = "connected"
    conn.refresh_token_ciphertext = crypto.encrypt("fixture-refresh-token")
    conn.granted_scopes = [GMAIL_READONLY]
    conn.last_error = None
    conn.connected_at = datetime.now(UTC)
    return {"address": state.address}


@router.post("/gmail/append")
def test_gmail_append(body: AppendBody, current: CurrentSession = Depends(get_current)) -> dict:
    state = fixture_gmail.get_state(current.user.id)
    if state is None:
        raise ApiError(409, "gmail_not_connected")
    for mid in body.messages:
        if mid not in state.message_ids:
            state.message_ids.append(mid)
    return {"count": len(state.message_ids)}


@router.post("/gmail/revoke")
def test_gmail_revoke(current: CurrentSession = Depends(get_current)) -> dict:
    state = fixture_gmail.get_state(current.user.id)
    if state is None:
        raise ApiError(409, "gmail_not_connected")
    state.revoked = True
    return {"revoked": True}


@router.post("/gmail/abort")
def test_gmail_abort(body: AbortBody, current: CurrentSession = Depends(get_current)) -> dict:
    state = fixture_gmail.get_state(current.user.id)
    if state is None:
        raise ApiError(409, "gmail_not_connected")
    state.abort_after_pages = body.after_pages
    state.pages_served = 0
    return {"ok": True}


@router.post("/clock")
def test_clock(body: ClockBody, current: CurrentSession = Depends(get_current)) -> dict:
    from app import clock

    clock.set_override(body.now)
    return {"now": clock.now().isoformat()}


@router.post("/worker/run")
def test_worker_run(current: CurrentSession = Depends(get_current)) -> dict:
    """Process queued runs synchronously (used by E2E when the embedded worker is off)."""
    from app.jobs.worker import run_until_idle

    return {"processed": run_until_idle()}


@router.post("/reset")
def test_reset() -> dict:
    """Wipe the *_test database and in-memory fixture state (E2E global setup only)."""
    from sqlalchemy import text

    from app import clock
    from app.db import get_engine

    with get_engine().begin() as conn:
        conn.execute(
            text(
                "TRUNCATE review_items, application_events, applications, processed_messages, "
                "scan_runs, recruiting_cycles, gmail_connections, sessions, users CASCADE"
            )
        )
    fixture_gmail.reset_registry()
    clock.set_override(None)
    return {"ok": True}
