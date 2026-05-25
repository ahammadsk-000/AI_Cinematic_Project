"""Domain enums shared by models and schemas.

JobStatus mirrors the lifecycle in docs/ARCHITECTURE.md §7. Style/AspectRatio
intentionally duplicate the ai_engine enum *values* (not the import) so the CPU
control plane never imports the GPU package.
"""

from __future__ import annotations

import enum


class JobStatus(str, enum.Enum):
    PENDING = "pending"      # created, not yet enqueued
    QUEUED = "queued"        # on the Redis queue, waiting for a GPU worker
    RUNNING = "running"      # a worker is executing a stage
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StyleMode(str, enum.Enum):
    CINEMATIC_REALISTIC = "cinematic_realistic"
    ANIME = "anime"
    CYBERPUNK = "cyberpunk"
    FANTASY = "fantasy"
    PORTRAIT = "portrait"


class AspectRatio(str, enum.Enum):
    WIDE = "16:9"
    VERTICAL = "9:16"
    SQUARE = "1:1"


class AssetKind(str, enum.Enum):
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    SUBTITLE = "subtitle"
    JSON = "json"
