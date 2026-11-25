"""Processed messages (email evidence), applications, events, and review items."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    ARRAY,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, Timestamps, UUIDPk

CLASSIFICATIONS = (
    "not_recruiting",
    "confirmation",
    "progress",
    "rejection",
    "acknowledgment",
    "offer",
    "withdrawal",
    "job_alert",
    "marketing",
    "invite_to_apply",
    "unclear",
)
APP_STATUSES = ("submitted", "in_progress", "rejected")
DATE_SOURCES = ("stated", "estimated", "unknown", "user")
EVENT_KINDS = (
    "confirmation",
    "progress",
    "rejection",
    "acknowledgment",
    "offer",
    "withdrawal",
    "manual_edit",
    "dismissed",
    "restored",
    "review_resolved",
)
REVIEW_TYPES = (
    "possible_application",
    "ambiguous_match",
    "offer_or_withdrawal",
    "contradictory_update",
    "manual_conflict",
    "missing_field",
)
REVIEW_STATES = ("pending", "resolved", "dismissed")
OVERRIDABLE_FIELDS = ("company", "position", "date_applied", "status")


class ProcessedMessage(UUIDPk, Base):
    __tablename__ = "processed_messages"
    __table_args__ = (
        UniqueConstraint("user_id", "gmail_message_id", name="uq_processed_user_message"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    gmail_message_id: Mapped[str] = mapped_column(Text, nullable=False)
    gmail_thread_id: Mapped[str | None] = mapped_column(Text)
    internal_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    classification: Mapped[str] = mapped_column(
        Enum(*CLASSIFICATIONS, name="message_classification"), nullable=False
    )
    sender: Mapped[str | None] = mapped_column(Text)
    subject: Mapped[str | None] = mapped_column(Text)
    excerpt: Mapped[str | None] = mapped_column(Text)
    extracted: Mapped[dict | None] = mapped_column(JSONB)
    rule_id: Mapped[str | None] = mapped_column(Text)
    dismissed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Application(UUIDPk, Timestamps, Base):
    __tablename__ = "applications"
    __table_args__ = (
        Index("ix_applications_user_company", "user_id", "company_norm"),
        Index("ix_applications_user_req", "user_id", "req_id"),
        Index("ix_applications_user_dismissed", "user_id", "dismissed_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    company: Mapped[str | None] = mapped_column(Text)
    company_norm: Mapped[str | None] = mapped_column(Text)
    position: Mapped[str | None] = mapped_column(Text)
    position_norm: Mapped[str | None] = mapped_column(Text)
    req_id: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Enum(*APP_STATUSES, name="app_status"), nullable=False)
    date_applied: Mapped[date | None] = mapped_column(Date)
    date_applied_source: Mapped[str] = mapped_column(
        Enum(*DATE_SOURCES, name="date_source"), nullable=False, default="unknown"
    )
    overridden_fields: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list, server_default="{}"
    )
    before_cycle: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ApplicationEvent(UUIDPk, Base):
    __tablename__ = "application_events"
    __table_args__ = (
        Index(
            "uq_event_application_message",
            "application_id",
            "message_id",
            unique=True,
            postgresql_where=text("message_id IS NOT NULL"),
        ),
        Index("ix_events_user_app", "user_id", "application_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(Enum(*EVENT_KINDS, name="event_kind"), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("processed_messages.id", ondelete="CASCADE")
    )
    detail: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ReviewItem(UUIDPk, Base):
    __tablename__ = "review_items"
    __table_args__ = (
        UniqueConstraint("user_id", "dedupe_key", name="uq_review_user_dedupe"),
        Index("ix_review_user_state", "user_id", "state"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(Enum(*REVIEW_TYPES, name="review_type"), nullable=False)
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("processed_messages.id", ondelete="CASCADE")
    )
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE")
    )
    candidate_application_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list, server_default="{}"
    )
    suggestion: Mapped[dict] = mapped_column(JSONB, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(
        Enum(*REVIEW_STATES, name="review_state"), nullable=False, default="pending"
    )
    resolution: Mapped[dict | None] = mapped_column(JSONB)
    dedupe_key: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
