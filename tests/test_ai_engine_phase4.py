"""Phase 4 tests for ai_engine. All run on CPU with no models / no network:
the LLM and ComfyUI HTTP calls are faked, so this verifies our parsing, prompt
assembly, graph injection, and registry wiring — the parts we actually wrote.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# make the ai_engine package importable
ENGINE = Path(__file__).resolve().parents[1] / "packages" / "ai_engine"
sys.path.insert(0, str(ENGINE))

from ai_engine.config import EngineConfig  # noqa: E402
from ai_engine.interfaces import Scene, StyleMode  # noqa: E402


# --------------------------------------------------------------------------- #
# prompt enhancer (pure)
# --------------------------------------------------------------------------- #
def test_prompt_enhancer_builds_ordered_prompt():
    from ai_engine.scene.prompt_enhancer import TemplatePromptEnhancer

    scene = Scene(
        index=0,
        summary="a boy walks",
        environment="rainy cyberpunk alley",
        camera="low-angle dolly-in",
        lighting="neon rim light",
        emotion="lonely",
    )
    out = TemplatePromptEnhancer().enhance(scene, style=StyleMode.CYBERPUNK)
    # subject first, style suffix present, negative auto-filled
    assert out.prompt.startswith("a boy walks, rainy cyberpunk alley")
    assert "cyberpunk" in out.prompt
    assert "neon rim light" in out.prompt
    assert "low quality" in out.negative_prompt


def test_prompt_enhancer_respects_existing_negative():
    from ai_engine.scene.prompt_enhancer import TemplatePromptEnhancer

    scene = Scene(index=0, summary="x", negative_prompt="custom neg")
    out = TemplatePromptEnhancer().enhance(scene, style=StyleMode.ANIME)
    assert out.negative_prompt == "custom neg"


# --------------------------------------------------------------------------- #
# scene backend (fake LLM client)
# --------------------------------------------------------------------------- #
class _FakeLLM:
    def __init__(self, payload: str) -> None:
        self.payload = payload
        self.seen: dict | None = None

    def complete(self, system: str, user: str, *, json_mode: bool = False) -> str:
        self.seen = {"system": system, "user": user, "json_mode": json_mode}
        return self.payload


def test_scene_backend_parses_clean_json():
    from ai_engine.scene.llm_scene_backend import LLMSceneBackend

    payload = """{"scenes":[
        {"summary":"boy walks","environment":"neon city","camera":"wide","lighting":"neon",
         "emotion":"lonely","motion":"rain falls","music_mood":"synth","sound_effects":["rain"],
         "narration":"He walked alone.","duration_sec":5},
        {"summary":"close up","duration_sec":99}
    ]}"""
    be = LLMSceneBackend(_FakeLLM(payload))
    scenes = be.generate_scenes("a boy in a city", style=StyleMode.CYBERPUNK, max_scenes=8)
    assert len(scenes) == 2
    assert scenes[0].summary == "boy walks"
    assert scenes[0].sound_effects == ["rain"]
    assert scenes[0].duration_sec == 5.0
    # duration clamped to [1,10]
    assert scenes[1].duration_sec == 10.0
    assert be.client.seen["json_mode"] is True


def test_scene_backend_extracts_json_from_prose():
    from ai_engine.scene.llm_scene_backend import LLMSceneBackend

    payload = 'Sure! Here you go:\n```json\n{"scenes":[{"summary":"hi"}]}\n```\nHope that helps!'
    scenes = LLMSceneBackend(_FakeLLM(payload)).generate_scenes("x", style=StyleMode.FANTASY)
    assert len(scenes) == 1 and scenes[0].summary == "hi"


def test_scene_backend_falls_back_on_garbage():
    from ai_engine.scene.llm_scene_backend import LLMSceneBackend

    scenes = LLMSceneBackend(_FakeLLM("not json at all")).generate_scenes(
        "a lone knight", style=StyleMode.FANTASY
    )
    assert len(scenes) == 1  # graceful single-scene fallback
    assert "knight" in scenes[0].summary


# --------------------------------------------------------------------------- #
# ComfyUI graph injection (offline — no server)
# --------------------------------------------------------------------------- #
def test_comfyui_graph_injection():
    from ai_engine.image.comfyui_backend import ComfyUIImageBackend
    from ai_engine.interfaces import GenerationConfig

    be = ComfyUIImageBackend("http://fake:8188")
    be.load_workflow()  # reads the real workflow JSON from comfyui/workflows/
    scene = Scene(index=2, summary="a cat scene", prompt="a cat", negative_prompt="dog")
    cfg = GenerationConfig(width=768, height=512, seed=42, steps=20, cfg_scale=7.0)
    graph = be._build_graph(scene, cfg)

    assert "_meta" not in graph
    assert graph["6"]["inputs"]["text"] == "a cat"
    assert graph["7"]["inputs"]["text"] == "dog"
    assert graph["5"]["inputs"]["width"] == 768
    assert graph["3"]["inputs"]["seed"] == 42
    assert graph["3"]["inputs"]["steps"] == 20
    assert graph["9"]["inputs"]["filename_prefix"] == "cineforge_s2"


# --------------------------------------------------------------------------- #
# registry wiring
# --------------------------------------------------------------------------- #
def test_registry_builds_default_backends():
    from ai_engine.backends import registry

    cfg = EngineConfig()
    assert registry.build_prompt_enhancer(cfg) is not None
    img = registry.build_image_backend(cfg)  # default = comfyui
    assert img.__class__.__name__ == "ComfyUIImageBackend"
    assert registry.build_character_engine(cfg) is not None


def test_registry_rejects_unknown_image_backend():
    from ai_engine.backends import registry

    cfg = EngineConfig()
    cfg.image_backend = "nope"
    with pytest.raises(ValueError, match="unknown image backend"):
        registry.build_image_backend(cfg)
