"""Status and Date Applied derivation (research R11, FR-025..FR-029). Pure function.

Recomputed from ALL of an application's events every time, so the order in which emails are
processed never matters.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime

from app.pipeline.window import local_date

RANK = {"confirmation": 1, "progress": 2, "rejection": 3}
STATUS_OF = {"confirmation": "submitted", "progress": "in_progress", "rejection": "rejected"}


@dataclass(frozen=True)
class EventIn:
    kind: str
    occurred_at: datetime
    stated_applied_date: date | None = None
    message_id: uuid.UUID | None = None


@dataclass
class Conflict:
    type: str  # contradictory_update
    message_id: uuid.UUID | None
    explanation: str


@dataclass
class Derived:
    status: str | None
    date_applied: date | None
    date_source: str  # stated | estimated | unknown
    conflicts: list[Conflict] = field(default_factory=list)


def derive(events: list[EventIn], cycle_tz: str) -> Derived:
    status_events = sorted(
        (e for e in events if e.kind in RANK),
        key=lambda e: (e.occurred_at, RANK[e.kind]),
    )
    conflicts: list[Conflict] = []
    status: str | None = None
    if status_events:
        top = max(status_events, key=lambda e: (RANK[e.kind], e.occurred_at))
        status = STATUS_OF[top.kind]
        rejections = [e for e in status_events if e.kind == "rejection"]
        if rejections:
            last_rejection = max(e.occurred_at for e in rejections)
            for e in status_events:
                if e.kind == "progress" and e.occurred_at > last_rejection:
                    conflicts.append(
                        Conflict(
                            "contradictory_update",
                            e.message_id,
                            "A progress update is dated after a rejection. The status stays "
                            "Rejected until you decide.",
                        )
                    )

    confirmations = [e for e in events if e.kind == "confirmation"]
    stated = sorted(e.stated_applied_date for e in confirmations if e.stated_applied_date)
    if stated:
        return Derived(status, stated[0], "stated", conflicts)
    if confirmations:
        first = min(e.occurred_at for e in confirmations)
        return Derived(status, local_date(first, cycle_tz), "estimated", conflicts)
    return Derived(status, None, "unknown", conflicts)


def explain_date(source: str, date_applied: date | None, first_confirmation: datetime | None, tz: str) -> str:
    if source == "stated" and date_applied:
        return f"Stated in the confirmation email: applied on {date_applied.isoformat()}."
    if source == "estimated" and first_confirmation is not None:
        return (
            "Estimated from the date of the confirmation email "
            f"({local_date(first_confirmation, tz).isoformat()}, {tz}). The email did not state "
            "an application date."
        )
    if source == "user":
        return "Set by you."
    return (
        "Unknown. No confirmation email was found, and dates of progress or rejection emails "
        "are not used as the application date."
    )
