from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Enum as SAEnum
from sqlalchemy import Float, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.enums import AspectRatio, JobStatus, StyleMode

if TYPE_CHECKING:
    from app.models.asset import Asset
    from app.models.character import Character
    from app.models.scene import Scene
    from app.models.user import User


class Job(Base, UUIDMixin, TimestampMixin):
    """One video-generation request and its live state.

    Progress is persisted here (durable, survives page refresh) *and* streamed
    over Redis pub/sub for live SSE — see docs/ARCHITECTURE.md §7.
    """

    __tablename__ = "jobs"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), default="Untitled", nullable=False)
    script: Mapped[str] = mapped_column(Text, nullable=False)

    style: Mapped[StyleMode] = mapped_column(
        SAEnum(StyleMode, native_enum=False), default=StyleMode.CINEMATIC_REALISTIC, nullable=False
    )
    aspect_ratio: Mapped[AspectRatio] = mapped_column(
        SAEnum(AspectRatio, native_enum=False), default=AspectRatio.WIDE, nullable=False
    )

    status: Mapped[JobStatus] = mapped_column(
        SAEnum(JobStatus, native_enum=False), default=JobStatus.PENDING, index=True, nullable=False
    )
    current_stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    progress_pct: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_path: Mapped[str | None] = mapped_column(String(512), nullable=True)

    user: Mapped["User"] = relationship(back_populates="jobs")
    scenes: Mapped[list["Scene"]] = relationship(
        back_populates="job", cascade="all, delete-orphan", lazy="selectin", order_by="Scene.index"
    )
    assets: Mapped[list["Asset"]] = relationship(
        back_populates="job", cascade="all, delete-orphan", lazy="selectin"
    )
    characters: Mapped[list["Character"]] = relationship(
        back_populates="job", cascade="all, delete-orphan", lazy="selectin"
    )
