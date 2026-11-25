"""Date boundary math (research R5, FR-006/007/008).

The user's start date is inclusive from 00:00 in the cycle's time zone. A run covers
[window_start, window_end) where window_end is the moment the run was created. Gmail is
queried with a ±1-day padded epoch range and the exact boundary is applied in code.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

PADDING_SECONDS = 86_400
SYNC_OVERLAP = timedelta(hours=1)


def window_start_utc(start_date: date, tz: str) -> datetime:
    return datetime.combine(start_date, time.min, ZoneInfo(tz)).astimezone(UTC)


def gmail_query(from_utc: datetime, to_utc: datetime) -> str:
    after = int(from_utc.timestamp()) - PADDING_SECONDS
    before = int(to_utc.timestamp()) + PADDING_SECONDS
    return f"after:{after} before:{before}"


def ms_to_utc(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, UTC)


def in_window(internal_date_ms: int, from_utc: datetime, to_utc: datetime) -> bool:
    ts = ms_to_utc(internal_date_ms)
    return from_utc <= ts < to_utc


def local_date(ts: datetime, tz: str) -> date:
    return ts.astimezone(ZoneInfo(tz)).date()


def _seg(a: datetime, b: datetime) -> dict:
    return {"from": a.isoformat(), "to": b.isoformat()}


def parse_seg(seg: dict) -> tuple[datetime, datetime]:
    return datetime.fromisoformat(seg["from"]), datetime.fromisoformat(seg["to"])


def segments_for_run(
    *,
    start_date: date,
    tz: str,
    covered_from: datetime | None,
    covered_to: datetime | None,
    now: datetime,
    kind: str,
) -> list[dict]:
    """Ordered [{from, to}] ranges a run must list.

    initial: [start, now).
    sync:    back-fill [start, covered_from) if the start date moved earlier, then
             [covered_to - 1h, now) so late-listed mail is not missed (duplicates are skipped
             by the processed_messages idempotency key).
    """
    start = window_start_utc(start_date, tz)
    if kind == "initial" or covered_to is None:
        return [_seg(start, now)] if start < now else []
    segs: list[dict] = []
    if covered_from is not None and start < covered_from:
        segs.append(_seg(start, covered_from))
    sync_from = max(start, covered_to - SYNC_OVERLAP)
    if sync_from < now:
        segs.append(_seg(sync_from, now))
    return segs
