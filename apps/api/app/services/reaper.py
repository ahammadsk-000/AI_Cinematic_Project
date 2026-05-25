"""Stalled-job reaper — completes the recovery story (docs/ARCHITECTURE.md §7).

A GPU worker on Colab/Kaggle can vanish mid-render (session killed, network drop).
Celery's acks_late re-queues the *task*, but if the broker entry was already acked
or the worker died between ack and crash, a job can be left stuck in RUNNING with
no worker. The worker writes a self-expiring Redis heartbeat each tick; this reaper
periodically finds RUNNING jobs whose heartbeat has expired and re-queues them.

Runs as a lightweight asyncio loop inside the always-on API (no extra process).
Idempotent and safe: it only touches RUNNING jobs with a missing heartbeat.
"""

from __future__ import annotations

import asyncio

import redis.asyncio as aioredis

from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.models.enums import JobStatus
from app.repositories.job_repo import JobRepository
from app.tasks.celery_app import enqueue_video_job

log = get_logger(__name__)

# must match gpu_worker.progress.heartbeat_key / HEARTBEAT_TTL_S
def _heartbeat_key(job_id: str) -> str:
    return f"job:{job_id}:heartbeat"


async def reap_once(redis: aioredis.Redis) -> int:
    """Re-queue every RUNNING job whose worker heartbeat has expired. Returns the
    number of jobs re-queued."""
    stalled_ids: list[str] = []
    async with SessionLocal() as session:
        repo = JobRepository(session)
        for job in await repo.list_by_status(JobStatus.RUNNING):
            if await redis.exists(_heartbeat_key(str(job.id))):
                continue  # worker is alive
            log.warning("reaper: job %s is RUNNING with no heartbeat — re-queuing", job.id)
            await repo.update_progress(job, status=JobStatus.QUEUED, stage=None)
            stalled_ids.append(str(job.id))
        await session.commit()

    # re-enqueue after the DB commit so a broker hiccup can't leave the row QUEUED
    # but un-enqueued in the same failed transaction.
    for job_id in stalled_ids:
        enqueue_video_job(job_id)
    return len(stalled_ids)


async def run_reaper_loop(interval_s: int = 60) -> None:
    """Background loop started from the app lifespan. Cancelled on shutdown."""
    redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    log.info("stalled-job reaper started (every %ds)", interval_s)
    try:
        while True:
            try:
                n = await reap_once(redis)
                if n:
                    log.info("reaper re-queued %d stalled job(s)", n)
            except Exception:  # noqa: BLE001 - never let the loop die
                log.exception("reaper pass failed")
            await asyncio.sleep(interval_s)
    finally:
        await redis.aclose()
