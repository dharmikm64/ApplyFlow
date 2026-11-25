"""User lookups. Users are identified by Google's stable `sub`, never by email."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.models import User


def get_or_create_by_sub(
    db: DbSession, *, sub: str, email: str, display_name: str | None
) -> User:
    user = db.execute(select(User).where(User.google_sub == sub)).scalar_one_or_none()
    if user is None:
        user = User(google_sub=sub, email=email, display_name=display_name)
        db.add(user)
    else:
        user.email = email
        user.display_name = display_name
    db.flush()
    return user
