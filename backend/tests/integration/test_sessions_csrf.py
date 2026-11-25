from app.auth.google import get_oauth


def test_me_requires_session(client):
    r = client.get("/api/me")
    assert r.status_code == 401
    assert r.json()["error"] == "unauthenticated"


def test_me_returns_user_and_csrf(login):
    alice = login()
    r = alice.get("/api/me")
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["email"] == "alice@example.test"
    assert body["csrfToken"] == alice.csrf
    assert body["gmail"] == {"status": "not_connected", "address": None}
    assert body["cycle"]["startDate"] is None


def test_mutation_without_csrf_is_rejected(login):
    alice = login()
    r = alice.http.post("/auth/logout")
    assert r.status_code == 403
    assert r.json()["error"] == "csrf"
    r = alice.http.post("/auth/logout", headers={"X-CSRF-Token": "wrong"})
    assert r.status_code == 403


def test_logout_invalidates_session(login):
    alice = login()
    assert alice.post("/auth/logout").status_code == 204
    assert alice.get("/api/me").status_code == 401


def _stub_token(monkeypatch, userinfo):
    google = get_oauth().google

    async def fake_authorize_access_token(request, **kwargs):
        return {"access_token": "x", "userinfo": userinfo}

    monkeypatch.setattr(google, "authorize_access_token", fake_authorize_access_token)


def test_callback_rejects_account_not_on_allowlist(client, monkeypatch):
    _stub_token(
        monkeypatch,
        {"sub": "s-mallory", "email": "mallory@example.test", "email_verified": True},
    )
    r = client.get("/auth/callback?code=c&state=s", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/?error=not_allowed"
    assert "af_session" not in r.cookies


def test_callback_signs_in_allowlisted_account(client, monkeypatch):
    _stub_token(
        monkeypatch,
        {"sub": "s-alice", "email": "Alice@example.test", "email_verified": True, "name": "Alice"},
    )
    r = client.get("/auth/callback?code=c&state=s", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/"
    cookie = r.headers["set-cookie"].lower()
    assert "af_session=" in cookie and "httponly" in cookie and "samesite=lax" in cookie
    me = client.get("/api/me")
    assert me.status_code == 200
    assert me.json()["user"]["displayName"] == "Alice"


def test_callback_user_cancelled(client):
    r = client.get("/auth/callback?error=access_denied", follow_redirects=False)
    assert r.headers["location"] == "/?error=signin_cancelled"
