from datetime import UTC, date, datetime, timedelta

from app.pipeline.window import (
    PADDING_SECONDS,
    gmail_query,
    in_window,
    local_date,
    segments_for_run,
    window_start_utc,
)


def ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def test_start_is_local_midnight_utc_minus():
    start = window_start_utc(date(2026, 9, 1), "America/New_York")
    assert start == datetime(2026, 9, 1, 4, 0, tzinfo=UTC)  # EDT = UTC-4


def test_start_is_local_midnight_utc_plus():
    start = window_start_utc(date(2026, 9, 1), "Asia/Kolkata")
    assert start == datetime(2026, 8, 31, 18, 30, tzinfo=UTC)  # IST = UTC+5:30


def test_start_on_dst_spring_forward_date():
    # 2026-03-08: US clocks jump 02:00 -> 03:00; midnight is still EST (UTC-5).
    start = window_start_utc(date(2026, 3, 8), "America/New_York")
    assert start == datetime(2026, 3, 8, 5, 0, tzinfo=UTC)
    # The next day's midnight is EDT (UTC-4): the boundary math follows the zone rules.
    assert window_start_utc(date(2026, 3, 9), "America/New_York") == datetime(
        2026, 3, 9, 4, 0, tzinfo=UTC
    )


def test_inclusive_start_and_exclusive_end():
    start = window_start_utc(date(2026, 9, 1), "America/New_York")
    end = start + timedelta(days=30)
    assert in_window(ms(start), start, end)
    assert not in_window(ms(start) - 1, start, end)
    assert in_window(ms(end) - 1, start, end)
    assert not in_window(ms(end), start, end)


def test_gmail_query_is_padded_by_a_day():
    a = datetime(2026, 9, 1, 4, tzinfo=UTC)
    b = datetime(2026, 10, 1, 4, tzinfo=UTC)
    q = gmail_query(a, b)
    assert q == f"after:{int(a.timestamp()) - PADDING_SECONDS} before:{int(b.timestamp()) + PADDING_SECONDS}"
    assert "in:inbox" not in q  # archived mail must be included


def test_local_date_uses_cycle_timezone():
    # 23:30 on Sep 3 in New York is already Sep 4 in UTC.
    ts = datetime(2026, 9, 4, 3, 30, tzinfo=UTC)
    assert local_date(ts, "America/New_York") == date(2026, 9, 3)
    assert local_date(ts, "UTC") == date(2026, 9, 4)


def test_initial_segment_covers_start_to_now():
    now = datetime(2026, 10, 1, tzinfo=UTC)
    segs = segments_for_run(
        start_date=date(2026, 9, 1), tz="UTC", covered_from=None, covered_to=None, now=now,
        kind="initial",
    )
    assert segs == [{"from": "2026-09-01T00:00:00+00:00", "to": now.isoformat()}]


def test_sync_overlaps_previous_end_by_one_hour():
    covered_to = datetime(2026, 9, 20, 12, tzinfo=UTC)
    now = datetime(2026, 9, 25, tzinfo=UTC)
    segs = segments_for_run(
        start_date=date(2026, 9, 1), tz="UTC",
        covered_from=datetime(2026, 9, 1, tzinfo=UTC), covered_to=covered_to, now=now, kind="sync",
    )
    assert segs == [{"from": (covered_to - timedelta(hours=1)).isoformat(), "to": now.isoformat()}]


def test_sync_backfills_when_start_moved_earlier():
    covered_from = datetime(2026, 9, 1, tzinfo=UTC)
    covered_to = datetime(2026, 9, 20, tzinfo=UTC)
    now = datetime(2026, 9, 25, tzinfo=UTC)
    segs = segments_for_run(
        start_date=date(2026, 8, 15), tz="UTC", covered_from=covered_from,
        covered_to=covered_to, now=now, kind="sync",
    )
    assert segs[0] == {"from": "2026-08-15T00:00:00+00:00", "to": covered_from.isoformat()}
    assert segs[1]["to"] == now.isoformat()


def test_sync_without_prior_success_acts_like_initial():
    now = datetime(2026, 10, 1, tzinfo=UTC)
    segs = segments_for_run(
        start_date=date(2026, 9, 1), tz="UTC", covered_from=None, covered_to=None, now=now,
        kind="sync",
    )
    assert segs[0]["from"] == "2026-09-01T00:00:00+00:00"
