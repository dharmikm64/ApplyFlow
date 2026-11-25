"""Every US1 fixture mailbox scanned end-to-end through the API (T039, SC-003, SC-004)."""

from __future__ import annotations

import pytest
import yaml
from sqlalchemy import select

from app.db import get_sessionmaker
from app.models import ReviewItem
from app.testing.fixture_gmail import FIXTURES_DIR, load_mailbox
from tests.integration.helpers import apps, connect, row_tuple, scan

SCENARIOS = sorted(
    p.stem
    for p in (FIXTURES_DIR / "mailboxes").glob("*.yaml")
    if "expected" in yaml.safe_load(p.read_text())
)


def expected_rows(box: dict) -> set[tuple]:
    return {
        (a["company"], a["position"], a["status"],
         str(a["date_applied"]) if a.get("date_applied") else None, a["date_source"])
        for a in box["expected"]["applications"]
    }


def review_types(user_id: str) -> list[str]:
    with get_sessionmaker()() as db:
        return sorted(
            db.execute(
                select(ReviewItem.type).where(
                    ReviewItem.user_id == user_id, ReviewItem.state == "pending"
                )
            ).scalars()
        )


@pytest.mark.parametrize("mailbox", SCENARIOS)
def test_mailbox_scenario(login, mailbox):
    api = login()
    box = connect(api, mailbox)
    run = scan(api)
    assert run["status"] == "succeeded", run
    assert {row_tuple(a) for a in apps(api)} == expected_rows(box)
    assert review_types(api.user_id) == sorted(box["expected"]["review_items"])


def test_rescan_creates_no_duplicates(login):
    api = login()
    connect(api, "core-journey")
    scan(api)
    first = sorted(row_tuple(a) for a in apps(api))
    first_reviews = review_types(api.user_id)
    r = api.post("/api/scans", json={"kind": "initial"})
    assert r.status_code == 202
    from app.jobs.worker import run_until_idle

    run_until_idle()
    assert sorted(row_tuple(a) for a in apps(api)) == first
    assert review_types(api.user_id) == first_reviews


def test_progress_counters_and_last_sync(login):
    api = login()
    connect(api, "core-journey")
    run = scan(api)
    assert run["progress"]["listed"] >= 8  # spam is never listed
    assert run["progress"]["candidates"] >= 6
    assert run["results"]["createdApps"] == 3
    me = api.get("/api/me").json()
    assert me["cycle"]["lastSuccessfulSyncAt"] == run["windowEnd"]


def test_scan_requires_connection_and_start_date(login):
    api = login()
    r = api.post("/api/scans", json={"kind": "initial"})
    assert r.status_code == 409 and r.json()["error"] == "gmail_not_connected"
    api.post("/test/gmail/connect", json={"mailbox": "core-journey"})
    r = api.post("/api/scans", json={"kind": "initial"})
    assert r.status_code == 409 and r.json()["error"] == "no_start_date"


def test_only_one_active_scan(login):
    api = login()
    connect(api, "core-journey")
    assert api.post("/api/scans", json={"kind": "initial"}).status_code == 202
    r = api.post("/api/scans", json={"kind": "sync"})
    assert r.status_code == 409
    assert r.json()["error"] == "scan_in_progress"


def test_accuracy_summary_sc003(login):
    """SC-003: >= 90% of expected applications with a confirmation are imported correctly."""
    total = correct = 0
    for i, name in enumerate(SCENARIOS):
        box = load_mailbox(name)
        expected = [
            a for a in box["expected"]["applications"] if a["date_source"] in ("stated", "estimated")
        ]
        if not expected:
            continue
        api = login(sub=f"sc003-{i}", email="alice@example.test")
        connect(api, name)
        scan(api)
        got = {(a["company"], a["position"], a["status"]) for a in apps(api)}
        for a in expected:
            total += 1
            correct += (a["company"], a["position"], a["status"]) in got
    score = 100.0 * correct / total
    print(f"\nSC-003 accuracy: {correct}/{total} = {score:.1f}%")
    assert score >= 90.0
