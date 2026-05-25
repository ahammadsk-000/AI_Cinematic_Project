from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.job import Job


class Scene(Base, UUIDMixin, TimestampMixin):
    """A structured beat of the script. Mirrors ai_engine.interfaces.Scene so the
    worker can hydrate the engine dataclass directly from these rows."""

    __tablename__ = "scenes"

    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("jobs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    index: Mapped[int] = mapped_column(Integer, nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    prompt: Mapped[str] = mapped_column(Text, default="", nullable=False)
    negative_prompt: Mapped[str] = mapped_column(Text, default="", nullable=False)
    camera: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    lighting: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    emotion: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    environment: Mapped[str] = mapped_column(Text, default="", nullable=False)
    motion: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    music_mood: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    narration: Mapped[str] = mapped_column(Text, default="", nullable=False)
    duration_sec: Mapped[float] = mapped_column(Float, default=4.0, nullable=False)

    job: Mapped["Job"] = relationship(back_populates="scenes")
