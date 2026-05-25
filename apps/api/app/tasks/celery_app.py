"""Celery client used by the BACKEND to enqueue jobs only.

Critically, the backend never imports the task *implementation* (which lives in
gpu_worker and pulls in torch/diffusers). It dispatches by task NAME via
send_task, so this CPU process stays free of GPU deps. The GPU worker registers
a task under the same name (TASK_GENERATE_VIDEO) and executes it.

Queue settings here are mirrored by the worker; acks_late + prefetch=1 mean a
killed Colab session returns its job to the queue (docs/ARCHITECTURE.md §7).
"""

from __future__ import annotations

import ssl

from celery import Celery

from app.core.config import settings

#: shared task name contract between backend (enqueue) and worker (execute)
TASK_GENERATE_VIDEO = "cineforge.generate_video"

celery_app = Celery(
    "cineforge",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_default_queue="video",
)

# TLS Redis (Upstash etc.): configure SSL via the config object rather than the
# URL query string — the latter's accepted spelling of ssl_cert_reqs varies across
# celery/kombu/redis-py versions and is a common source of startup errors.
if settings.celery_broker_url.startswith("rediss://"):
    celery_app.conf.broker_use_ssl = {"ssl_cert_reqs": ssl.CERT_NONE}
if settings.celery_result_backend.startswith("rediss://"):
    celery_app.conf.redis_backend_use_ssl = {"ssl_cert_reqs": ssl.CERT_NONE}


def enqueue_video_job(job_id: str) -> str:
    """Push a job onto the queue. Returns the Celery task id."""
    async_result = celery_app.send_task(TASK_GENERATE_VIDEO, args=[job_id], queue="video")
    return async_result.id
