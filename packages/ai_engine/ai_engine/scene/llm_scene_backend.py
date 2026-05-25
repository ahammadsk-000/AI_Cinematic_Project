"""LLMSceneBackend — script -> structured Scene[] via any LLMClient.

This is the default SceneBackend adapter. It wraps an LLMClient (Ollama by
default), prompts for strict JSON, and parses the result into Scene dataclasses
with defensive fallbacks so a malformed model response degrades gracefully rather
than crashing the whole pipeline.
"""

from __future__ import annotations

import dataclasses
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

# Explicit narration/voice-over lines a user writes in the script, in straight or
# curly quotes. We extract these verbatim (preserving language, e.g. Telugu) rather
# than trusting the LLM to reproduce them — far more reliable for non-English.
_QUOTED = re.compile(r'[“"”‘’\'](.{2,}?)[“"”‘’\']', re.DOTALL)


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

        # If the user wrote explicit quoted narration lines, trust THEM over the LLM:
        # build one scene per line (verbatim narration), reusing the LLM's visuals.
        narration_lines = self._extract_narration(script)
        if len(narration_lines) >= 2:
            scenes = self._align_to_narration(scenes, narration_lines, max_scenes=max_scenes)
            log.info("using %d explicit narration line(s) from the script", len(narration_lines))

        log.info("scene backend produced %d scene(s)", len(scenes))
        return scenes

    @staticmethod
    def _extract_narration(script: str) -> list[str]:
        """Pull quoted voice-over lines from the script, verbatim (any language)."""
        lines = [m.strip() for m in _QUOTED.findall(script)]
        # keep lines that read like narration: long enough AND (multi-word OR non-ASCII)
        return [ln for ln in lines if len(ln) >= 3 and (" " in ln or any(ord(c) > 127 for c in ln))]

    @staticmethod
    def _align_to_narration(scenes: list[Scene], lines: list[str], *, max_scenes: int) -> list[Scene]:
        """Make one scene per narration line, each carrying the exact line. Reuses the
        LLM scenes' visuals (cycling if there are more lines than scenes)."""
        lines = lines[:max_scenes]
        out: list[Scene] = []
        for i, line in enumerate(lines):
            base = scenes[i] if i < len(scenes) else scenes[-1]
            out.append(dataclasses.replace(base, index=i, narration=line, duration_sec=3.0))
        return out

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
        # The fixed character description, applied identically to every scene so the
        # same subject is rendered each time (face-consistency anchor).
        character = str(data.get("character", "")).strip() if isinstance(data, dict) else ""
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
                    meta={"character": character},
                )
            )
        return scenes
