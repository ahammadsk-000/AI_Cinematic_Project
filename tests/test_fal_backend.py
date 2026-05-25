"""Tests for the optional fal.ai paid video backend. Pure/offline — no network,
no FAL_KEY needed. Also asserts the existing free backends are unaffected."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "ai_engine"))

from ai_engine.config import EngineConfig  # noqa: E402
from ai_engine.interfaces import Artifact, AspectRatio, GenerationConfig, Scene, StyleMode  # noqa: E402


def test_from_config_requires_fal_key(monkeypatch):
    from ai_engine.animation.fal_video_backend import FalVideoBackend

    monkeypatch.delenv("FAL_KEY", raising=False)
    with pytest.raises(ValueError, match="FAL_KEY"):
        FalVideoBackend.from_config(EngineConfig())


def test_build_input_payload(tmp_path, monkeypatch):
    from ai_engine.animation.fal_video_backend import FalVideoBackend

    monkeypatch.setenv("FAL_KEY", "test-key")
    be = FalVideoBackend.from_config(EngineConfig())
    img_file = tmp_path / "frame.png"
    img_file.write_bytes(b"\x89PNG\r\n\x1a\n fake image bytes")
    img = Artifact(path=img_file, kind="image", scene_index=0)
    scene = Scene(index=0, summary="a boy walks", motion="slow forward push", camera="dolly-in")
    cfg = GenerationConfig(aspect_ratio=AspectRatio.VERTICAL)

    payload = be.build_input(img, scene, cfg)
    assert payload["image_url"].startswith("data:image/png;base64,")
    assert payload["aspect_ratio"] == "9:16"
    assert payload["duration"] == "5"
    assert "a boy walks" in payload["prompt"] and "slow forward push" in payload["prompt"]


def test_registry_dispatches_to_fal_when_enabled(monkeypatch):
    from ai_engine.backends import registry

    monkeypatch.setenv("FAL_KEY", "test-key")
    cfg = EngineConfig()
    cfg.animation_backend = "fal"
    assert registry.build_animation_backend(cfg).__class__.__name__ == "FalVideoBackend"


def test_existing_free_backends_unaffected(monkeypatch):
    """Setting fal must not change the free path — the original backends still build."""
    from ai_engine.backends import registry

    monkeypatch.delenv("FAL_KEY", raising=False)
    cfg = EngineConfig()
    cfg.animation_backend = "kenburns"
    assert registry.build_animation_backend(cfg).__class__.__name__ == "KenBurnsAnimationBackend"
    cfg.animation_backend = "svd"
    assert registry.build_animation_backend(cfg).__class__.__name__ == "ComfyUIAnimateDiffBackend"
