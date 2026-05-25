"""Progress bridge: satisfies ai_engine's ProgressReporter protocol.

The orchestrator calls this on every stage tick. It (1) publishes a JSON event to
the Redis channel the backend's SSE endpoint subscribes to, and (2) updates the
durable Job row, so both the live stream and a page refresh stay accurate. It also
provides cooperative cancellation: if the Job row has been flipped to CANCELLED,
the next tick raises JobCancelled to abort the pipeline cleanly.

ai_engine has no idea this exists — it only sees a callable matching the Protocol.
"""

from __future__ import annotations

import json

import redis

from gpu_worker.config import WorkerConfig


class JobCancelled(Exception):
    """Raised mid-pipeline when the user cancels the job."""


#: a job's heartbeat key auto-expires after this many seconds of worker silence;
#: the backend reaper re-queues jobs whose heartbeat has vanished (dead worker).
HEARTBEAT_TTL_S = 120


def _channel(job_id: str) -> str:
    return f"job:{job_id}:progress"


def heartbeat_key(job_id: str) -> str:
    return f"job:{job_id}:heartbeat"


class RedisDBReporter:
    def __init__(self, cfg: WorkerConfig, job_id: str, *, status: str = "running") -> None:
        self.cfg = cfg
        self.job_id = job_id
        self.status = status
        self._redis = redis.Redis.from_url(cfg.redis_url, decode_responses=True)

    def publish(self, *, status: str, stage: str | None, pct: float, message: str = "") -> None:
        event = {"job_id": self.job_id, "status": status, "stage": stage, "pct": pct, "message": message}
        self._redis.publish(_channel(self.job_id), json.dumps(event))

    def beat(self) -> None:
        """Refresh the self-expiring heartbeat. Call at task start and each tick so
        the reaper can tell a live worker from a dead one."""
        self._redis.set(heartbeat_key(self.job_id), "1", ex=HEARTBEAT_TTL_S)

    def clear_heartbeat(self) -> None:
        self._redis.delete(heartbeat_key(self.job_id))

    # --- ProgressReporter protocol: callable(stage, pct, message, **extra) --- #
    def __call__(self, *, stage: str, pct: float, message: str = "", **_extra) -> None:
        self._check_cancelled()
        self.beat()
        self._persist(stage=stage, pct=pct)
        self.publish(status=self.status, stage=stage, pct=pct, message=message)

    def _persist(self, *, stage: str, pct: float) -> None:
        # local import so this module is importable without the app on path (tests)
        from app.models.enums import JobStatus
        from app.models.job import Job
        from gpu_worker.db import session_scope

        with session_scope() as s:
            job = s.get(Job, _as_uuid(self.job_id))
            if job:
                job.status = JobStatus.RUNNING
                job.current_stage = stage
                job.progress_pct = pct

    def _check_cancelled(self) -> None:
        from app.models.enums import JobStatus
        from app.models.job import Job
        from gpu_worker.db import session_scope

        with session_scope() as s:
            job = s.get(Job, _as_uuid(self.job_id))
            if job and job.status == JobStatus.CANCELLED:
                raise JobCancelled(self.job_id)


def _as_uuid(value: str):
    import uuid

    return uuid.UUID(value) if not isinstance(value, uuid.UUID) else value
