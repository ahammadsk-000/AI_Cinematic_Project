"""Concrete pipeline stages. Each wraps backend(s) and operates on JobContext,
reporting LOCAL progress 0-100 via ctx.report (the runner rescales it to a global
band). Heavy backends are opened with the load()/unload() lifecycle so only one
big model is VRAM-resident at a time.

Stages write their outputs both into ctx (for the next stage) and to disk (so the
manifest can reference them on resume).
"""

from __future__ import annotations

import json
from pathlib import Path

from ai_engine.interfaces import (
    AnimationBackend,
    Artifact,
    CharacterEngine,
    Composer,
    ImageBackend,
    MusicBackend,
    PromptEnhancer,
    SceneBackend,
    VoiceBackend,
)
from ai_engine.orchestrator.pipeline import JobContext, Stage, StageResult, StageStatus
from ai_engine.utils.logging import get_logger

log = get_logger("stage")


def _report(ctx: JobContext, name: str, pct: float, msg: str = "") -> None:
    if ctx.report is not None:
        ctx.report(stage=name, pct=pct, message=msg)


class SceneGenerationStage(Stage):
    name = "scene_generation"
    weight = 1.5

    def __init__(self, backend: SceneBackend, max_scenes: int = 8) -> None:
        self.backend = backend
        self.max_scenes = max_scenes

    def run(self, ctx: JobContext) -> StageResult:
        _report(ctx, self.name, 5, "Breaking the script into scenes…")
        scenes = self.backend.generate_scenes(ctx.script, style=ctx.config.style, max_scenes=self.max_scenes)
        ctx.scenes = scenes
        out = ctx.workdir / "scenes.json"
        out.write_text(json.dumps([s.__dict__ for s in scenes], indent=2, default=str), "utf-8")
        _report(ctx, self.name, 100, f"{len(scenes)} scenes")
        return StageResult(self.name, StageStatus.COMPLETED, [Artifact(path=out, kind="json")])


class PromptEnhancementStage(Stage):
    name = "prompt_enhancement"
    weight = 0.5

    def __init__(self, enhancer: PromptEnhancer) -> None:
        self.enhancer = enhancer

    def run(self, ctx: JobContext) -> StageResult:
        for i, scene in enumerate(ctx.scenes):
            self.enhancer.enhance(scene, style=ctx.config.style)
            _report(ctx, self.name, (i + 1) / max(1, len(ctx.scenes)) * 100)
        out = ctx.workdir / "scenes_enhanced.json"
        out.write_text(json.dumps([s.__dict__ for s in ctx.scenes], indent=2, default=str), "utf-8")
        return StageResult(self.name, StageStatus.COMPLETED, [Artifact(path=out, kind="json")])


class ImageGenerationStage(Stage):
    name = "image_generation"
    weight = 3.0

    def __init__(self, backend: ImageBackend, character_engine: CharacterEngine | None = None) -> None:
        self.backend = backend
        self.character_engine = character_engine

    def run(self, ctx: JobContext) -> StageResult:
        if self.character_engine:
            for char in ctx.characters:
                self.character_engine.register(char)
        self.backend.output_dir = ctx.workdir / "images"  # type: ignore[attr-defined]
        artifacts: list[Artifact] = []
        with self.backend:  # load()/unload() around the whole batch
            for i, scene in enumerate(ctx.scenes):
                _report(ctx, self.name, i / max(1, len(ctx.scenes)) * 100, f"Rendering scene {i + 1}")
                art = self.backend.generate_image(scene, ctx.config, characters=ctx.characters or None)
                artifacts.append(art)
        ctx.artifacts["images"] = artifacts
        _report(ctx, self.name, 100, f"{len(artifacts)} images")
        return StageResult(self.name, StageStatus.COMPLETED, artifacts)


class CharacterLockStage(Stage):
    name = "character_lock"
    weight = 0.5

    def __init__(self, character_engine: CharacterEngine) -> None:
        self.character_engine = character_engine

    def run(self, ctx: JobContext) -> StageResult:
        images = ctx.artifacts.get("images", [])
        if not ctx.characters or not images:
            _report(ctx, self.name, 100, "No characters to lock")
            return StageResult(self.name, StageStatus.SKIPPED, [])
        for i, art in enumerate(images):
            for char in ctx.characters:
                self.character_engine.verify(art, char)
            _report(ctx, self.name, (i + 1) / len(images) * 100)
        return StageResult(self.name, StageStatus.COMPLETED, [])


class AnimationStage(Stage):
    name = "animation"
    weight = 3.0

    def __init__(self, backend: AnimationBackend) -> None:
        self.backend = backend

    def run(self, ctx: JobContext) -> StageResult:
        images = ctx.artifacts.get("images", [])
        self.backend.output_dir = ctx.workdir / "clips"  # type: ignore[attr-defined]
        clips: list[Artifact] = []
        with self.backend:
            for i, (scene, img) in enumerate(zip(ctx.scenes, images)):
                _report(ctx, self.name, i / max(1, len(images)) * 100, f"Animating scene {i + 1}")
                clips.append(self.backend.animate(img, scene, ctx.config))
        ctx.artifacts["clips"] = clips
        _report(ctx, self.name, 100, f"{len(clips)} clips")
        return StageResult(self.name, StageStatus.COMPLETED, clips)


class VoiceStage(Stage):
    name = "voice"
    weight = 1.0

    def __init__(self, backend: VoiceBackend) -> None:
        self.backend = backend

    def run(self, ctx: JobContext) -> StageResult:
        out_dir = ctx.workdir / "voice"
        self.backend.output_dir = out_dir  # type: ignore[attr-defined]
        narrations: list[Artifact] = []
        has_narration = any(s.narration.strip() for s in ctx.scenes)
        if not has_narration:
            _report(ctx, self.name, 100, "No narration")
            return StageResult(self.name, StageStatus.SKIPPED, [])
        with self.backend:
            for i, scene in enumerate(ctx.scenes):
                art = self.backend.synthesize(
                    scene.narration, emotion=scene.emotion or "neutral",
                    out_path=out_dir / f"narration_s{scene.index}.wav",
                )
                art.scene_index = scene.index
                narrations.append(art)
                _report(ctx, self.name, (i + 1) / len(ctx.scenes) * 100)
        ctx.artifacts["voice"] = narrations
        return StageResult(self.name, StageStatus.COMPLETED, narrations)


class MusicStage(Stage):
    name = "music"
    weight = 1.5

    def __init__(self, backend: MusicBackend) -> None:
        self.backend = backend

    def run(self, ctx: JobContext) -> StageResult:
        total = sum(s.duration_sec for s in ctx.scenes) or 8.0
        mood = next((s.music_mood for s in ctx.scenes if s.music_mood), "cinematic ambient")
        self.backend.output_dir = ctx.workdir / "music"  # type: ignore[attr-defined]
        _report(ctx, self.name, 20, f"Scoring ({mood})…")
        with self.backend:
            art = self.backend.compose_music(mood, duration_sec=total, out_path=ctx.workdir / "music" / "score.wav")
        ctx.artifacts["music"] = [art]
        _report(ctx, self.name, 100, "Score ready")
        return StageResult(self.name, StageStatus.COMPLETED, [art])


class ComposeStage(Stage):
    name = "compose"
    weight = 1.0

    def __init__(self, composer: Composer) -> None:
        self.composer = composer

    def run(self, ctx: JobContext) -> StageResult:
        from ai_engine.compose.ffmpeg_composer import FFmpegComposer

        clips = ctx.artifacts.get("clips", [])
        narration = ctx.artifacts.get("voice") or None
        music = (ctx.artifacts.get("music") or [None])[0]
        self.composer.output_dir = ctx.workdir  # type: ignore[attr-defined]

        # build + write SRT subtitles from narration
        subtitle_art = None
        if isinstance(self.composer, FFmpegComposer) and narration:
            srt = self.composer.build_srt(
                clips,
                narrations={s.index: s.narration for s in ctx.scenes},
                durations={s.index: s.duration_sec for s in ctx.scenes},
            )
            if srt.strip():
                srt_path = ctx.workdir / "subtitles.srt"
                srt_path.write_text(srt, "utf-8")
                subtitle_art = Artifact(path=srt_path, kind="subtitle")

        _report(ctx, self.name, 30, "Stitching final cut…")
        final = self.composer.compose(
            clips, narration=narration, music=music, subtitles=subtitle_art,
            aspect_ratio=ctx.config.aspect_ratio, out_path=ctx.workdir / "final.mp4",
        )
        ctx.artifacts["final"] = [final]
        _report(ctx, self.name, 100, "Done")
        return StageResult(self.name, StageStatus.COMPLETED, [final])
