"""Gmail authorization flow: gmail.readonly only, separate from sign-in (FR-002/003/005, R2)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import httpx
from authlib.integrations.base_client.errors import OAuthError
from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import RedirectResponse, Response

from app.auth import crypto
from app.auth.google import GMAIL_READONLY, get_oauth, redirect_uri
from app.auth.sessions import COOKIE_NAME, load_session
from app.db import get_sessionmaker
from app.models import GmailConnection, RecruitingCycle

log = logging.getLogger(__name__)
router = APIRouter(prefix="/auth/gmail", tags=["gmail-auth"])

PROFILE_URL = "https://gmail.googleapis.com/gmail/v1/users/me/profile"


def _session_user(request: Request):
    db = get_sessionmaker()()
    try:
        current = load_session(db, request.cookies.get(COOKIE_NAME))
        db.commit()
        return (current.user.id, current.user.email) if current else None
    finally:
        db.close()


@router.get("/connect")
async def connect(request: Request) -> Response:
    who = await run_in_threadpool(_session_user, request)
    if who is None:
        return RedirectResponse("/?error=signin_required", status_code=303)
    return await get_oauth().google_gmail.authorize_redirect(
        request,
        redirect_uri("/auth/gmail/callback"),
        access_type="offline",
        prompt="consent",
        login_hint=who[1],
    )


def _record_denied(user_id, reason: str) -> None:
    db = get_sessionmaker()()
    try:
        conn = db.get(GmailConnection, user_id)
        if conn is None:
            db.add(GmailConnection(user_id=user_id, status="denied", last_error=reason))
        elif conn.status != "connected":
            conn.status = "denied"
            conn.refresh_token_ciphertext = None
            conn.last_error = reason
        db.commit()
    finally:
        db.close()


def _store_connection(user_id, address: str, refresh_token: str, scopes: list[str]) -> str:
    """Returns 'connected' or 'mailbox_mismatch'."""
    db = get_sessionmaker()()
    try:
        cycle = db.get(RecruitingCycle, user_id)
        if cycle and cycle.source_gmail_address and cycle.source_gmail_address != address:
            return "mailbox_mismatch"
        conn = db.get(GmailConnection, user_id)
        if conn is None:
            conn = GmailConnection(user_id=user_id)
            db.add(conn)
        conn.gmail_address = address
        conn.status = "connected"
        conn.refresh_token_ciphertext = crypto.encrypt(refresh_token)
        conn.granted_scopes = scopes
        conn.last_error = None
        conn.connected_at = datetime.now(UTC)
        db.commit()
        return "connected"
    finally:
        db.close()


async def _revoke_quietly(token: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post("https://oauth2.googleapis.com/revoke", data={"token": token})
    except httpx.HTTPError:
        log.warning("gmail token revoke failed")


@router.get("/callback")
async def callback(request: Request) -> Response:
    who = await run_in_threadpool(_session_user, request)
    if who is None:
        return RedirectResponse("/?error=signin_required", status_code=303)
    user_id = who[0]

    if request.query_params.get("error"):
        await run_in_threadpool(_record_denied, user_id, "access_denied")
        return RedirectResponse("/?gmail=denied", status_code=303)
    try:
        token = await get_oauth().google_gmail.authorize_access_token(request)
    except OAuthError as exc:
        log.warning("gmail callback rejected", extra={"reason": exc.error})
        return RedirectResponse("/?gmail=error", status_code=303)

    scopes = str(token.get("scope", "")).split()
    if GMAIL_READONLY not in scopes:
        # Granular consent: the user unticked the Gmail box (FR-005).
        await run_in_threadpool(_record_denied, user_id, "scope_missing")
        return RedirectResponse("/?gmail=denied", status_code=303)
    refresh_token = token.get("refresh_token")
    if not refresh_token:
        return RedirectResponse("/?gmail=error", status_code=303)

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            PROFILE_URL, headers={"Authorization": f"Bearer {token['access_token']}"}
        )
    if resp.status_code != 200:
        return RedirectResponse("/?gmail=error", status_code=303)
    address = resp.json().get("emailAddress", "")

    outcome = await run_in_threadpool(_store_connection, user_id, address, refresh_token, scopes)
    if outcome == "mailbox_mismatch":
        await _revoke_quietly(refresh_token)
        return RedirectResponse("/?gmail=mailbox_mismatch", status_code=303)
    return RedirectResponse("/?gmail=connected", status_code=303)
