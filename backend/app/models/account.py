"""Users, sessions, and Gmail connections (data-model.md)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    ARRAY,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    LargeBinary,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, Timestamps, UUIDPk

GMAIL_STATUSES = ("connected", "revoked", "denied")


class User(UUIDPk, Timestamps, Base):
    __tablename__ = "users"

    google_sub: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str | None] = mapped_column(Text)


class Session(Base):
    __tablename__ = "sessions"

    id_hash: Mapped[bytes] = mapped_column(LargeBinary, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    csrf_token: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class GmailConnection(Base):
    __tablename__ = "gmail_connections"
    __table_args__ = (
        CheckConstraint(
            "(status = 'connected') = (refresh_token_ciphertext IS NOT NULL)",
            name="ck_gmail_connected_has_token",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    gmail_address: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        Enum(*GMAIL_STATUSES, name="gmail_status"), nullable=False
    )
    refresh_token_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    granted_scopes: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, server_default="{}"
    )
    last_error: Mapped[str | None] = mapped_column(Text)
    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
