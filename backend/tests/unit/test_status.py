import itertools
from datetime import UTC, date, datetime

from app.pipeline.status import EventIn, derive

TZ = "America/New_York"


def ev(kind, day, hour=12, stated=None):
    return EventIn(kind=kind, occurred_at=datetime(2026, 9, day, hour, tzinfo=UTC), stated_applied_date=stated)


def test_confirm_interview_reject_is_rejected_in_any_order():
    events = [ev("confirmation", 3), ev("progress", 10), ev("rejection", 20)]
    for perm in itertools.permutations(events):
        d = derive(list(perm), TZ)
        assert d.status == "rejected"
        assert d.date_applied == date(2026, 9, 3)
        assert d.date_source == "estimated"
        assert d.conflicts == []


def test_old_confirmation_never_lowers_status():
    d = derive([ev("rejection", 20), ev("confirmation", 3)], TZ)
    assert d.status == "rejected"
    d = derive([ev("progress", 10), ev("confirmation", 3)], TZ)
    assert d.status == "in_progress"


def test_acknowledgment_never_changes_status():
    d = derive([ev("progress", 10), ev("acknowledgment", 15)], TZ)
    assert d.status == "in_progress"


def test_offer_and_withdrawal_never_change_status():
    d = derive([ev("confirmation", 3), ev("offer", 25), ev("withdrawal", 26)], TZ)
    assert d.status == "submitted"


def test_progress_after_rejection_is_conflict_and_stays_rejected():
    d = derive([ev("confirmation", 3), ev("rejection", 10), ev("progress", 15)], TZ)
    assert d.status == "rejected"
    assert len(d.conflicts) == 1
    assert d.conflicts[0].type == "contradictory_update"


def test_stated_date_wins():
    d = derive([ev("confirmation", 5, stated=date(2026, 9, 2))], TZ)
    assert (d.date_applied, d.date_source) == (date(2026, 9, 2), "stated")


def test_estimated_date_uses_earliest_confirmation_in_cycle_timezone():
    # 03:30 UTC on Sep 4 is 23:30 on Sep 3 in New York.
    d = derive([ev("confirmation", 4, hour=3), ev("confirmation", 9)], TZ)
    assert (d.date_applied, d.date_source) == (date(2026, 9, 3), "estimated")
    d_utc = derive([ev("confirmation", 4, hour=3)], "UTC")
    assert d_utc.date_applied == date(2026, 9, 4)


def test_rejection_only_has_unknown_date():
    d = derive([ev("rejection", 12)], TZ)
    assert (d.status, d.date_applied, d.date_source) == ("rejected", None, "unknown")


def test_progress_only_has_unknown_date():
    d = derive([ev("progress", 12)], TZ)
    assert (d.status, d.date_applied, d.date_source) == ("in_progress", None, "unknown")
