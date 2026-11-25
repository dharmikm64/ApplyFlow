"""Evidence, corrections, and the review area (T072, FR-034..FR-038, SC-009)."""

from __future__ import annotations

from tests.integration.helpers import apps, at, connect, reviews, scan


def find(rows, company, position=None):
    return next(r for r in rows if r["company"] == company and (position is None or r["position"] == position))


def test_detail_shows_chronological_evidence_and_date_explanation(login):
    api = login()
    connect(api, "core-journey")
    scan(api)
    swe = find(apps(api), "Acme Robotics", "Software Engineer")
    d = api.get(f"/api/applications/{swe['id']}").json()
    kinds = [e["kind"] for e in d["events"]]
    assert kinds == ["confirmation", "progress", "rejection"]
    times = [e["occurredAt"] for e in d["events"]]
    assert times == sorted(times)
    ev = d["events"][0]["evidence"]
    assert ev["sender"].startswith("Acme Robotics") and ev["subject"]
    assert "applying" in ev["excerpt"].lower() and len(ev["excerpt"]) <= 300
    assert "Estimated from the date of the confirmation email" in d["dateAppliedExplanation"]

    globex = find(apps(api), "Globex")
    d = api.get(f"/api/applications/{globex['id']}").json()
    assert d["dateAppliedExplanation"].startswith("Unknown")


def test_manual_edits_are_recorded_and_validated(login):
    api = login()
    connect(api, "core-journey")
    scan(api)
    pm = find(apps(api), "Acme Robotics", "Product Manager")
    r = api.patch(f"/api/applications/{pm['id']}", json={
        "company": "Acme Robotics Inc", "position": "Senior Product Manager",
        "dateApplied": "2026-09-05", "status": "in_progress",
    })
    assert r.status_code == 200, r.text
    a = r.json()["application"]
    assert (a["company"], a["position"], a["dateApplied"], a["dateAppliedSource"], a["status"]) == (
        "Acme Robotics Inc", "Senior Product Manager", "2026-09-05", "user", "in_progress")
    assert set(a["overriddenFields"]) == {"company", "position", "date_applied", "status"}
    edits = [e for e in r.json()["events"] if e["kind"] == "manual_edit"]
    assert {e["detail"]["field"] for e in edits} == {"company", "position", "date_applied", "status"}
    assert r.json()["dateAppliedExplanation"] == "Set by you."

    bad = api.patch(f"/api/applications/{pm['id']}", json={"status": "offer"})
    assert bad.status_code == 422
    bad = api.patch(f"/api/applications/{pm['id']}", json={"status": None})
    assert bad.status_code == 422


def test_manual_correction_survives_sync_and_conflict_goes_to_review(login):
    api = login()
    connect(api, "manual-correction-then-sync")
    scan(api)
    row = apps(api)[0]
    api.patch(f"/api/applications/{row['id']}", json={"status": "rejected", "company": "ACME Robotics"})
    at("2026-10-10T00:00:00+00:00")
    api.post("/test/gmail/append", json={"messages": ["fx-new-interview-oct"]})
    scan(api, "sync")
    rows = apps(api)
    assert len(rows) == 1
    assert rows[0]["status"] == "rejected"  # user's value kept (SC-009)
    assert rows[0]["company"] == "ACME Robotics"
    items = reviews(api)
    assert [i["type"] for i in items] == ["manual_conflict"]
    assert items[0]["suggestion"] == {"action": "apply", "field": "status", "value": "in_progress"}

    # Applying the suggestion is the user's decision.
    r = api.post(f"/api/review-items/{items[0]['id']}/resolve", json={"action": "apply"})
    assert r.status_code == 200
    assert apps(api)[0]["status"] == "in_progress"
    assert reviews(api) == []
    # A resolved item can't be resolved twice and never comes back.
    assert api.post(f"/api/review-items/{items[0]['id']}/resolve", json={"action": "dismiss"}).status_code == 409
    scan(api, "initial")
    assert reviews(api) == []


def test_offer_and_ambiguous_items_stay_out_of_the_table(login):
    api = login()
    connect(api, "ambiguous-company-only")
    scan(api)
    rows = apps(api)
    assert len(rows) == 2 and {r["status"] for r in rows} == {"submitted"}
    items = reviews(api)
    assert [i["type"] for i in items] == ["ambiguous_match"]
    assert len(items[0]["candidates"]) == 2
    assert items[0]["evidence"]["subject"] == "Update on your application"

    # Attach it to the Software Engineer application.
    swe = find(rows, "Acme Robotics", "Software Engineer")
    r = api.post(f"/api/review-items/{items[0]['id']}/resolve", json={"action": "attach", "applicationId": swe["id"]})
    assert r.status_code == 200
    assert find(apps(api), "Acme Robotics", "Software Engineer")["status"] == "rejected"
    assert find(apps(api), "Acme Robotics", "Product Manager")["status"] == "submitted"
    scan(api, "initial")
    assert reviews(api) == []


def test_offer_review_item_dismiss(login):
    api = login()
    connect(api, "core-journey")
    scan(api)
    items = reviews(api)
    assert [i["type"] for i in items] == ["offer_or_withdrawal"]
    assert "Offers and withdrawals" in items[0]["explanation"]
    api.post(f"/api/review-items/{items[0]['id']}/resolve", json={"action": "dismiss"})
    assert reviews(api) == []
    assert {r["status"] for r in apps(api)} <= {"submitted", "in_progress", "rejected"}


def test_create_from_possible_application(login):
    api = login()
    connect(api, "reapply-after-rejection")
    at("2026-10-10T00:00:00+00:00")
    scan(api)
    rows = apps(api)
    assert len(rows) == 1 and rows[0]["status"] == "rejected"
    items = reviews(api)
    assert [i["type"] for i in items] == ["ambiguous_match"]
    r = api.post(f"/api/review-items/{items[0]['id']}/resolve",
                 json={"action": "create", "fields": {"company": "Acme Robotics", "position": "Software Engineer"}})
    assert r.status_code == 200
    rows = apps(api)
    assert len(rows) == 2
    assert sorted(r["status"] for r in rows) == ["rejected", "submitted"]
    new = next(r for r in rows if r["status"] == "submitted")
    assert new["dateApplied"] == "2026-10-05"


def test_missing_position_creates_row_and_review(login):
    api = login()
    connect(api, "missing-position")
    scan(api)
    rows = apps(api)
    assert len(rows) == 1 and rows[0]["company"] == "Soylent Corp" and rows[0]["position"] is None
    items = reviews(api)
    assert [i["type"] for i in items] == ["missing_field"]
    api.post(f"/api/review-items/{items[0]['id']}/resolve", json={"action": "apply", "fields": {"position": "Nutrition Analyst"}})
    assert apps(api)[0]["position"] == "Nutrition Analyst"


def test_shared_thread_and_req_ids_stay_separate(login):
    api = login()
    connect(api, "shared-thread-two-positions")
    scan(api)
    assert sorted(r["position"] for r in apps(api)) == ["Product Manager", "Software Engineer"]
    bob = login("sub-bob", "bob@example.test")
    connect(bob, "req-id-split")
    scan(bob)
    rows = apps(bob)
    assert len(rows) == 2 and {r["position"] for r in rows} == {"Data Analyst"}
