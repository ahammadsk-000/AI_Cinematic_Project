"""Worker configuration. Reads the same env as the backend (shared broker, DB,
storage) but is otherwise independent — the worker runs on the GPU box."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class WorkerConfig:
    celery_broker_url: str = field(default_factory=lambda: os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/1"))
    celery_result_backend: str = field(default_factory=lambda: os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/2"))
    redis_url: str = field(default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", "postgresql+asyncpg://cineforge:cineforge@localhost:5432/cineforge"))
    storage_root: Path = field(default_factory=lambda: Path(os.getenv("STORAGE_ROOT", "storage")))

    @property
    def sync_database_url(self) -> str:
        """Celery tasks are sync, so convert the backend's async URL to a sync one."""
        url = self.database_url
        if "+asyncpg" in url:
            return url.replace("+asyncpg", "")          # -> postgresql:// (psycopg2)
        if "+aiosqlite" in url:
            return url.replace("+aiosqlite", "")         # -> sqlite:// (tests)
        return url


def load_worker_config() -> WorkerConfig:
    return WorkerConfig()
