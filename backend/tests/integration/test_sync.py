"""Sync behavior: idempotency, status chronology, overlap window (T064)."""

from __future__ import annotations

from sqlalchemy import func, select

from app.db import get_sessionmaker
from app.models import ApplicationEvent, ReviewItem
from tests.integration.helpers import apps, at, connect, row_tuple, scan


def counts(user_id):
    with get_sessionmaker()() as db:
        ev = db.execute(select(func.count()).select_from(ApplicationEvent).where(ApplicationEvent.user_id == user_id)).scalar_one()
        rv = db.execute(select(func.count()).select_from(ReviewItem).where(ReviewItem.user_id == user_id)).scalar_one()
    return ev, rv


def pending_types(user_id):
    with get_sessionmaker()() as db:
        return sorted(db.execute(select(ReviewItem.type).where(ReviewItem.user_id == user_id, ReviewItem.state == "pending")).scalars())


def test_same_scan_twice_is_identical(login):
    api = login()
    connect(api, "core-journey")
    scan(api)
    before = (sorted(map(row_tuple, apps(api))), counts(api.user_id))
    scan(api, "initial")
    scan(api, "sync")
    after = (sorted(map(row_tuple, apps(api))), counts(api.user_id))
    assert before == after


def test_sync_new_interview_moves_to_in_progress(login):
    api = login()
    connect(api, "sync-new-mail")
    scan(api)
    assert [a["status"] for a in apps(api)] == ["submitted"]
    at("2026-10-10T00:00:00+00:00")
    api.post("/test/gmail/append", json={"messages": ["fx-new-interview-oct"]})
    run = scan(api, "sync")
    assert run["kind"] == "sync" and run["status"] == "succeeded"
    rows = apps(api)
    assert len(rows) == 1
    assert rows[0]["status"] == "in_progress"
    assert run["results"]["updatedApps"] == 1 and run["results"]["createdApps"] == 0


def test_old_confirmation_found_later_keeps_rejected(login):
    api = login()
    connect(api, "out-of-order-confirmation")  # start Sep 10: only the rejection is in range
    scan(api)
    rows = apps(api)
    assert [(r["status"], r["dateApplied"]) for r in rows] == [("rejected", None)]
    # Move the start date earlier: the back-fill finds the Sep 4 confirmation.
    r = api.put("/api/cycle", json={"startDate": "2026-09-01", "timezone": "America/New_York", "confirm": True})
    assert r.status_code == 200
    scan(api, "sync")
    rows = apps(api)
    assert len(rows) == 1
    assert (rows[0]["status"], rows[0]["dateApplied"], rows[0]["dateAppliedSource"]) == ("rejected", "2026-09-04", "estimated")


def test_ack_after_interview_keeps_in_progress(login):
    api = login()
    connect(api, "ack-after-interview")
    scan(api)
    assert apps(api)[0]["status"] == "in_progress"
    at("2026-10-10T00:00:00+00:00")
    api.post("/test/gmail/append", json={"messages": ["fx-acme-swe-ack-oct"]})
    scan(api, "sync")
    assert apps(api)[0]["status"] == "in_progress"


def test_progress_after_rejection_creates_review_and_stays_rejected(login):
    api = login()
    connect(api, "progress-after-rejection")
    scan(api)
    at("2026-10-10T00:00:00+00:00")
    api.post("/test/gmail/append", json={"messages": ["fx-acme-late-progress-oct"]})
    scan(api, "sync")
    rows = apps(api)
    assert len(rows) == 1 and rows[0]["status"] == "rejected"
    assert pending_types(api.user_id) == ["contradictory_update"]


def test_sync_window_overlaps_previous_end_by_one_hour(login):
    api = login()
    connect(api, "late-arrival")
    first = scan(api)  # covered_to = 2026-10-01T00:00Z
    assert first["windowEnd"].startswith("2026-10-01T00:00")
    # A message dated 30 min before the previous end that only became visible now.
    api.post("/test/gmail/append", json={"messages": ["fx-late-arrival"]})
    at("2026-10-02T00:00:00+00:00")
    run = scan(api, "sync")
    assert run["windowStart"].startswith("2026-09-30T23:00")
    assert {a["company"] for a in apps(api)} == {"Acme Robotics", "Massive Dynamic"}
    # Already-processed messages in the overlap create nothing new.
    ev, rv = counts(api.user_id)
    at("2026-10-02T00:30:00+00:00")
    scan(api, "sync")
    assert counts(api.user_id) == (ev, rv)
