"""Declarative base + shared mixins for all ORM models.

UUID primary keys (portable across Postgres and sqlite-for-tests via SQLAlchemy's
generic ``Uuid`` type) and automatic created/updated timestamps.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class UUIDMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )


class TimestampMixin:
    # Both a Python-side default (so the value is present on the instance right
    # after flush — critical under async, where lazy refresh-on-access fails) and
    # a server_default (so direct/bulk SQL inserts still get a timestamp).
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        server_default=func.now(),
        onupdate=_utcnow,
        nullable=False,
    )
