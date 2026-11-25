"""'Not an application' (T073, FR-038a)."""

from tests.integration.helpers import apps, at, connect, scan


def test_dismiss_hides_persists_and_restores(login):
    api = login()
    connect(api, "dismiss-then-sync")
    scan(api)
    rows = apps(api)
    assert [(r["company"], r["position"]) for r in rows] == [("Example Bank", "Platinum Card")]
    row_id = rows[0]["id"]

    d = api.post(f"/api/applications/{row_id}/dismiss")
    assert d.status_code == 200
    assert apps(api) == []
    assert [r["id"] for r in apps(api, view="dismissed")] == [row_id]

    at("2026-10-10T00:00:00+00:00")
    api.post("/test/gmail/append", json={"messages": ["fx-bank-false-positive-2"]})
    scan(api, "sync")
    assert apps(api) == []  # no new row
    dismissed = apps(api, view="dismissed")
    assert [r["id"] for r in dismissed] == [row_id]
    detail = api.get(f"/api/applications/{row_id}").json()
    assert [e["kind"] for e in detail["events"]].count("confirmation") == 2  # new email attached

    r = api.post(f"/api/applications/{row_id}/restore")
    assert r.status_code == 200
    restored = apps(api)
    assert [x["id"] for x in restored] == [row_id]
    assert (restored[0]["company"], restored[0]["status"]) == ("Example Bank", "submitted")
    assert apps(api, view="dismissed") == []
