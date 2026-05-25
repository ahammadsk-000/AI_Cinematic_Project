from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import AspectRatio, JobStatus, StyleMode
from app.schemas.scene import SceneRead


class JobCreate(BaseModel):
    script: str = Field(min_length=4, max_length=8000)
    title: str = Field(default="Untitled", max_length=200)
    style: StyleMode = StyleMode.CINEMATIC_REALISTIC
    aspect_ratio: AspectRatio = AspectRatio.WIDE


class AssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    stage: str
    scene_index: int | None
    path: str


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    script: str
    style: StyleMode
    aspect_ratio: AspectRatio
    status: JobStatus
    current_stage: str | None
    progress_pct: float
    error: str | None
    result_path: str | None
    created_at: datetime
    updated_at: datetime


class JobDetail(JobRead):
    """Full job view including its scenes and assets."""

    scenes: list[SceneRead] = []
    assets: list[AssetRead] = []


class JobProgress(BaseModel):
    """Shape of an SSE progress event (also persisted to the Job row)."""

    job_id: uuid.UUID
    status: JobStatus
    stage: str | None = None
    pct: float = 0.0
    message: str = ""
