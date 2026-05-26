"""Tests for the FREE local Flux ComfyUI path (offline graph injection + registry).
Reuses the existing ComfyUIImageBackend with the flux workflow — no new backend code."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "ai_engine"))

from ai_engine.config import EngineConfig  # noqa: E402
from ai_engine.interfaces import GenerationConfig, Scene  # noqa: E402


def test_flux_workflow_graph_injection():
    from ai_engine.image.comfyui_backend import ComfyUIImageBackend

    be = ComfyUIImageBackend("http://fake:8188", workflow="flux_txt2img")
    be.load_workflow()  # reads comfyui/workflows/flux_txt2img.json + node_map
    scene = Scene(index=1, summary="x", prompt="a cute cartoon mango king", negative_prompt="ignored")
    cfg = GenerationConfig(width=768, height=1024, seed=99, steps=24)
    g = be._build_graph(scene, cfg)
    assert g["6"]["inputs"]["text"] == "a cute cartoon mango king"   # positive
    assert g["5"]["inputs"]["width"] == 768 and g["5"]["inputs"]["height"] == 1024
    assert g["3"]["inputs"]["seed"] == 99 and g["3"]["inputs"]["steps"] == 24
    assert g["3"]["inputs"]["cfg"] == 1.0          # Flux cfg stays 1.0 (not injected)
    assert g["7"]["inputs"]["text"] == ""           # negative stays empty for Flux
    assert g["26"]["inputs"]["guidance"] == 3.5     # FluxGuidance untouched


def test_registry_dispatches_comfyui_flux():
    from ai_engine.backends import registry

    cfg = EngineConfig()
    cfg.image_backend = "comfyui-flux"
    be = registry.build_image_backend(cfg)
    assert be.__class__.__name__ == "ComfyUIImageBackend"
    assert be.workflow_name == "flux_txt2img"


def test_default_image_backend_still_sdxl():
    from ai_engine.backends import registry

    be = registry.build_image_backend(EngineConfig())  # default comfyui
    assert be.workflow_name == "sdxl_txt2img"
