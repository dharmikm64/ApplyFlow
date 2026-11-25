"""User isolation on every user-data route (T040, FR-040, SC-006).

For each route, the owner first gets a success (proving the route exists and the resource is
real), then the other user gets a 404 identical to "does not exist".
"""

from __future__ import annotations

import uuid

from tests.integration.helpers import apps, connect, reviews, scan


def two_users(login):
    alice = login("sub-alice", "alice@example.test")
    bob = login("sub-bob", "bob@example.test")
    connect(alice, "core-journey")
    scan(alice)
    connect(bob, "bob-mailbox")
    scan(bob)
    return alice, bob


def test_lists_never_include_other_users_rows(login):
    alice, bob = two_users(login)
    assert {a["company"] for a in apps(alice)} == {"Acme Robotics", "Globex"}
    assert {a["company"] for a in apps(bob)} == {"Pied Piper"}
    assert reviews(bob) == []
    assert len(reviews(alice)) == 1
    assert apps(bob, view="dismissed") == []


def test_application_routes_return_404_for_other_user(login):
    alice, bob = two_users(login)
    app_id = apps(alice)[0]["id"]

    assert alice.get(f"/api/applications/{app_id}").status_code == 200
    for r in (
        bob.get(f"/api/applications/{app_id}"),
        bob.patch(f"/api/applications/{app_id}", json={"company": "Hacked"}),
        bob.post(f"/api/applications/{app_id}/dismiss"),
        bob.post(f"/api/applications/{app_id}/restore"),
    ):
        assert r.status_code == 404, r.text
        assert r.json() == {"error": "not_found", "message": "Not found."}

    # Identical to a random nonexistent ID: reveals nothing about existence.
    missing = bob.get(f"/api/applications/{uuid.uuid4()}")
    assert missing.status_code == 404 and missing.json() == {"error": "not_found", "message": "Not found."}
    assert alice.get(f"/api/applications/{app_id}").json()["application"]["company"] != "Hacked"


def test_review_routes_return_404_for_other_user(login):
    alice, bob = two_users(login)
    item_id = reviews(alice)[0]["id"]
    r = bob.post(f"/api/review-items/{item_id}/resolve", json={"action": "dismiss"})
    assert r.status_code == 404
    assert len(reviews(alice)) == 1  # untouched


def test_scan_state_is_per_user(login):
    alice, bob = two_users(login)
    a = alice.get("/api/scans/current").json()
    b = bob.get("/api/scans/current").json()
    assert a["id"] != b["id"]
    assert a["results"]["createdApps"] == 3 and b["results"]["createdApps"] == 1


def test_account_controls_affect_only_self(login):
    alice, bob = two_users(login)
    assert bob.delete("/api/data", json={"confirm": "DELETE"}).status_code == 204
    assert apps(bob) == []
    assert len(apps(alice)) == 3
