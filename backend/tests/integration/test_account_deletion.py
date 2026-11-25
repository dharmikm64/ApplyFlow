"""Delete account (T090, FR-042a)."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select

from app.db import get_sessionmaker
from app.models import (
    Application,
    ApplicationEvent,
    GmailConnection,
    ProcessedMessage,
    RecruitingCycle,
    ReviewItem,
    ScanRun,
    Session,
    User,
)
from app.testing import fixture_gmail
from tests.integration.helpers import apps, connect, scan

OWNED = (Session, GmailConnection, RecruitingCycle, ScanRun, ProcessedMessage, Application, ApplicationEvent, ReviewItem)


def rows_for(user_id: uuid.UUID) -> dict:
    with get_sessionmaker()() as db:
        out = {m.__tablename__: db.execute(select(func.count()).select_from(m).where(m.user_id == user_id)).scalar_one() for m in OWNED}
        out["users"] = db.execute(select(func.count()).select_from(User).where(User.id == user_id)).scalar_one()
    return out


def test_delete_account_requires_confirmation(login):
    api = login()
    assert api.delete("/api/account", json={}).status_code == 422
    assert api.delete("/api/account", json={"confirm": "delete"}).status_code == 422
    assert api.get("/api/me").status_code == 200


def test_delete_account_removes_everything_for_that_user_only(login):
    alice = login()
    connect(alice, "core-journey")
    scan(alice)
    alice.post("/api/scans", json={"kind": "sync"})  # a queued run gets cancelled
    bob = login("sub-bob", "bob@example.test")
    connect(bob, "bob-mailbox")
    scan(bob)
    alice_id = uuid.UUID(alice.user_id)

    r = alice.delete("/api/account", json={"confirm": "DELETE"})
    assert r.status_code == 204
    assert "af_session=" in r.headers.get("set-cookie", "")
    assert all(v == 0 for v in rows_for(alice_id).values()), rows_for(alice_id)
    assert fixture_gmail.get_state(alice_id) is None  # Gmail revoked
    assert alice.get("/api/me").status_code == 401

    assert len(apps(bob)) == 1  # untouched

    fresh = login()  # same Google sub signs in again -> brand-new empty user
    assert fresh.user_id != alice.user_id
    me = fresh.get("/api/me").json()
    assert me["gmail"]["status"] == "not_connected" and me["cycle"]["startDate"] is None
    assert apps(fresh) == []
