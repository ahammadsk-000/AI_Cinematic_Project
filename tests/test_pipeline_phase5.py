"""Phase 5 tests — the video pipeline, all on CPU with no models/ffmpeg/network.

Fake backends stand in for the heavy adapters so we verify the parts we wrote:
orchestrator ordering, progress rescaling, manifest checkpoint + resume, VRAM
retry/shrink, the pure ffmpeg/ken-burns command builders, AnimateDiff graph
injection, registry wiring, and the worker's Redis progress event format.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "ai_engine"))
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT))  # for gpu_worker

from ai_engine.interfaces import (  # noqa: E402
    AnimationBackend,
    Artifact,
    AspectRatio,
    GenerationConfig,
    ImageBackend,
    MusicBackend,
    Scene,
    SceneBackend,
    StyleMode,
    VoiceBackend,
)
from ai_engine.orchestrator.pipeline import JobContext, StageStatus  # noqa: E402
from ai_engine.utils.vram import VRAMError  # noqa: E402


# --------------------------------------------------------------------------- #
# fakes
# --------------------------------------------------------------------------- #
def _touch(p: Path) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x")
    return p


class FakeSceneBackend(SceneBackend):
    def generate_scenes(self, script, *, style, max_scenes=8):
        return [
            Scene(index=0, summary="boy walks", environment="neon city", narration="He walked alone.", music_mood="synthwave", duration_sec=4),
            Scene(index=1, summary="rain falls", environment="alley", narration="", music_mood="synthwave", duration_sec=3),
        ]


class FakeImageBackend(ImageBackend):
    def __init__(self, oom_first=False):
        self.output_dir = Path.cwd()
        self._loaded = False
        self.oom_first = oom_first
        self.calls = 0

    @property
    def is_loaded(self):
        return self._loaded

    def load(self):
        self._loaded = True

    def unload(self):
        self._loaded = False

    def generate_image(self, scene, cfg, *, characters=None, control_image=None):
        self.calls += 1
        if self.oom_first and self.calls == 1:
            raise VRAMError("cuda out of memory")
        return Artifact(path=_touch(self.output_dir / f"img_{scene.index}.png"), kind="image", scene_index=scene.index)


class FakeAnimationBackend(AnimationBackend):
    def __init__(self):
        self.output_dir = Path.cwd()
        self._loaded = False

    @property
    def is_loaded(self):
        return self._loaded

    def load(self):
        self._loaded = True

    def unload(self):
        self._loaded = False

    def animate(self, image, scene, cfg):
        return Artifact(path=_touch(self.output_dir / f"clip_{scene.index}.mp4"), kind="video", scene_index=scene.index)


class FakeVoiceBackend(VoiceBackend):
    def __init__(self):
        self.output_dir = Path.cwd()

    @property
    def is_loaded(self):
        return True

    def load(self):
        pass

    def unload(self):
        pass

    def synthesize(self, text, *, voice="narrator_male", language="en", emotion="neutral", out_path=None):
        return Artifact(path=_touch(out_path or self.output_dir / "n.wav"), kind="audio")


class FakeMusicBackend(MusicBackend):
    def __init__(self):
        self.output_dir = Path.cwd()

    @property
    def is_loaded(self):
        return True

    def load(self):
        pass

    def unload(self):
        pass

    def compose_music(self, mood, *, duration_sec, out_path=None):
        return Artifact(path=_touch(out_path or self.output_dir / "score.wav"), kind="audio", meta={"mood": mood})


class FakeComposer:
    def __init__(self):
        self.output_dir = Path.cwd()
        self.received = {}

    def compose(self, clips, *, narration=None, music=None, subtitles=None, aspect_ratio=AspectRatio.WIDE, out_path=None):
        self.received = {"clips": len(clips), "narration": narration, "music": music}
        return Artifact(path=_touch(out_path or self.output_dir / "final.mp4"), kind="video")


def _build_stages(image_backend=None):
    from ai_engine.character.engine import IPAdapterCharacterEngine
    from ai_engine.orchestrator.stages import (
        AnimationStage, CharacterLockStage, ComposeStage, ImageGenerationStage,
        MusicStage, PromptEnhancementStage, SceneGenerationStage, VoiceStage,
    )
    from ai_engine.scene.prompt_enhancer import TemplatePromptEnhancer

    ce = IPAdapterCharacterEngine()
    return [
        SceneGenerationStage(FakeSceneBackend()),
        PromptEnhancementStage(TemplatePromptEnhancer()),
        ImageGenerationStage(image_backend or FakeImageBackend(), ce),
        CharacterLockStage(ce),
        AnimationStage(FakeAnimationBackend()),
        VoiceStage(FakeVoiceBackend()),
        MusicStage(FakeMusicBackend()),
        ComposeStage(FakeComposer()),
    ]


def _ctx(tmp_path):
    events = []
    ctx = JobContext(
        job_id="job1",
        script="a boy in a rainy city",
        workdir=tmp_path / "job1",
        config=GenerationConfig(style=StyleMode.CYBERPUNK, aspect_ratio=AspectRatio.VERTICAL),
        report=lambda *, stage, pct, message="", **k: events.append((stage, pct, message)),
    )
    return ctx, events


# --------------------------------------------------------------------------- #
# orchestrator
# --------------------------------------------------------------------------- #
def test_orchestrator_runs_full_pipeline(tmp_path):
    from ai_engine.orchestrator import manifest
    from ai_engine.orchestrator.runner import DefaultOrchestrator

    ctx, events = _ctx(tmp_path)
    DefaultOrchestrator(_build_stages()).run(ctx)

    # all eight stages recorded as completed in the manifest
    data = manifest.load(ctx.workdir)
    assert set(data["completed"]) == {
        "scene_generation", "prompt_enhancement", "image_generation", "character_lock",
        "animation", "voice", "music", "compose",
    }
    # final artifact produced + global progress reached 100
    assert ctx.artifacts["final"][0].path.name == "final.mp4"
    assert max(pct for _, pct, _ in events) == 100.0
    # progress is globally non-decreasing (rescaling works across stage bands)
    pcts = [pct for _, pct, _ in events]
    assert pcts == sorted(pcts)


def test_orchestrator_resume_skips_completed(tmp_path):
    from ai_engine.orchestrator.runner import DefaultOrchestrator

    ctx, _ = _ctx(tmp_path)
    DefaultOrchestrator(_build_stages()).run(ctx)

    # second run with a fresh image backend: if stages are skipped, it never renders
    fresh_img = FakeImageBackend()
    ctx2, _ = _ctx(tmp_path)
    DefaultOrchestrator(_build_stages(image_backend=fresh_img)).run(ctx2)
    assert fresh_img.calls == 0  # image_generation was skipped on resume


def test_orchestrator_vram_retry_shrinks_and_recovers(tmp_path):
    from ai_engine.orchestrator.runner import DefaultOrchestrator

    ctx, _ = _ctx(tmp_path)
    start_w = ctx.config.width
    oom_backend = FakeImageBackend(oom_first=True)
    DefaultOrchestrator(_build_stages(image_backend=oom_backend)).run(ctx)
    assert oom_backend.calls >= 2          # failed once, retried
    assert ctx.config.width < start_w      # resolution was shrunk before retry


# --------------------------------------------------------------------------- #
# pure command / graph builders
# --------------------------------------------------------------------------- #
def test_kenburns_command_builder(tmp_path):
    from ai_engine.animation.kenburns_backend import KenBurnsAnimationBackend

    be = KenBurnsAnimationBackend()
    img = Artifact(path=tmp_path / "i.png", kind="image", scene_index=0)
    scene = Scene(index=0, summary="x", camera="slow push-in")
    cmd = be.build_command(img, scene, GenerationConfig(fps=12, width=576, height=1024), tmp_path / "o.mp4")
    assert "zoompan" in " ".join(cmd)
    assert "libx264" in cmd


def test_ffmpeg_srt_builder():
    from ai_engine.compose.ffmpeg_composer import FFmpegComposer

    clips = [Artifact(path=Path("c0.mp4"), kind="video", scene_index=0),
             Artifact(path=Path("c1.mp4"), kind="video", scene_index=1)]
    srt = FFmpegComposer.build_srt(clips, narrations={0: "Hello world", 1: ""}, durations={0: 4.0, 1: 3.0})
    assert "Hello world" in srt
    assert "00:00:00,000 --> 00:00:04,000" in srt
    assert srt.count("-->") == 1  # only scene 0 had narration


def test_ffmpeg_mux_command_mixes_audio():
    from ai_engine.compose.ffmpeg_composer import FFmpegComposer

    cmd = FFmpegComposer.build_mux_command(
        Path("v.mp4"), Path("out.mp4"),
        narration=Path("n.wav"), music=Path("m.wav"), subtitles=None, dims=(720, 1280),
    )
    joined = " ".join(cmd)
    assert "amix=inputs=2" in joined        # narration + ducked music mixed
    assert "scale=720:1280" in joined        # letterboxed to vertical
    assert "volume=0.3" in joined            # music ducked


def test_animatediff_graph_injection():
    from ai_engine.animation.comfyui_animatediff import ComfyUIAnimateDiffBackend

    be = ComfyUIAnimateDiffBackend("http://fake:8188")
    be.load_workflow()
    scene = Scene(index=0, summary="x", prompt="a cat", negative_prompt="dog", motion="pan left")
    graph = be.build_graph("img_0.png", scene, GenerationConfig(frames_per_clip=16, fps=12, seed=7))
    assert graph["10"]["inputs"]["image"] == "img_0.png"
    assert graph["2"]["inputs"]["text"] == "a cat"
    assert graph["7"]["inputs"]["batch_size"] == 16
    assert graph["6"]["inputs"]["frame_rate"] == 12
    assert graph["5"]["inputs"]["seed"] == 7


def test_svd_graph_injection():
    from ai_engine.animation.comfyui_animatediff import ComfyUIAnimateDiffBackend

    be = ComfyUIAnimateDiffBackend("http://fake:8188", workflow="svd")
    be.load_workflow()
    scene = Scene(index=0, summary="x")
    graph = be.build_graph("frame.png", scene, GenerationConfig(width=1024, height=576, fps=8, seed=11))
    assert graph["10"]["inputs"]["image"] == "frame.png"   # uploaded still injected
    assert graph["3"]["inputs"]["width"] == 1024
    assert graph["3"]["inputs"]["height"] == 576
    assert graph["6"]["inputs"]["frame_rate"] == 8
    assert graph["5"]["inputs"]["seed"] == 11
    assert graph["3"]["inputs"]["video_frames"] == 14      # SVD native length, not overridden


# --------------------------------------------------------------------------- #
# registry
# --------------------------------------------------------------------------- #
def test_registry_builds_all_phase5_backends():
    from ai_engine.backends import registry
    from ai_engine.config import EngineConfig

    cfg = EngineConfig()
    assert registry.build_animation_backend(cfg).__class__.__name__ == "ComfyUIAnimateDiffBackend"
    cfg.animation_backend = "kenburns"
    assert registry.build_animation_backend(cfg).__class__.__name__ == "KenBurnsAnimationBackend"
    assert registry.build_voice_backend(cfg) is not None
    assert registry.build_music_backend(cfg) is not None
    assert registry.build_composer(cfg) is not None


# --------------------------------------------------------------------------- #
# worker progress reporter
# --------------------------------------------------------------------------- #
def test_worker_reporter_publishes_expected_event(monkeypatch):
    import gpu_worker.progress as progress_mod

    published = []

    class FakeRedis:
        def publish(self, channel, data):
            published.append((channel, data))

        def set(self, *a, **k):  # heartbeat beat()
            pass

    monkeypatch.setattr(progress_mod.redis.Redis, "from_url", classmethod(lambda cls, *a, **k: FakeRedis()))
    from gpu_worker.config import WorkerConfig

    reporter = progress_mod.RedisDBReporter(WorkerConfig(), "abc-123")
    # avoid DB on the protocol call path
    monkeypatch.setattr(reporter, "_persist", lambda **k: None)
    monkeypatch.setattr(reporter, "_check_cancelled", lambda: None)

    reporter(stage="animation", pct=42.5, message="Animating scene 2")

    import json
    channel, payload = published[-1]
    evt = json.loads(payload)
    assert channel == "job:abc-123:progress"
    assert evt == {"job_id": "abc-123", "status": "running", "stage": "animation", "pct": 42.5, "message": "Animating scene 2"}
