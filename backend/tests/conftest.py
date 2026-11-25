"""Shared test setup: APP_ENV=test against the *_test database, fixture Gmail, helpers.

Isolation: all tables are truncated before each test (the app opens its own DB sessions in
OAuth handlers and the worker, so per-test transaction rollback would not cover them).
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

os.environ["APP_ENV"] = "test"
os.environ["WORKER_MODE"] = "off"
os.environ.setdefault("TOKEN_ENCRYPTION_KEYS", Fernet.generate_key().decode())
os.environ["ALLOWED_GOOGLE_EMAILS"] = "alice@example.test,bob@example.test"
os.environ["SESSION_SECRET"] = "test-session-secret-value"
os.environ["GOOGLE_CLIENT_ID"] = "test-client-id"
os.environ["GOOGLE_CLIENT_SECRET"] = "test-client-secret"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app import clock  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import get_engine  # noqa: E402
from app.testing import fixture_gmail  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1]
TABLES = (
    "review_items, application_events, applications, processed_messages, scan_runs, "
    "recruiting_cycles, gmail_connections, sessions, users"
)


@pytest.fixture(scope="session", autouse=True)
def _migrate() -> None:
    env = {**os.environ, "APP_ENV": "test"}
    for args in (["downgrade", "base"], ["upgrade", "head"]):
        subprocess.run(
            [sys.executable, "-m", "alembic", *args],
            cwd=BACKEND,
            env=env,
            check=True,
            capture_output=True,
        )


FIXED_NOW = datetime(2026, 10, 1, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _clean_db() -> Iterator[None]:
    with get_engine().begin() as conn:
        conn.execute(text(f"TRUNCATE {TABLES} CASCADE"))
    fixture_gmail.reset_registry()
    clock.set_override(FIXED_NOW)
    yield
    clock.set_override(None)


@pytest.fixture(scope="session")
def app():
    assert get_settings().APP_ENV == "test"
    from app.main import app as fastapi_app

    return fastapi_app


@dataclass
class ApiClient:
    """A TestClient bound to one signed-in synthetic user."""

    http: TestClient
    csrf: str
    user_id: str

    def _h(self, extra: dict | None = None) -> dict:
        return {"X-CSRF-Token": self.csrf, **(extra or {})}

    def get(self, url: str, **kw):
        return self.http.get(url, **kw)

    def post(self, url: str, json: dict | None = None, **kw):
        return self.http.post(url, json=json, headers=self._h(kw.pop("headers", None)), **kw)

    def put(self, url: str, json: dict | None = None, **kw):
        return self.http.put(url, json=json, headers=self._h(kw.pop("headers", None)), **kw)

    def patch(self, url: str, json: dict | None = None, **kw):
        return self.http.patch(url, json=json, headers=self._h(kw.pop("headers", None)), **kw)

    def delete(self, url: str, json: dict | None = None, **kw):
        return self.http.request(
            "DELETE", url, json=json, headers=self._h(kw.pop("headers", None)), **kw
        )


@pytest.fixture
def client(app) -> Iterator[TestClient]:
    with TestClient(app, base_url="http://localhost:5173") as c:
        yield c


@pytest.fixture
def login(app):
    """login(sub, email) -> ApiClient with its own cookie jar."""
    opened: list[TestClient] = []

    def _login(sub: str = "sub-alice", email: str = "alice@example.test") -> ApiClient:
        c = TestClient(app, base_url="http://localhost:5173")
        c.__enter__()
        opened.append(c)
        r = c.post("/test/login", json={"sub": sub, "email": email})
        assert r.status_code == 200, r.text
        body = r.json()
        return ApiClient(http=c, csrf=body["csrfToken"], user_id=body["userId"])

    yield _login
    for c in opened:
        c.__exit__(None, None, None)
