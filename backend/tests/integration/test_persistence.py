"""Persistence across sessions and single active run (T066, FR-009, FR-039)."""

from tests.integration.helpers import apps, connect, row_tuple, scan


def test_table_survives_sign_out_and_in(login):
    api = login()
    connect(api, "core-journey")
    scan(api)
    before_rows = sorted(map(row_tuple, apps(api)))
    before_me = api.get("/api/me").json()["cycle"]
    assert api.post("/auth/logout").status_code == 204
    assert api.get("/api/me").status_code == 401

    again = login()  # same Google sub, fresh session
    assert sorted(map(row_tuple, apps(again))) == before_rows
    assert again.get("/api/me").json()["cycle"] == before_me


def test_concurrent_scan_is_rejected(login):
    api = login()
    connect(api, "core-journey")
    assert api.post("/api/scans", json={"kind": "initial"}).status_code == 202
    r = api.post("/api/scans", json={"kind": "initial"})
    assert r.status_code == 409 and r.json()["error"] == "scan_in_progress"
