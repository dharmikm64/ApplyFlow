"""Crash-resume and failure semantics (T065, FR-011)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import update

from app.db import get_sessionmaker
from app.jobs.worker import run_until_idle
from app.models import ScanRun
from tests.integration.helpers import apps, connect, row_tuple, scan


def test_resume_after_crash_mid_page(login):
    api = login()
    connect(api, "crash-mid-page-resume")  # page size 2
    api.post("/test/gmail/abort", json={"after_pages": 1})
    assert api.post("/api/scans", json={"kind": "initial"}).status_code == 202
    run_until_idle()

    cur = api.get("/api/scans/current").json()
    assert cur["status"] == "running"  # the "process" died mid-scan
    assert cur["progress"]["listed"] == 2  # first page committed
    assert api.get("/api/me").json()["cycle"]["lastSuccessfulSyncAt"] is None

    # Simulate the heartbeat going stale, then a fresh worker reclaims the run.
    with get_sessionmaker()() as db:
        db.execute(update(ScanRun).values(heartbeat_at=datetime.now(UTC) - timedelta(minutes=5)))
        db.commit()
    api.post("/test/gmail/abort", json={"after_pages": None})
    run_until_idle()

    cur = api.get("/api/scans/current").json()
    assert cur["status"] == "succeeded"
    assert cur["progress"]["listed"] == 8
    rows = sorted(map(row_tuple, apps(api)))
    assert len(rows) == 3  # same result as an uninterrupted scan, no duplicates

    # Compare with a clean run of the same mailbox for another user.
    other = login("sub-bob", "bob@example.test")
    connect(other, "core-journey")
    scan(other)
    assert rows == sorted(map(row_tuple, apps(other)))


def test_failed_run_does_not_advance_last_sync(login):
    api = login()
    connect(api, "core-journey")
    scan(api)
    last = api.get("/api/me").json()["cycle"]["lastSuccessfulSyncAt"]
    api.post("/test/gmail/revoke")
    run = scan(api, "sync")
    assert run["status"] == "failed" and run["failureCode"] == "reconnect_required"
    assert api.get("/api/me").json()["cycle"]["lastSuccessfulSyncAt"] == last
    assert len(apps(api)) == 3  # rows kept
