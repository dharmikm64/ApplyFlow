"""GET /api/me: the signed-in user, CSRF token, Gmail status, and recruiting cycle."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as DbSession

from app.auth.sessions import CurrentSession, get_current
from app.db import get_db
from app.models import GmailConnection, RecruitingCycle

router = APIRouter(prefix="/api", tags=["me"])


def gmail_payload(conn: GmailConnection | None) -> dict:
    if conn is None:
        return {"status": "not_connected", "address": None}
    return {"status": conn.status, "address": conn.gmail_address}


def cycle_payload(cycle: RecruitingCycle | None) -> dict:
    if cycle is None:
        return {"startDate": None, "timezone": None, "lastSuccessfulSyncAt": None}
    return {
        "startDate": cycle.start_date.isoformat(),
        "timezone": cycle.timezone,
        "lastSuccessfulSyncAt": cycle.covered_to_utc.isoformat() if cycle.covered_to_utc else None,
    }


@router.get("/me")
def me(current: CurrentSession = Depends(get_current), db: DbSession = Depends(get_db)) -> dict:
    user = current.user
    return {
        "user": {"email": user.email, "displayName": user.display_name},
        "csrfToken": current.session.csrf_token,
        "gmail": gmail_payload(db.get(GmailConnection, user.id)),
        "cycle": cycle_payload(db.get(RecruitingCycle, user.id)),
    }
