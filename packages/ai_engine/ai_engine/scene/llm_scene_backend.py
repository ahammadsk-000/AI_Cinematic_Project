"""LLMSceneBackend — script -> structured Scene[] via any LLMClient.

This is the default SceneBackend adapter. It wraps an LLMClient (Ollama by
default), prompts for strict JSON, and parses the result into Scene dataclasses
with defensive fallbacks so a malformed model response degrades gracefully rather
than crashing the whole pipeline.
"""

from __future__ import annotations

import json
import re

from ai_engine.config import EngineConfig
from ai_engine.interfaces import Scene, SceneBackend, StyleMode
from ai_engine.scene.llm import LLMClient, build_llm_client
from ai_engine.scene.templates import SCENE_SYSTEM_PROMPT
from ai_engine.utils.logging import get_logger

log = get_logger("scene")

# Match the first {...} block even if the model wraps it in prose / markdown fences.
_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


class LLMSceneBackend(SceneBackend):
    def __init__(self, client: LLMClient) -> None:
        self.client = client

    @classmethod
    def from_config(cls, cfg: EngineConfig) -> "LLMSceneBackend":
        return cls(build_llm_client(cfg))

    def generate_scenes(self, script: str, *, style: StyleMode, max_scenes: int = 8) -> list[Scene]:
        system = SCENE_SYSTEM_PROMPT.format(max_scenes=max_scenes, style=style.value)
        raw = self.client.complete(system, script.strip(), json_mode=True)
        data = self._parse(raw)
        scenes = self._to_scenes(data, max_scenes=max_scenes)
        if not scenes:
            log.warning("LLM produced no usable scenes; falling back to a single scene")
            scenes = [Scene(index=0, summary=script.strip()[:200], environment=script.strip()[:200])]
        log.info("scene backend produced %d scene(s)", len(scenes))
        return scenes

    @staticmethod
    def _parse(raw: str) -> dict:
        raw = raw.strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            m = _JSON_BLOCK.search(raw)
            if m:
                try:
                    return json.loads(m.group(0))
                except json.JSONDecodeError:
                    pass
        log.error("could not parse LLM scene JSON: %s", raw[:300])
        return {}

    @staticmethod
    def _to_scenes(data: dict, *, max_scenes: int) -> list[Scene]:
        items = data.get("scenes") if isinstance(data, dict) else None
        if not isinstance(items, list):
            return []
        scenes: list[Scene] = []
        for i, it in enumerate(items[:max_scenes]):
            if not isinstance(it, dict):
                continue
            sfx = it.get("sound_effects") or []
            if isinstance(sfx, str):
                sfx = [sfx]
            try:
                duration = float(it.get("duration_sec", 4.0))
            except (TypeError, ValueError):
                duration = 4.0
            scenes.append(
                Scene(
                    index=i,
                    summary=str(it.get("summary", "")).strip(),
                    environment=str(it.get("environment", "")).strip(),
                    camera=str(it.get("camera", "")).strip(),
                    lighting=str(it.get("lighting", "")).strip(),
                    emotion=str(it.get("emotion", "")).strip(),
                    motion=str(it.get("motion", "")).strip(),
                    music_mood=str(it.get("music_mood", "")).strip(),
                    sound_effects=[str(s) for s in sfx],
                    narration=str(it.get("narration", "")).strip(),
                    duration_sec=max(1.0, min(10.0, duration)),
                )
            )
        return scenes
