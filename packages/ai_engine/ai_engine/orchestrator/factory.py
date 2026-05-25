"""Assemble a fully-wired DefaultOrchestrator from EngineConfig.

This is the single entry point the GPU worker calls: give it config, get back a
ready pipeline. All backends are built via the registry, so swapping a model is a
config change — the factory and stages are untouched.
"""

from __future__ import annotations

from ai_engine.backends import registry
from ai_engine.config import EngineConfig
from ai_engine.orchestrator.runner import DefaultOrchestrator
from ai_engine.orchestrator.stages import (
    AnimationStage,
    CharacterLockStage,
    ComposeStage,
    ImageGenerationStage,
    MusicStage,
    PromptEnhancementStage,
    SceneGenerationStage,
    VoiceStage,
)


def build_orchestrator(cfg: EngineConfig, *, max_scenes: int = 8) -> DefaultOrchestrator:
    scene_backend = registry.build_scene_backend(cfg)
    enhancer = registry.build_prompt_enhancer(cfg)
    image_backend = registry.build_image_backend(cfg)
    character_engine = registry.build_character_engine(cfg)
    animation_backend = registry.build_animation_backend(cfg)
    voice_backend = registry.build_voice_backend(cfg)
    music_backend = registry.build_music_backend(cfg)
    composer = registry.build_composer(cfg)

    stages = [
        SceneGenerationStage(scene_backend, max_scenes=max_scenes),
        PromptEnhancementStage(enhancer),
        ImageGenerationStage(image_backend, character_engine),
        CharacterLockStage(character_engine),
        AnimationStage(animation_backend),
        VoiceStage(voice_backend),
        MusicStage(music_backend),
        ComposeStage(composer),
    ]
    return DefaultOrchestrator(stages)
