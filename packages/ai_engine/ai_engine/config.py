"""ai_engine runtime configuration.

Deliberately free of any web/db dependency so this object behaves identically
in a Colab cell, in the Celery GPU worker, or in a unit test. Everything is
env-overridable but has sane low-VRAM defaults targeting a T4 / RTX 3060.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(key: str, default: str) -> str:
    return os.getenv(key, default)


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, default))
    except (TypeError, ValueError):
        return default


@dataclass
class EngineConfig:
    # --- storage ---
    storage_root: Path = field(default_factory=lambda: Path(_env("CINEFORGE_STORAGE", "storage")))
    model_cache: Path = field(default_factory=lambda: Path(_env("CINEFORGE_MODEL_CACHE", "storage/models")))

    # --- scene / LLM (Ollama-default, OpenAI-compatible fallback) ---
    llm_provider: str = field(default_factory=lambda: _env("CINEFORGE_LLM_PROVIDER", "ollama"))
    llm_model: str = field(default_factory=lambda: _env("CINEFORGE_LLM_MODEL", "llama3"))
    ollama_host: str = field(default_factory=lambda: _env("OLLAMA_HOST", "http://localhost:11434"))

    # --- image / animation (ComfyUI-default) ---
    image_backend: str = field(default_factory=lambda: _env("CINEFORGE_IMAGE_BACKEND", "comfyui"))
    animation_backend: str = field(default_factory=lambda: _env("CINEFORGE_ANIM_BACKEND", "comfyui"))
    comfyui_url: str = field(default_factory=lambda: _env("COMFYUI_URL", "http://127.0.0.1:8188"))

    # --- voice / music ---
    voice_backend: str = field(default_factory=lambda: _env("CINEFORGE_VOICE_BACKEND", "xtts"))
    voice_lang: str = field(default_factory=lambda: _env("CINEFORGE_VOICE_LANG", "en"))
    music_backend: str = field(default_factory=lambda: _env("CINEFORGE_MUSIC_BACKEND", "musicgen"))

    # --- compose ---
    composer: str = field(default_factory=lambda: _env("CINEFORGE_COMPOSER", "ffmpeg"))

    # --- VRAM / performance ---
    vram_budget_gb: float = field(default_factory=lambda: _env_float("CINEFORGE_VRAM_GB", 12.0))
    use_fp16: bool = field(default_factory=lambda: _env("CINEFORGE_FP16", "1") == "1")
    enable_cpu_offload: bool = field(default_factory=lambda: _env("CINEFORGE_CPU_OFFLOAD", "1") == "1")
    enable_vae_tiling: bool = field(default_factory=lambda: _env("CINEFORGE_VAE_TILING", "1") == "1")

    def job_dir(self, job_id: str) -> Path:
        return self.storage_root / "outputs" / job_id


def load_config() -> EngineConfig:
    return EngineConfig()
