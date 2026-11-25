"""Search, status filter, and date sort (T083, FR-031)."""

from tests.integration.helpers import apps, connect, scan


def setup(login):
    api = login()
    connect(api, "core-journey")
    scan(api)
    return api


def names(rows):
    return [(r["company"], r["position"]) for r in rows]


def test_search_is_case_insensitive_substring_on_company_or_position(login):
    api = setup(login)
    assert {r["position"] for r in apps(api, q="acme")} == {"Software Engineer", "Product Manager"}
    assert names(apps(api, q="ANALYST")) == [("Globex", "Data Analyst")]
    assert names(apps(api, q="manag")) == [("Acme Robotics", "Product Manager")]
    assert apps(api, q="%") == []  # wildcards are literal
    assert apps(api, q="nomatch") == []


def test_status_filter_single_and_multiple(login):
    api = setup(login)
    assert {r["status"] for r in apps(api, status="rejected")} == {"rejected"}
    assert len(apps(api, status="rejected")) == 2
    assert len(apps(api, status=["submitted", "rejected"])) == 3
    assert apps(api, status="in_progress") == []
    assert api.get("/api/applications", params={"status": "offer"}).status_code == 422


def test_sort_by_date_with_unknown_last_in_both_orders(login):
    api = setup(login)
    desc = [r["dateApplied"] for r in apps(api, order="desc")]
    asc = [r["dateApplied"] for r in apps(api, order="asc")]
    assert desc == ["2026-09-06", "2026-09-04", None]
    assert asc == ["2026-09-04", "2026-09-06", None]


def test_combined_search_and_status(login):
    api = setup(login)
    assert names(apps(api, q="acme", status="rejected")) == [("Acme Robotics", "Software Engineer")]


def test_filters_are_user_scoped(login):
    setup(login)
    bob = login("sub-bob", "bob@example.test")
    assert apps(bob, q="acme") == []
