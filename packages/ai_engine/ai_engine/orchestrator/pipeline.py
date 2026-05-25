"""The cinematic generation pipeline contract.

This defines the *shape* of the orchestrator: an ordered list of checkpointed,
idempotent stages. Stage implementations are filled in during Phases 4–5; this
file establishes the skeleton, the stage protocol, and the resume semantics so
later code conforms to a single contract.

The orchestrator runs stages sequentially, keeping one heavy model resident at a
time (docs/ARCHITECTURE.md §6), checkpoints each completed stage to a job
manifest, and reports progress through a ProgressReporter (Protocol) so it has no
dependency on Redis/Celery/SSE.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from ai_engine.interfaces import Artifact, ProgressReporter


class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"  # already completed on a prior (crashed) run


@dataclass
class StageResult:
    name: str
    status: StageStatus
    artifacts: list[Artifact] = field(default_factory=list)
    error: Optional[str] = None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class JobContext:
    """Mutable bag carried through the pipeline. Each stage reads prior artifacts
    and writes its own. Serializable to the job manifest for resume-after-crash."""

    job_id: str
    script: str
    workdir: Any  # pathlib.Path to storage/<job_id>/
    config: Any   # ai_engine.interfaces.GenerationConfig
    scenes: list = field(default_factory=list)
    characters: list = field(default_factory=list)
    artifacts: dict[str, list[Artifact]] = field(default_factory=dict)  # stage -> artifacts
    completed_stages: set[str] = field(default_factory=set)
    report: Optional[ProgressReporter] = None


class Stage(abc.ABC):
    """One pipeline step. Must be idempotent and safe to skip on resume."""

    name: str
    #: rough share of total job time, used for smooth overall % reporting
    weight: float = 1.0

    @abc.abstractmethod
    def run(self, ctx: JobContext) -> StageResult:
        ...

    def already_done(self, ctx: JobContext) -> bool:
        return self.name in ctx.completed_stages


#: The canonical pipeline order. Stage classes are registered in Phases 4–5.
#: Listed here as names so the contract (and the SSE progress UI) is stable now.
PIPELINE_STAGES: list[str] = [
    "scene_generation",     # script -> Scene[]            (SceneBackend)
    "prompt_enhancement",   # Scene -> cinematic prompts   (PromptEnhancer)
    "image_generation",     # Scene -> still image         (ImageBackend / SDXL)
    "character_lock",       # enforce identity consistency (CharacterEngine)
    "animation",            # image -> clip                (AnimationBackend)
    "voice",                # narration -> audio           (VoiceBackend)
    "music",                # mood -> score                (MusicBackend)
    "compose",              # clips+audio+subs -> MP4      (Composer)
]


class Orchestrator(abc.ABC):
    """Drives the pipeline. Concrete implementation lands in Phase 4.

    Responsibilities (documented now so the implementation is unambiguous):
      * load the job manifest and mark already-completed stages SKIPPED (resume);
      * run remaining stages in order, one heavy model resident at a time;
      * checkpoint after each stage (write manifest + persist artifacts);
      * translate VRAMError into a reduced-resolution retry before failing;
      * emit progress via ctx.report(stage=..., pct=..., message=...).
    """

    @abc.abstractmethod
    def run(self, ctx: JobContext) -> JobContext:
        ...
