"""Helpers for scan scenario tests."""

from __future__ import annotations

from datetime import datetime

from app import clock
from app.jobs.worker import run_until_idle
from app.testing.fixture_gmail import load_mailbox


def connect(api, mailbox: str, *, start_date: str | None = None, tz: str | None = None) -> dict:
    box = load_mailbox(mailbox)
    r = api.post("/test/gmail/connect", json={"mailbox": mailbox})
    assert r.status_code == 200, r.text
    r = api.put(
        "/api/cycle",
        json={
            "startDate": start_date or str(box.get("start_date", "2026-09-01")),
            "timezone": tz or box.get("timezone", "America/New_York"),
        },
    )
    assert r.status_code == 200, r.text
    return box


def scan(api, kind: str = "initial") -> dict:
    r = api.post("/api/scans", json={"kind": kind})
    assert r.status_code == 202, r.text
    run_until_idle()
    cur = api.get("/api/scans/current")
    assert cur.status_code == 200
    return cur.json()


def at(iso: str) -> None:
    clock.set_override(datetime.fromisoformat(iso))


def apps(api, **params) -> list[dict]:
    r = api.get("/api/applications", params=params)
    assert r.status_code == 200, r.text
    return r.json()["items"]


def reviews(api) -> list[dict]:
    r = api.get("/api/review-items", params={"state": "pending"})
    assert r.status_code == 200, r.text
    return r.json()["items"]


def row_tuple(a: dict) -> tuple:
    return (a["company"], a["position"], a["status"], a["dateApplied"], a["dateAppliedSource"])
