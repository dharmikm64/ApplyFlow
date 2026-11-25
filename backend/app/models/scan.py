"""Recruiting cycles and scan runs (data-model.md)."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Index, Integer, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, UUIDPk

SCAN_KINDS = ("initial", "sync")
SCAN_STATUSES = ("queued", "running", "succeeded", "failed")
FAILURE_CODES = (
    "reconnect_required",
    "gmail_disconnected",
    "gmail_unavailable",
    "internal_error",
)


class RecruitingCycle(Base):
    __tablename__ = "recruiting_cycles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    timezone: Mapped[str] = mapped_column(Text, nullable=False)
    source_gmail_address: Mapped[str | None] = mapped_column(Text)
    covered_from_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    covered_to_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ScanRun(UUIDPk, Base):
    __tablename__ = "scan_runs"
    __table_args__ = (
        Index(
            "uq_scan_runs_one_active_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running')"),
        ),
        Index("ix_scan_runs_status_heartbeat", "status", "heartbeat_at"),
        Index("ix_scan_runs_user_created", "user_id", "created_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(Enum(*SCAN_KINDS, name="scan_kind"), nullable=False)
    status: Mapped[str] = mapped_column(
        Enum(*SCAN_STATUSES, name="scan_status"), nullable=False, default="queued"
    )
    window_start_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    segments: Mapped[list[dict]] = mapped_column(JSONB, nullable=False)
    segment_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    page_token: Mapped[str | None] = mapped_column(Text)

    listed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    screened: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    candidates: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_apps: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_apps: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    review_items: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estimated_total: Mapped[int | None] = mapped_column(Integer)

    worker_id: Mapped[str | None] = mapped_column(Text)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    failure_code: Mapped[str | None] = mapped_column(Text)
