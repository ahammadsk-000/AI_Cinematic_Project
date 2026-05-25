"""Worker-side Celery app. Registers the task under the SAME name the backend
enqueues (cineforge.generate_video). Mirrors the backend's queue settings so a
killed Colab session returns its job to the queue (acks_late) and only one heavy
job runs at a time (prefetch=1)."""

from __future__ import annotations

import ssl

from celery import Celery

from gpu_worker.config import load_worker_config
from gpu_worker.tasks import run_generation

_cfg = load_worker_config()

TASK_GENERATE_VIDEO = "cineforge.generate_video"

celery_app = Celery("cineforge_worker", broker=_cfg.celery_broker_url, backend=_cfg.celery_result_backend)
celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    task_serializer="json",
    accept_content=["json"],
    task_default_queue="video",
    # a single GPU job can run long; give it room
    task_time_limit=60 * 60,
    task_soft_time_limit=55 * 60,
)

# TLS Redis (Upstash): configure SSL via config object (robust across versions).
if _cfg.celery_broker_url.startswith("rediss://"):
    celery_app.conf.broker_use_ssl = {"ssl_cert_reqs": ssl.CERT_NONE}
if _cfg.celery_result_backend.startswith("rediss://"):
    celery_app.conf.redis_backend_use_ssl = {"ssl_cert_reqs": ssl.CERT_NONE}


@celery_app.task(name=TASK_GENERATE_VIDEO, bind=True, max_retries=2)
def generate_video(self, job_id: str) -> str:
    return run_generation(job_id)
