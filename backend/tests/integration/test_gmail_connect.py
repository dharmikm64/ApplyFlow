"""Gmail consent callback: scope check, encryption, state, session (T041, FR-003/005)."""

from __future__ import annotations

import pytest
from authlib.integrations.base_client.errors import OAuthError
from sqlalchemy import select

import app.auth.gmail_oauth as gmail_oauth
from app.auth import crypto
from app.auth.google import GMAIL_READONLY, get_oauth
from app.db import get_sessionmaker
from app.models import GmailConnection


class FakeResp:
    def __init__(self, status: int, body: dict) -> None:
        self.status_code = status
        self._body = body

    def json(self) -> dict:
        return self._body


class FakeAsyncClient:
    address = "jordan@candidate.test"

    def __init__(self, *a, **kw) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, headers=None):
        return FakeResp(200, {"emailAddress": self.address})

    async def post(self, url, data=None):
        return FakeResp(200, {})


@pytest.fixture
def stub_google(monkeypatch):
    monkeypatch.setattr(gmail_oauth.httpx, "AsyncClient", FakeAsyncClient)

    def set_token(token=None, error: str | None = None):
        async def fake(request, **kw):
            if error:
                raise OAuthError(error=error)
            return token

        monkeypatch.setattr(get_oauth().google_gmail, "authorize_access_token", fake)

    return set_token


def conn_row(user_id):
    with get_sessionmaker()() as db:
        return db.execute(select(GmailConnection).where(GmailConnection.user_id == user_id)).scalar_one_or_none()


def test_granted_scope_stores_encrypted_token(login, stub_google):
    api = login()
    stub_google({"access_token": "at", "refresh_token": "1//refresh-secret", "scope": f"{GMAIL_READONLY}"})
    r = api.http.get("/auth/gmail/callback?code=c&state=s", follow_redirects=False)
    assert r.headers["location"] == "/?gmail=connected"
    row = conn_row(api.user_id)
    assert row.status == "connected"
    assert row.gmail_address == "jordan@candidate.test"
    assert b"1//refresh-secret" not in bytes(row.refresh_token_ciphertext)
    assert crypto.decrypt(row.refresh_token_ciphertext) == "1//refresh-secret"
    assert api.get("/api/me").json()["gmail"] == {"status": "connected", "address": "jordan@candidate.test"}


def test_unticked_scope_is_denied(login, stub_google):
    api = login()
    stub_google({"access_token": "at", "refresh_token": "1//x", "scope": "openid email"})
    r = api.http.get("/auth/gmail/callback?code=c&state=s", follow_redirects=False)
    assert r.headers["location"] == "/?gmail=denied"
    row = conn_row(api.user_id)
    assert row.status == "denied" and row.refresh_token_ciphertext is None


def test_user_cancelled_consent_is_denied(login):
    api = login()
    r = api.http.get("/auth/gmail/callback?error=access_denied&state=s", follow_redirects=False)
    assert r.headers["location"] == "/?gmail=denied"
    assert api.get("/api/me").json()["gmail"]["status"] == "denied"


def test_mismatched_state_is_rejected(login, stub_google):
    api = login()
    stub_google(error="mismatching_state")
    r = api.http.get("/auth/gmail/callback?code=c&state=bad", follow_redirects=False)
    assert r.headers["location"] == "/?gmail=error"
    assert conn_row(api.user_id) is None


def test_callback_without_session_is_rejected(client, stub_google):
    stub_google({"access_token": "at", "refresh_token": "1//x", "scope": GMAIL_READONLY})
    r = client.get("/auth/gmail/callback?code=c&state=s", follow_redirects=False)
    assert r.headers["location"] == "/?error=signin_required"


def test_connect_requires_session(client):
    r = client.get("/auth/gmail/connect", follow_redirects=False)
    assert r.headers["location"] == "/?error=signin_required"


def test_connect_requests_only_gmail_readonly(login, monkeypatch):
    api = login()
    captured = {}

    async def fake_redirect(request, redirect_uri, **kw):
        from fastapi.responses import RedirectResponse

        captured.update(kw, redirect_uri=redirect_uri)
        return RedirectResponse("https://accounts.google.com/o/oauth2/auth", status_code=302)

    monkeypatch.setattr(get_oauth().google_gmail, "authorize_redirect", fake_redirect)
    api.http.get("/auth/gmail/connect", follow_redirects=False)
    assert captured["access_type"] == "offline"
    assert captured["prompt"] == "consent"
    assert captured["redirect_uri"].endswith("/auth/gmail/callback")
    assert get_oauth().google_gmail.client_kwargs["scope"] == GMAIL_READONLY
