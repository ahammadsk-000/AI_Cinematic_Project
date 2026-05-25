"""The single GPU task: generate_video(job_id).

This is the ONLY glue between Celery/DB and ai_engine. It loads the job, builds a
JobContext, runs the orchestrator (which does all the real work), then persists
scenes + assets and flips the job to COMPLETED. On a killed worker the task is
re-queued (acks_late) and the orchestrator resumes from the manifest checkpoint.
"""

from __future__ import annotations

import uuid

from ai_engine.config import load_config
from ai_engine.interfaces import AspectRatio, GenerationConfig, Scene, StyleMode
from ai_engine.orchestrator.factory import build_orchestrator
from ai_engine.orchestrator.pipeline import JobContext
from ai_engine.utils.gpu_tiers import apply_tier, detect_tier
from ai_engine.utils.logging import get_logger
from gpu_worker.config import load_worker_config
from gpu_worker.progress import JobCancelled, RedisDBReporter

log = get_logger("task")

# 16:9 / 9:16 / 1:1 -> (w, h) tuned for a T4 (multiples of 64)
_ASPECT_DIMS = {
    AspectRatio.WIDE: (1024, 576),
    AspectRatio.VERTICAL: (576, 1024),
    AspectRatio.SQUARE: (768, 768),
}


def _generation_config(engine_cfg, style: str, aspect: str) -> GenerationConfig:
    style_mode = StyleMode(style)
    ar = AspectRatio(aspect)
    w, h = _ASPECT_DIMS[ar]
    cfg = GenerationConfig(style=style_mode, aspect_ratio=ar, width=w, height=h, vram_budget_gb=engine_cfg.vram_budget_gb)
    # auto-tune to the detected GPU so we size the job before it can OOM
    tier = detect_tier()
    apply_tier(cfg, tier)
    if tier.force_kenburns and engine_cfg.animation_backend == "comfyui":
        log.info("tier %s: forcing kenburns animation (motion model won't fit)", tier.name)
        engine_cfg.animation_backend = "kenburns"
    return cfg


def run_generation(job_id: str) -> str:
    """Execute the full pipeline for a job. Returns the final video's media path.
    Separated from the Celery wrapper so it's directly callable in tests."""
    from app.models.asset import Asset
    from app.models.enums import AssetKind, JobStatus
    from app.models.job import Job
    from app.models.scene import Scene as SceneRow
    from gpu_worker.db import session_scope

    wcfg = load_worker_config()
    engine_cfg = load_config()
    reporter = RedisDBReporter(wcfg, job_id)

    # --- load job ---
    with session_scope() as s:
        job = s.get(Job, uuid.UUID(job_id))
        if job is None:
            log.error("job %s not found", job_id)
            return ""
        if job.status == JobStatus.CANCELLED:
            log.info("job %s already cancelled; skipping", job_id)
            return ""
        script, style, aspect = job.script, job.style.value, job.aspect_ratio.value

    workdir = engine_cfg.job_dir(job_id)
    ctx = JobContext(
        job_id=job_id,
        script=script,
        workdir=workdir,
        config=_generation_config(engine_cfg, style, aspect),
        report=reporter,
    )

    reporter.beat()  # claim the job; reaper won't re-queue while this is fresh
    reporter.publish(status="running", stage="scene_generation", pct=0, message="Starting…")
    try:
        orchestrator = build_orchestrator(engine_cfg)
        ctx = orchestrator.run(ctx)
    except JobCancelled:
        log.info("job %s cancelled mid-pipeline", job_id)
        reporter.clear_heartbeat()
        reporter.publish(status="cancelled", stage=None, pct=0, message="Cancelled")
        return ""
    except Exception as exc:  # noqa: BLE001 - persist failure, then re-raise for Celery retry policy
        log.exception("job %s failed", job_id)
        reporter.clear_heartbeat()
        _mark_failed(job_id, str(exc))
        reporter.publish(status="failed", stage=None, pct=0, message=str(exc))
        raise

    # --- persist results ---
    final = (ctx.artifacts.get("final") or [None])[0]
    media_path = f"/media/outputs/{job_id}/{final.path.name}" if final else None

    with session_scope() as s:
        job = s.get(Job, uuid.UUID(job_id))
        _persist_scenes(s, job, ctx.scenes, SceneRow)
        _persist_assets(s, job, ctx, Asset, AssetKind, job_id)
        job.status = JobStatus.COMPLETED
        job.progress_pct = 100.0
        job.current_stage = "compose"
        job.result_path = media_path

    reporter.clear_heartbeat()
    reporter.publish(status="completed", stage="compose", pct=100, message="Your video is ready")
    log.info("job %s completed -> %s", job_id, media_path)
    return media_path or ""


# --- persistence helpers --------------------------------------------------- #
def _persist_scenes(session, job, scenes: list[Scene], SceneRow) -> None:
    for sc in list(job.scenes):  # clear previous (regeneration)
        session.delete(sc)
    for sc in scenes:
        session.add(SceneRow(
            job_id=job.id, index=sc.index, summary=sc.summary, prompt=sc.prompt,
            negative_prompt=sc.negative_prompt, camera=sc.camera, lighting=sc.lighting,
            emotion=sc.emotion, environment=sc.environment, motion=sc.motion,
            music_mood=sc.music_mood, narration=sc.narration, duration_sec=sc.duration_sec,
        ))


def _persist_assets(session, job, ctx, Asset, AssetKind, job_id: str) -> None:
    for sc in list(job.assets):
        session.delete(sc)
    kind_map = {"image": AssetKind.IMAGE, "video": AssetKind.VIDEO, "audio": AssetKind.AUDIO, "subtitle": AssetKind.SUBTITLE}
    for stage, arts in ctx.artifacts.items():
        for art in arts:
            rel = f"/media/outputs/{job_id}/{art.path.name}"
            session.add(Asset(
                job_id=job.id, kind=kind_map.get(art.kind, AssetKind.JSON), stage=stage,
                scene_index=art.scene_index, path=rel, meta=art.meta or {},
            ))


def _mark_failed(job_id: str, error: str) -> None:
    from app.models.enums import JobStatus
    from app.models.job import Job
    from gpu_worker.db import session_scope

    with session_scope() as s:
        job = s.get(Job, uuid.UUID(job_id))
        if job:
            job.status = JobStatus.FAILED
            job.error = error
