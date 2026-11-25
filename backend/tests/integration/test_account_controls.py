"""Disconnect Gmail and delete imported data (T087, FR-041/042, SC-008)."""

from __future__ import annotations

from sqlalchemy import func, select

from app.db import get_sessionmaker
from app.jobs.worker import run_until_idle
from app.models import Application, GmailConnection, ProcessedMessage, RecruitingCycle, ReviewItem, ScanRun
from app.testing import fixture_gmail
from tests.integration.helpers import apps, connect, scan


def count(model, user_id) -> int:
    with get_sessionmaker()() as db:
        return db.execute(select(func.count()).select_from(model).where(model.user_id == user_id)).scalar_one()


def test_disconnect_keeps_table_and_removes_credentials(login):
    api = login()
    connect(api, "core-journey")
    scan(api)
    assert api.delete("/api/gmail").status_code == 204
    assert count(GmailConnection, api.user_id) == 0  # SC-008
    assert fixture_gmail.get_state(__import__("uuid").UUID(api.user_id)) is None  # revoked
    assert len(apps(api)) == 3
    assert api.get("/api/me").json()["gmail"] == {"status": "not_connected", "address": None}
    r = api.post("/api/scans", json={"kind": "sync"})
    assert r.status_code == 409 and r.json()["error"] == "gmail_not_connected"


def test_disconnect_during_scan_stops_without_further_gmail_calls(login, monkeypatch):
    api = login()
    connect(api, "crash-mid-page-resume")  # page size 2 -> several pages
    state = fixture_gmail.get_state(__import__("uuid").UUID(api.user_id))
    original = fixture_gmail.FixtureGmailClient.list_message_ids
    marker: dict = {}

    def list_then_disconnect(self, query, page_token, max_results=500):
        page = original(self, query, page_token, max_results)
        if page_token is not None and "at" not in marker:  # second page: user disconnects
            assert api.delete("/api/gmail").status_code == 204
            marker["at"] = len(state.calls)
        return page

    monkeypatch.setattr(fixture_gmail.FixtureGmailClient, "list_message_ids", list_then_disconnect)
    assert api.post("/api/scans", json={"kind": "initial"}).status_code == 202
    run_until_idle()

    run = api.get("/api/scans/current").json()
    assert run["status"] == "failed" and run["failureCode"] == "gmail_disconnected"
    assert len(state.calls) == marker["at"]  # no Gmail request after the disconnect completed
    assert len(apps(api)) >= 1  # rows from the first page are kept
    assert api.get("/api/me").json()["cycle"]["lastSuccessfulSyncAt"] is None


def test_disconnect_cancels_queued_run(login):
    api = login()
    connect(api, "core-journey")
    api.post("/api/scans", json={"kind": "initial"})
    api.delete("/api/gmail")
    run = api.get("/api/scans/current").json()
    assert run["status"] == "failed" and run["failureCode"] == "gmail_disconnected"
    assert run_until_idle() == 0


def test_delete_imported_data(login):
    api = login()
    connect(api, "core-journey")
    scan(api)
    bad = api.delete("/api/data", json={"confirm": "yes"})
    assert bad.status_code == 422
    assert api.delete("/api/data", json={"confirm": "DELETE"}).status_code == 204
    for model in (Application, ReviewItem, ProcessedMessage, ScanRun):
        assert count(model, api.user_id) == 0
    assert count(GmailConnection, api.user_id) == 1
    me = api.get("/api/me").json()
    assert me["gmail"]["status"] == "connected"
    assert me["cycle"]["startDate"] == "2026-09-01" and me["cycle"]["lastSuccessfulSyncAt"] is None
    with get_sessionmaker()() as db:
        assert db.get(RecruitingCycle, __import__("uuid").UUID(api.user_id)).source_gmail_address is None
    # Scanning again rebuilds the same table.
    scan(api)
    assert len(apps(api)) == 3


def test_delete_data_refused_while_scanning(login):
    api = login()
    connect(api, "core-journey")
    api.post("/api/scans", json={"kind": "initial"})
    r = api.delete("/api/data", json={"confirm": "DELETE"})
    assert r.status_code == 409 and r.json()["error"] == "scan_in_progress"
