"""Revoked / denied access and mailbox mismatch (T088, FR-005)."""

from __future__ import annotations

import uuid

import app.auth.gmail_oauth as gmail_oauth
from app.auth.google import GMAIL_READONLY, get_oauth
from app.db import get_sessionmaker
from app.models import GmailConnection, RecruitingCycle
from tests.integration.helpers import apps, connect, scan
from tests.integration.test_gmail_connect import FakeAsyncClient


def test_revoked_mid_scan_is_recoverable(login):
    api = login()
    connect(api, "core-journey")
    scan(api)
    last = api.get("/api/me").json()["cycle"]["lastSuccessfulSyncAt"]
    api.post("/test/gmail/revoke")
    run = scan(api, "sync")
    assert run["status"] == "failed" and run["failureCode"] == "reconnect_required"
    with get_sessionmaker()() as db:
        conn = db.get(GmailConnection, uuid.UUID(api.user_id))
        assert conn.status == "revoked" and conn.refresh_token_ciphertext is None
    me = api.get("/api/me").json()
    assert me["gmail"]["status"] == "revoked"
    assert me["cycle"]["lastSuccessfulSyncAt"] == last
    assert len(apps(api)) == 3
    # Reconnect and sync again successfully.
    connect(api, "core-journey")
    assert scan(api, "sync")["status"] == "succeeded"


def test_denied_consent_shows_denied_status(login):
    api = login()
    r = api.http.get("/auth/gmail/callback?error=access_denied", follow_redirects=False)
    assert r.headers["location"] == "/?gmail=denied"
    assert api.get("/api/me").json()["gmail"]["status"] == "denied"
    r = api.post("/api/scans", json={"kind": "initial"})
    assert r.status_code == 409


def test_reconnecting_a_different_mailbox_is_refused_while_data_exists(login, monkeypatch):
    api = login()
    connect(api, "core-journey")
    scan(api)
    with get_sessionmaker()() as db:
        assert db.get(RecruitingCycle, uuid.UUID(api.user_id)).source_gmail_address == "jordan@candidate.test"

    # Real OAuth callback path, with a different mailbox address.
    class OtherMailbox(FakeAsyncClient):
        address = "someone-else@candidate.test"

    monkeypatch.setattr(gmail_oauth.httpx, "AsyncClient", OtherMailbox)

    async def fake(request, **kw):
        return {"access_token": "at", "refresh_token": "1//other", "scope": GMAIL_READONLY}

    monkeypatch.setattr(get_oauth().google_gmail, "authorize_access_token", fake)
    r = api.http.get("/auth/gmail/callback?code=c&state=s", follow_redirects=False)
    assert r.headers["location"] == "/?gmail=mailbox_mismatch"
    with get_sessionmaker()() as db:
        conn = db.get(GmailConnection, uuid.UUID(api.user_id))
        assert conn.gmail_address == "jordan@candidate.test"  # nothing stored for the other mailbox

    # After deleting imported data, switching mailboxes is allowed.
    api.delete("/api/data", json={"confirm": "DELETE"})
    r = api.http.get("/auth/gmail/callback?code=c&state=s", follow_redirects=False)
    assert r.headers["location"] == "/?gmail=connected"
