"""Google OpenID Connect sign-in (FR-001, research R2/R3).

Scopes are `openid email profile` only; signing in never grants mailbox access.
"""

from __future__ import annotations

import logging

from authlib.integrations.base_client.errors import OAuthError
from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import RedirectResponse, Response

from app.auth.google import get_oauth, redirect_uri
from app.auth.sessions import (
    COOKIE_NAME,
    clear_session_cookie,
    create_session,
    destroy_session,
    get_current,
    set_session_cookie,
)
from app.config import get_settings
from app.db import get_sessionmaker
from app.repositories.users import get_or_create_by_sub

log = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


def is_allowed(email: str) -> bool:
    return email.strip().lower() in get_settings().ALLOWED_GOOGLE_EMAILS


@router.get("/login")
async def login(request: Request) -> Response:
    return await get_oauth().google.authorize_redirect(
        request, redirect_uri("/auth/callback"), prompt="select_account"
    )


def _sign_in(sub: str, email: str, name: str | None, old_raw: str | None) -> str:
    db = get_sessionmaker()()
    try:
        user = get_or_create_by_sub(db, sub=sub, email=email, display_name=name)
        destroy_session(db, old_raw)  # rotate: never reuse a pre-login session ID
        raw = create_session(db, user.id)
        db.commit()
        return raw
    finally:
        db.close()


@router.get("/callback")
async def callback(request: Request) -> Response:
    if request.query_params.get("error"):
        return RedirectResponse("/?error=signin_cancelled", status_code=303)
    try:
        token = await get_oauth().google.authorize_access_token(request)
    except OAuthError as exc:
        log.warning("oidc callback rejected", extra={"reason": exc.error})
        return RedirectResponse("/?error=signin_failed", status_code=303)
    info = token.get("userinfo") or {}
    sub, email = info.get("sub"), info.get("email")
    if not sub or not email or not info.get("email_verified", False):
        return RedirectResponse("/?error=signin_failed", status_code=303)
    if not is_allowed(email):
        log.info("sign-in refused: account not on allowlist")
        return RedirectResponse("/?error=not_allowed", status_code=303)
    raw = await run_in_threadpool(
        _sign_in, sub, email, info.get("name"), request.cookies.get(COOKIE_NAME)
    )
    response = RedirectResponse("/", status_code=303)
    set_session_cookie(response, raw)
    return response


@router.post("/logout")
def logout(request: Request) -> Response:
    db = get_sessionmaker()()
    try:
        get_current(request, db)  # requires a valid session + CSRF header
        destroy_session(db, request.cookies.get(COOKIE_NAME))
        db.commit()
    finally:
        db.close()
    response = Response(status_code=204)
    clear_session_cookie(response)
    return response
