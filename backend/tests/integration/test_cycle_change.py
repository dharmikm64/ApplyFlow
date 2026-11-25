"""Changing the recruiting start date (T089, FR-043)."""

from __future__ import annotations

from sqlalchemy import select

from app.db import get_sessionmaker
from app.models import ProcessedMessage
from tests.integration.helpers import apps, connect, scan


def test_preview_and_confirm_later_start_date(login):
    api = login()
    connect(api, "core-journey")
    scan(api)
    p = api.get("/api/cycle/preview-change", params={"startDate": "2026-09-08"}).json()
    # Acme PM (Sep 6 only) is entirely before Sep 8; SWE and Globex have later emails.
    assert p["direction"] == "later" and p["rowsMarkedBeforeCycle"] == 1 and p["rowsDeleted"] == 0

    r = api.put("/api/cycle", json={"startDate": "2026-09-08", "timezone": "America/New_York"})
    assert r.status_code == 409 and r.json()["error"] == "confirm_required"
    r = api.put("/api/cycle", json={"startDate": "2026-09-08", "timezone": "America/New_York", "confirm": True})
    assert r.status_code == 200
    rows = apps(api)
    assert len(rows) == 3  # nothing deleted
    flagged = {(a["company"], a["position"]) for a in rows if a["beforeCycle"]}
    assert flagged == {("Acme Robotics", "Product Manager")}


def test_earlier_start_date_backfills_padding_messages(login):
    api = login()
    connect(api, "tz-boundaries")  # start Sep 1 NY
    scan(api)
    assert {a["company"] for a in apps(api)} == {"Nakatomi Trading", "Oscorp"}
    # The message 1 s before the start was listed (±1-day padding) but must NOT be recorded.
    with get_sessionmaker()() as db:
        ids = set(db.execute(select(ProcessedMessage.gmail_message_id)).scalars())
    assert "fx-before-start-boundary" not in ids

    p = api.get("/api/cycle/preview-change", params={"startDate": "2026-08-31"}).json()
    assert p["direction"] == "earlier" and p["willScanAddedPeriod"] is True and p["rowsDeleted"] == 0
    api.put("/api/cycle", json={"startDate": "2026-08-31", "timezone": "America/New_York", "confirm": True})
    scan(api, "sync")
    assert {a["company"] for a in apps(api)} == {"Nakatomi Trading", "Oscorp", "Gringotts"}


def test_first_time_set_needs_no_confirm_and_validates(login):
    api = login()
    r = api.put("/api/cycle", json={"startDate": "2030-01-01", "timezone": "UTC"})
    assert r.status_code == 422 and r.json()["error"] == "start_date_in_future"
    r = api.put("/api/cycle", json={"startDate": "2026-09-01", "timezone": "Mars/Olympus"})
    assert r.status_code == 422 and r.json()["error"] == "invalid_timezone"
    r = api.put("/api/cycle", json={"startDate": "2026-09-01", "timezone": "Europe/London"})
    assert r.status_code == 200 and r.json()["timezone"] == "Europe/London"
