from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import JSON, ForeignKey, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.models.job import Job


class Character(Base, UUIDMixin, TimestampMixin):
    """A character whose identity is locked across scenes. The face embedding /
    reference image is computed by ai_engine.CharacterEngine on the GPU side; we
    persist only the locator + light metadata here."""

    __tablename__ = "characters"

    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("jobs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    reference_image_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    lora_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    meta: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=dict, nullable=False
    )

    job: Mapped["Job"] = relationship(back_populates="characters")
