"""Backend configuration — env-driven via pydantic-settings.

This is the CPU control plane. It must NOT import torch/diffusers or anything
GPU-related; it only enqueues jobs and reads progress/results.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    cors_origins: list[str] = ["http://localhost:3000"]

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


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
