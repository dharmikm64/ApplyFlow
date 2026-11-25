"""Clock with a test-only override (set only via the APP_ENV=test /test/clock route or tests)."""

from __future__ import annotations

from datetime import UTC, datetime

_override: datetime | None = None


def now() -> datetime:
    return _override if _override is not None else datetime.now(UTC)


def set_override(value: datetime | None) -> None:
    global _override
    _override = value
