"""Worker entrypoint: `python -m gpu_worker`.

Optionally boots a local ComfyUI server (the Colab/Kaggle notebooks call
bootstrap directly), then starts the Celery worker that pulls video jobs from the
shared Redis queue.
"""

from __future__ import annotations

import os
import sys

from ai_engine.utils.logging import get_logger

log = get_logger("worker")


def main() -> None:
    if os.getenv("CINEFORGE_BOOTSTRAP_COMFYUI", "0") == "1":
        from gpu_worker import bootstrap

        bootstrap.ensure_comfyui()

    from gpu_worker.celery_app import celery_app

    log.info("starting Cineforge GPU worker (queue=video)")
    # solo pool is safest for GPU work (no fork issues with CUDA contexts)
    celery_app.worker_main(argv=["worker", "--loglevel=INFO", "--pool=solo", "--queues=video"])


if __name__ == "__main__":
    sys.exit(main())
