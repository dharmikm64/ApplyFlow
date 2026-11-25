import uuid
from datetime import UTC, datetime

from app.pipeline.matching import (
    Candidate,
    Incoming,
    match,
    normalize_company,
    normalize_position,
)

T0 = datetime(2026, 9, 10, tzinfo=UTC)


def cand(company="Acme Robotics", position="Software Engineer", req=None, **kw) -> Candidate:
    return Candidate(
        id=uuid.uuid4(),
        company_norm=normalize_company(company),
        position_norm=normalize_position(position),
        req_id=req,
        **kw,
    )


def inc(company="Acme Robotics", position="Software Engineer", req=None, kind="progress",
        when=T0, domain="greenhouse.io", thread=None) -> Incoming:
    return Incoming(kind=kind, company=company, position=position, req_id=req,
                    occurred_at=when, sender_domain=domain, thread_id=thread)


def test_normalization():
    assert normalize_company("The Acme Robotics, Inc.") == "acme robotics"
    assert normalize_company("Globex Corporation") == "globex"
    assert normalize_position("Sr. SWE (R-12345)") == "senior software engineer"
    assert normalize_position("Software Engineer II") == "software engineer 2"


def test_same_req_id_is_existing():
    c = cand(req="R-1")
    r = match(inc(position="Something Else", req="r-1"), [c])
    assert (r.outcome, r.application_id) == ("existing", c.id)


def test_different_req_ids_are_new():
    c = cand(req="R-1")
    r = match(inc(req="R-2"), [c])
    assert r.outcome == "new"


def test_same_company_and_position_is_existing():
    c = cand()
    r = match(inc(company="ACME ROBOTICS INC", position="software engineer"), [c])
    assert (r.outcome, r.application_id) == ("existing", c.id)


def test_two_positions_same_company_are_separate():
    c = cand(position="Software Engineer")
    r = match(inc(position="Product Manager", kind="confirmation"), [c])
    assert r.outcome == "new"


def test_company_only_one_candidate_same_sender_is_existing():
    c = cand(sender_domains={"greenhouse.io"})
    r = match(inc(position=None, kind="rejection"), [c])
    assert (r.outcome, r.application_id) == ("existing", c.id)


def test_company_only_one_candidate_other_sender_is_ambiguous():
    c = cand(sender_domains={"greenhouse.io"})
    r = match(inc(position=None, domain="acme.example"), [c])
    assert r.outcome == "ambiguous"
    assert r.candidates == [c.id]


def test_company_only_several_candidates_is_ambiguous():
    a, b = cand(position="Software Engineer"), cand(position="Product Manager")
    r = match(inc(position=None), [a, b])
    assert r.outcome == "ambiguous"
    assert set(r.candidates) == {a.id, b.id}


def test_similar_positions_are_ambiguous():
    c = cand(position="Senior Software Engineer Platform")
    r = match(inc(position="Senior Software Engineer"), [c])
    assert r.outcome == "ambiguous"


def test_thread_alone_is_never_sufficient():
    c = cand(position="Software Engineer", thread_ids={"th-1"})
    r = match(inc(position="Product Manager", thread="th-1", kind="confirmation"), [c])
    assert r.outcome == "new"


def test_no_company_requires_thread_and_sender():
    c = cand(thread_ids={"th-1"}, sender_domains={"greenhouse.io"})
    assert match(inc(company=None, thread="th-1"), [c]).outcome == "existing"
    assert match(inc(company=None, thread="th-1", domain="other.example"), [c]).outcome == "unmatchable"
    assert match(inc(company=None, thread=None), [c]).outcome == "unmatchable"


def test_confirmation_after_rejection_is_possible_reapplication():
    c = cand(rejected_at=datetime(2026, 9, 1, tzinfo=UTC))
    r = match(inc(kind="confirmation", when=datetime(2026, 10, 1, tzinfo=UTC)), [c])
    assert r.outcome == "ambiguous"


def test_old_confirmation_before_rejection_matches():
    c = cand(rejected_at=datetime(2026, 9, 20, tzinfo=UTC))
    r = match(inc(kind="confirmation", when=datetime(2026, 9, 1, tzinfo=UTC)), [c])
    assert r.outcome == "existing"


def test_new_company():
    assert match(inc(company="Hooli"), [cand()]).outcome == "new"
