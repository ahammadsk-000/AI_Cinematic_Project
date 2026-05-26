"""Tests for the optional fal.ai Flux image backend. Offline — no network/FAL_KEY.
Also confirms the existing SDXL/ComfyUI image path is unaffected."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "ai_engine"))

from ai_engine.config import EngineConfig  # noqa: E402
from ai_engine.interfaces import AspectRatio, GenerationConfig, Scene  # noqa: E402


def test_from_config_requires_fal_key(monkeypatch):
    from ai_engine.image.fal_image_backend import FalImageBackend

    monkeypatch.delenv("FAL_KEY", raising=False)
    with pytest.raises(ValueError, match="FAL_KEY"):
        FalImageBackend.from_config(EngineConfig())


def test_build_input_payload(monkeypatch):
    from ai_engine.image.fal_image_backend import FalImageBackend

    monkeypatch.setenv("FAL_KEY", "test-key")
    be = FalImageBackend.from_config(EngineConfig())
    scene = Scene(index=0, summary="x", prompt="a cute cartoon mango king")
    cfg = GenerationConfig(width=576, height=1024, steps=28, seed=42, aspect_ratio=AspectRatio.VERTICAL)
    p = be.build_input(scene, cfg)
    assert p["prompt"] == "a cute cartoon mango king"
    assert p["image_size"] == {"width": 576, "height": 1024}
    assert p["seed"] == 42
    assert p["guidance_scale"] == 3.5            # Flux-appropriate, not SDXL's cfg
    assert "negative_prompt" not in p            # Flux has no negative prompt


def test_registry_dispatches_to_fal_flux(monkeypatch):
    from ai_engine.backends import registry

    monkeypatch.setenv("FAL_KEY", "test-key")
    cfg = EngineConfig()
    cfg.image_backend = "fal-flux"
    assert registry.build_image_backend(cfg).__class__.__name__ == "FalImageBackend"


def test_existing_image_backends_unaffected():
    from ai_engine.backends import registry

    cfg = EngineConfig()  # default image_backend == "comfyui"
    assert registry.build_image_backend(cfg).__class__.__name__ == "ComfyUIImageBackend"
