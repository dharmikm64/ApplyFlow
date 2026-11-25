"""Server-side sessions and CSRF protection (research R3).

The browser holds only an opaque random session ID in an HttpOnly cookie; the database stores
its SHA-256 hash, the user, a CSRF token, and an expiry.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import Depends, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DbSession

from app.api.errors import ApiError, unauthenticated
from app.config import get_settings
from app.db import get_db
from app.models import Session, User

COOKIE_NAME = "af_session"
SESSION_TTL = timedelta(days=14)
SLIDE_AFTER = timedelta(hours=1)
MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _hash(raw: str) -> bytes:
    return hashlib.sha256(raw.encode()).digest()


@dataclass
class CurrentSession:
    user: User
    session: Session


def create_session(db: DbSession, user_id: uuid.UUID) -> str:
    raw = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    db.add(
        Session(
            id_hash=_hash(raw),
            user_id=user_id,
            csrf_token=secrets.token_urlsafe(32),
            created_at=now,
            last_seen_at=now,
            expires_at=now + SESSION_TTL,
        )
    )
    db.flush()
    return raw


def set_session_cookie(response: Response, raw: str) -> None:
    response.set_cookie(
        COOKIE_NAME,
        raw,
        max_age=int(SESSION_TTL.total_seconds()),
        httponly=True,
        samesite="lax",
        secure=get_settings().secure_cookies,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


def destroy_session(db: DbSession, raw: str | None) -> None:
    if raw:
        db.execute(delete(Session).where(Session.id_hash == _hash(raw)))


def load_session(db: DbSession, raw: str | None) -> CurrentSession | None:
    if not raw:
        return None
    now = datetime.now(UTC)
    row = db.execute(
        select(Session, User)
        .join(User, User.id == Session.user_id)
        .where(Session.id_hash == _hash(raw), Session.expires_at > now)
    ).first()
    if row is None:
        return None
    sess, user = row
    if now - sess.last_seen_at > SLIDE_AFTER:
        sess.last_seen_at = now
        sess.expires_at = now + SESSION_TTL
    return CurrentSession(user=user, session=sess)


def get_current(request: Request, db: DbSession = Depends(get_db)) -> CurrentSession:
    current = load_session(db, request.cookies.get(COOKIE_NAME))
    if current is None:
        raise unauthenticated()
    if request.method in MUTATING_METHODS:
        header = request.headers.get("X-CSRF-Token", "")
        if not secrets.compare_digest(header, current.session.csrf_token):
            raise ApiError(403, "csrf", "Missing or invalid CSRF token.")
    return current


def get_current_user(current: CurrentSession = Depends(get_current)) -> User:
    return current.user
