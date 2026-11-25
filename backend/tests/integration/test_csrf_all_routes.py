"""Every state-changing route requires the CSRF header (T104, constitution security section)."""

from __future__ import annotations

import re
import uuid
from pathlib import Path

MUTATING = {"POST", "PUT", "PATCH", "DELETE"}
# /test/* exist only in APP_ENV=test; /test/login and /test/reset create or wipe sessions by design.
EXEMPT = {"/test/login", "/test/reset"}


def test_every_mutating_route_rejects_missing_csrf(app, login):
    alice = login()
    checked = []
    for path_t, ops in app.openapi()["paths"].items():
        if path_t in EXEMPT:
            continue
        for method in {m.upper() for m in ops} & MUTATING:
            path = re.sub(r"\{[^}]+\}", str(uuid.uuid4()), path_t)
            r = alice.http.request(method, path, json={})
            assert r.status_code == 403, f"{method} {path_t} -> {r.status_code}"
            assert r.json()["error"] == "csrf"
            checked.append(f"{method} {path_t}")
    assert len(checked) >= 12, checked


def test_gmail_client_only_uses_read_only_get_requests():
    src = (Path(__file__).resolve().parents[2] / "app" / "gmail" / "google_client.py").read_text()
    gmail_calls = re.findall(r"self\._http\.(\w+)\(", src)
    # The only POST is the OAuth token refresh; every Gmail API call is a GET.
    assert set(gmail_calls) == {"get", "post"}
    assert src.count("self._http.post(") == 1 and "TOKEN_URL" in src
    for forbidden in ("/send", "/modify", "/trash", "/batchModify", "/batchDelete", "/insert", "/import", "/labels", "/drafts"):
        assert forbidden not in src, forbidden


def test_session_cookie_flags(client, monkeypatch):
    from app.auth.google import get_oauth

    async def fake(request, **kw):
        return {"userinfo": {"sub": "s1", "email": "alice@example.test", "email_verified": True}}

    monkeypatch.setattr(get_oauth().google, "authorize_access_token", fake)
    r = client.get("/auth/callback?code=c&state=s", follow_redirects=False)
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and "path=/" in cookie
