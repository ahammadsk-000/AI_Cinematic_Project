"""Backend configuration — env-driven via pydantic-settings.

This is the CPU control plane. It must NOT import torch/diffusers or anything
GPU-related; it only enqueues jobs and reads progress/results.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- app ---
    app_name: str = "Cineforge API"
    environment: Literal["dev", "staging", "prod"] = "dev"
    debug: bool = True
    api_v1_prefix: str = "/api/v1"

    # --- security / auth (JWT) ---
    secret_key: str = Field(default="CHANGE_ME_IN_ENV", description="JWT signing key")
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24
    # NoDecode: don't let pydantic-settings JSON-parse the raw env value — our
    # validator below accepts JSON list, comma-separated, OR a single bare URL,
    # so a value like CORS_ORIGINS=https://x.vercel.app won't crash startup.
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, v: object) -> list[str]:
        if v is None:
            return ["http://localhost:3000"]
        if isinstance(v, (list, tuple)):
            return [str(o).strip() for o in v if str(o).strip()]
        s = str(v).strip()
        if not s:
            return ["http://localhost:3000"]
        if s.startswith("["):  # JSON list, e.g. ["https://a","https://b"]
            return [str(o).strip() for o in json.loads(s) if str(o).strip()]
        # comma-separated or a single bare origin
        return [o.strip() for o in s.split(",") if o.strip()]

    # --- database (Supabase / local Postgres) ---
    database_url: str = "postgresql+asyncpg://cineforge:cineforge@localhost:5432/cineforge"

    # --- queue / cache (Redis) ---
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"
    celery_queue: str = "video"

    # --- stalled-job reaper ---
    enable_reaper: bool = True
    reaper_interval_s: int = 60

    # --- storage ---
    storage_root: str = "storage"

    # --- engine handoff (the worker reads these too) ---
    comfyui_url: str = "http://127.0.0.1:8188"
    ollama_host: str = "http://localhost:11434"

    @model_validator(mode="after")
    def _fill_celery_from_redis(self) -> "Settings":
        # On free Redis (e.g. Upstash, single DB 0) the broker, result backend,
        # and pub/sub all share one URL. If the Celery URLs are blank/unset (a
        # common deploy mistake — only REDIS_URL gets filled in), fall back to
        # REDIS_URL so enqueueing doesn't crash with "No such transport: ''".
        if not (self.celery_broker_url or "").strip():
            self.celery_broker_url = self.redis_url
        if not (self.celery_result_backend or "").strip():
            self.celery_result_backend = self.redis_url
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
