from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import JSON
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.enums import AssetKind

if TYPE_CHECKING:
    from app.models.job import Job


class Asset(Base, UUIDMixin, TimestampMixin):
    """A produced artifact (image/clip/audio/subtitle) addressed by job+stage.
    Mirrors ai_engine.interfaces.Artifact."""

    __tablename__ = "assets"

    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("jobs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    kind: Mapped[AssetKind] = mapped_column(SAEnum(AssetKind, native_enum=False), nullable=False)
    stage: Mapped[str] = mapped_column(String(64), nullable=False)
    scene_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    path: Mapped[str] = mapped_column(String(512), nullable=False)
    # JSONB on Postgres; degrades to generic JSON on other dialects (e.g. sqlite tests)
    meta: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), default=dict, nullable=False
    )

    job: Mapped["Job"] = relationship(back_populates="assets")
