"""User-scoping helpers (Constitution III, FR-040).

Every repository function takes `user_id` as a required keyword argument and filters by it.
There are deliberately no unscoped finders for user-owned tables.
"""

from __future__ import annotations

import uuid
from typing import TypeVar

from sqlalchemy import Select, select
from sqlalchemy.orm import Session as DbSession

from app.api.errors import not_found

T = TypeVar("T")


def scoped(model: type[T], *, user_id: uuid.UUID) -> Select[tuple[T]]:
    if user_id is None:  # defensive: never allow an unscoped query
        raise ValueError("user_id is required")
    return select(model).where(model.user_id == user_id)  # type: ignore[attr-defined]


def get_owned(db: DbSession, model: type[T], obj_id: uuid.UUID | str, *, user_id: uuid.UUID) -> T:
    """Fetch one row owned by user_id, or raise the uniform 404."""
    try:
        oid = obj_id if isinstance(obj_id, uuid.UUID) else uuid.UUID(str(obj_id))
    except ValueError as exc:
        raise not_found() from exc
    row = db.execute(
        scoped(model, user_id=user_id).where(model.id == oid)  # type: ignore[attr-defined]
    ).scalar_one_or_none()
    if row is None:
        raise not_found()
    return row
