"""TemplatePromptEnhancer — Scene -> Scene with rich SDXL prompt/negative filled.

Pure, dependency-free, deterministic: it assembles the LLM's structured scene
fields plus the style vocabulary into a single weighted prompt string. Because it
has no network/model deps it's fully unit-testable and runs anywhere.
"""

from __future__ import annotations

from ai_engine.interfaces import PromptEnhancer, Scene, StyleMode
from ai_engine.scene.templates import style_negative, style_suffix
from ai_engine.utils.logging import get_logger

log = get_logger("prompt")


class TemplatePromptEnhancer(PromptEnhancer):
    def enhance(self, scene: Scene, *, style: StyleMode) -> Scene:
        # Order matters for SDXL: subject/action first, then environment, then
        # camera + lighting modifiers, then the style suffix.
        parts = [
            scene.summary,
            scene.environment,
            scene.camera,
            scene.lighting,
            scene.emotion,
            style_suffix(style),
        ]
        prompt = ", ".join(p.strip() for p in parts if p and p.strip())

        scene.prompt = prompt
        # Respect an LLM-provided negative if present, else use the style default.
        scene.negative_prompt = scene.negative_prompt or style_negative(style)
        log.debug("enhanced scene %d -> %s", scene.index, prompt[:90])
        return scene

    def enhance_all(self, scenes: list[Scene], *, style: StyleMode) -> list[Scene]:
        return [self.enhance(s, style=style) for s in scenes]
