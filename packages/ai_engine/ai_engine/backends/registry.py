"""Adapter registry — the single place that maps config strings to concrete
backends. Call sites ask the registry for a capability; they never import a
concrete adapter. Adding a model = register a new builder here. This is the
structural enforcement of "never break existing functionality": new adapters are
additive and isolated.

Builders are lazy (imported inside the function) so that referencing, say, the
diffusers backend doesn't drag torch into the CPU control plane.
"""

from __future__ import annotations

from ai_engine.config import EngineConfig
from ai_engine.interfaces import (
    AnimationBackend,
    CharacterEngine,
    Composer,
    ImageBackend,
    MusicBackend,
    PromptEnhancer,
    SceneBackend,
    VoiceBackend,
)
from ai_engine.utils.logging import get_logger

log = get_logger("registry")


# --- scene ---------------------------------------------------------------- #
def build_scene_backend(cfg: EngineConfig) -> SceneBackend:
    from ai_engine.scene.llm_scene_backend import LLMSceneBackend

    return LLMSceneBackend.from_config(cfg)


def build_prompt_enhancer(_cfg: EngineConfig) -> PromptEnhancer:
    from ai_engine.scene.prompt_enhancer import TemplatePromptEnhancer

    return TemplatePromptEnhancer()


# --- image ---------------------------------------------------------------- #
_IMAGE_BUILDERS = {
    "comfyui": lambda cfg: _comfyui_image(cfg),
    "diffusers": lambda cfg: _diffusers_image(cfg),
}


def build_image_backend(cfg: EngineConfig) -> ImageBackend:
    builder = _IMAGE_BUILDERS.get(cfg.image_backend)
    if builder is None:
        raise ValueError(f"unknown image backend '{cfg.image_backend}'. options: {list(_IMAGE_BUILDERS)}")
    log.info("image backend -> %s", cfg.image_backend)
    return builder(cfg)


def _comfyui_image(cfg: EngineConfig) -> ImageBackend:
    from ai_engine.image.comfyui_backend import ComfyUIImageBackend

    return ComfyUIImageBackend.from_config(cfg)


def _diffusers_image(cfg: EngineConfig) -> ImageBackend:
    from ai_engine.image.diffusers_backend import DiffusersImageBackend

    return DiffusersImageBackend.from_config(cfg)


# --- character ------------------------------------------------------------ #
def build_character_engine(_cfg: EngineConfig) -> CharacterEngine:
    from ai_engine.character.engine import IPAdapterCharacterEngine

    return IPAdapterCharacterEngine()


# --- animation ------------------------------------------------------------ #
def build_animation_backend(cfg: EngineConfig) -> AnimationBackend:
    log.info("animation backend -> %s", cfg.animation_backend)
    if cfg.animation_backend == "comfyui":
        from ai_engine.animation.comfyui_animatediff import ComfyUIAnimateDiffBackend

        return ComfyUIAnimateDiffBackend.from_config(cfg)
    if cfg.animation_backend in ("kenburns", "ffmpeg"):
        from ai_engine.animation.kenburns_backend import KenBurnsAnimationBackend

        return KenBurnsAnimationBackend.from_config(cfg)
    raise ValueError(f"unknown animation backend '{cfg.animation_backend}'")


# --- voice ---------------------------------------------------------------- #
def build_voice_backend(cfg: EngineConfig) -> VoiceBackend:
    log.info("voice backend -> %s (lang=%s)", cfg.voice_backend, cfg.voice_lang)
    if cfg.voice_backend == "gtts":
        from ai_engine.voice.gtts_backend import GTTSBackend

        return GTTSBackend.from_config(cfg)
    from ai_engine.voice.xtts_backend import XTTSBackend

    return XTTSBackend.from_config(cfg)


# --- music ---------------------------------------------------------------- #
def build_music_backend(cfg: EngineConfig) -> MusicBackend:
    from ai_engine.music.musicgen_backend import MusicGenBackend

    return MusicGenBackend.from_config(cfg)


# --- compose -------------------------------------------------------------- #
def build_composer(_cfg: EngineConfig) -> Composer:
    from ai_engine.compose.ffmpeg_composer import FFmpegComposer

    return FFmpegComposer()
