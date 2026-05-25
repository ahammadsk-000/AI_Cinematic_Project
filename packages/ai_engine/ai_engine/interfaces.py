"""Core inference abstractions for Cineforge.

Every generative capability in the platform is expressed here as an abstract
backend. Concrete models (ComfyUI, Diffusers, Ollama, XTTS, MusicGen, ...) are
*adapters* implementing these contracts and live under ``ai_engine.backends``.

Design rules (see docs/ARCHITECTURE.md §3, §4):
  * This module has ZERO dependency on FastAPI / SQLAlchemy / Celery.
  * Adding a model = new adapter implementing an existing interface. No call-site
    changes anywhere else. This is what makes "never break existing functionality"
    a structural guarantee rather than a hope.
  * Every heavy backend shares the load()/unload() lifecycle so the orchestrator
    can keep exactly one big model resident at a time (the core low-VRAM lever).

Nothing here is implemented yet — Phases 4 and 5 fill in the adapters. This file
defines the *shape* of the system.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Protocol, runtime_checkable


# --------------------------------------------------------------------------- #
# Shared value objects
# --------------------------------------------------------------------------- #
class StyleMode(str, Enum):
    """High-level visual style presets that bias prompts and model/LoRA choice."""

    CINEMATIC_REALISTIC = "cinematic_realistic"
    ANIME = "anime"
    CYBERPUNK = "cyberpunk"
    FANTASY = "fantasy"
    PORTRAIT = "portrait"


class AspectRatio(str, Enum):
    WIDE = "16:9"      # YouTube / cinematic
    VERTICAL = "9:16"  # Reels / Shorts / TikTok
    SQUARE = "1:1"     # feed posts


@dataclass
class Character:
    """A character whose identity must stay consistent across scenes."""

    id: str
    name: str
    description: str
    reference_image: Optional[Path] = None   # locked reference (ref-image locking)
    face_embedding: Optional[Any] = None      # populated by CharacterEngine
    lora_path: Optional[Path] = None          # optional per-character LoRA
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class Scene:
    """One structured beat of the script. Produced by SceneBackend."""

    index: int
    summary: str
    prompt: str = ""                 # filled by PromptEnhancer
    negative_prompt: str = ""
    camera: str = ""                 # e.g. "low-angle dolly-in"
    lighting: str = ""               # e.g. "neon rim light, volumetric fog"
    emotion: str = ""                # e.g. "lonely, tense"
    environment: str = ""            # e.g. "rain-slicked cyberpunk alley at night"
    motion: str = ""                 # animation hint, e.g. "slow forward push"
    sound_effects: list[str] = field(default_factory=list)
    music_mood: str = ""             # e.g. "melancholic synth, suspense"
    narration: str = ""              # voice-over text for this scene
    character_ids: list[str] = field(default_factory=list)
    duration_sec: float = 4.0
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class GenerationConfig:
    """Per-job knobs shared by image/animation backends. VRAM-aware."""

    style: StyleMode = StyleMode.CINEMATIC_REALISTIC
    aspect_ratio: AspectRatio = AspectRatio.WIDE
    width: int = 1024
    height: int = 576
    steps: int = 28
    cfg_scale: float = 6.5
    seed: Optional[int] = None
    fps: int = 12
    frames_per_clip: int = 16
    vram_budget_gb: float = 12.0     # drives offload/tiling/fallback decisions
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class Artifact:
    """A produced file on disk, addressed by job/stage. Returned by every stage."""

    path: Path
    kind: str                         # "image" | "video" | "audio" | "json" | "subtitle"
    scene_index: Optional[int] = None
    meta: dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Lifecycle mixin — the low-VRAM contract
# --------------------------------------------------------------------------- #
class LoadableBackend(abc.ABC):
    """Heavy backends implement explicit load/unload so the orchestrator can keep
    only one large model resident at a time (docs/ARCHITECTURE.md §6)."""

    @property
    @abc.abstractmethod
    def is_loaded(self) -> bool: ...

    @abc.abstractmethod
    def load(self) -> None:
        """Bring weights into VRAM. Idempotent."""

    @abc.abstractmethod
    def unload(self) -> None:
        """Free VRAM (move to CPU / del / torch.cuda.empty_cache). Idempotent."""

    def __enter__(self):
        self.load()
        return self

    def __exit__(self, *exc):
        self.unload()
        return False


# --------------------------------------------------------------------------- #
# Stage backends — the contract each model adapter implements
# --------------------------------------------------------------------------- #
class SceneBackend(abc.ABC):
    """script (str) -> structured Scene[].  Default adapter: Ollama (Llama3/Mistral/Qwen)."""

    @abc.abstractmethod
    def generate_scenes(self, script: str, *, style: StyleMode, max_scenes: int = 8) -> list[Scene]:
        ...


class PromptEnhancer(abc.ABC):
    """Scene -> Scene with rich cinematic prompt/negative_prompt filled in."""

    @abc.abstractmethod
    def enhance(self, scene: Scene, *, style: StyleMode) -> Scene:
        ...


class ImageBackend(LoadableBackend):
    """prompt (+ optional control/reference) -> still image.
    Default adapter: ComfyUIImageBackend (SDXL). Alt: DiffusersImageBackend."""

    @abc.abstractmethod
    def generate_image(
        self,
        scene: Scene,
        cfg: GenerationConfig,
        *,
        characters: Optional[list[Character]] = None,
        control_image: Optional[Path] = None,
    ) -> Artifact:
        ...


class CharacterEngine(abc.ABC):
    """Maintains identity across scenes via face-embedding memory, reference-image
    locking, IPAdapter, optional per-character LoRA, and ControlNet reference mode."""

    @abc.abstractmethod
    def register(self, character: Character) -> Character:
        """Compute & store the face embedding / lock the reference image."""

    @abc.abstractmethod
    def apply(self, scene: Scene, characters: list[Character], cfg: GenerationConfig) -> dict[str, Any]:
        """Return backend kwargs (ipadapter weights, ref image, lora) to inject into ImageBackend."""

    @abc.abstractmethod
    def verify(self, artifact: Artifact, character: Character) -> float:
        """Return a similarity score so low-consistency frames can be regenerated."""


class AnimationBackend(LoadableBackend):
    """still image(s) -> short video clip with motion/camera moves.
    Default adapter: ComfyUIAnimateDiffBackend. Alt: SVDBackend."""

    @abc.abstractmethod
    def animate(self, image: Artifact, scene: Scene, cfg: GenerationConfig) -> Artifact:
        ...


class VoiceBackend(LoadableBackend):
    """narration text -> speech audio. Default: XTTS v2. Alt: Bark / Coqui."""

    @abc.abstractmethod
    def synthesize(
        self,
        text: str,
        *,
        voice: str = "narrator_male",
        language: str = "en",
        emotion: str = "neutral",
        out_path: Optional[Path] = None,
    ) -> Artifact:
        ...


class MusicBackend(LoadableBackend):
    """mood description -> background score audio. Default: MusicGen (AudioCraft)."""

    @abc.abstractmethod
    def compose_music(self, mood: str, *, duration_sec: float, out_path: Optional[Path] = None) -> Artifact:
        ...


class Composer(abc.ABC):
    """clips + narration + music + subtitles -> final MP4.
    Default: FFmpegComposer. Alt: MoviePyComposer."""

    @abc.abstractmethod
    def compose(
        self,
        clips: list[Artifact],
        *,
        narration: Optional[list[Artifact]] = None,
        music: Optional[Artifact] = None,
        subtitles: Optional[Artifact] = None,
        aspect_ratio: AspectRatio = AspectRatio.WIDE,
        out_path: Optional[Path] = None,
    ) -> Artifact:
        ...


# --------------------------------------------------------------------------- #
# Progress reporting — how stages talk to the SSE layer without depending on it
# --------------------------------------------------------------------------- #
@runtime_checkable
class ProgressReporter(Protocol):
    """The orchestrator is handed an object satisfying this Protocol. In the worker
    it's backed by Redis pub/sub; in a Colab notebook it can just print. ai_engine
    never imports Redis — it only depends on this duck-typed contract."""

    def __call__(self, *, stage: str, pct: float, message: str = "", **extra: Any) -> None: ...


__all__ = [
    "StyleMode", "AspectRatio", "Character", "Scene", "GenerationConfig", "Artifact",
    "LoadableBackend", "SceneBackend", "PromptEnhancer", "ImageBackend",
    "CharacterEngine", "AnimationBackend", "VoiceBackend", "MusicBackend",
    "Composer", "ProgressReporter",
]
