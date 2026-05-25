from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field


class SceneRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    index: int
    summary: str
    prompt: str
    negative_prompt: str
    camera: str
    lighting: str
    emotion: str
    environment: str
    motion: str
    music_mood: str
    narration: str
    duration_sec: float


class SceneUpdate(BaseModel):
    """Partial edit of a scene (Phase 3 'scene editing' / regeneration feature).
    All fields optional — only provided ones are applied."""

    summary: str | None = None
    prompt: str | None = None
    negative_prompt: str | None = None
    camera: str | None = None
    lighting: str | None = None
    emotion: str | None = None
    environment: str | None = None
    motion: str | None = None
    music_mood: str | None = None
    narration: str | None = None
    duration_sec: float | None = Field(default=None, gt=0, le=30)
