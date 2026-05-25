"""System / queue status — observability for the queue-dashboard UI.

Reports queue depth (length of the Celery list in Redis), live worker count
(best-effort Celery ping), and the caller's job-status breakdown. All checks are
defensive: a missing/slow broker yields nulls rather than a 500, so the dashboard
degrades gracefully when no GPU worker is connected.
"""

from __future__ import annotations

import redis.asyncio as aioredis
from fastapi import APIRouter
from sqlalchemy import func, select

from app.api.v1.deps import CurrentUser, DbSession
from app.core.config import settings
from app.models.enums import JobStatus
from app.models.job import Job

router = APIRouter(prefix="/system", tags=["system"])


async def _queue_depth() -> int | None:
    try:
        redis = aioredis.from_url(settings.celery_broker_url, decode_responses=True)
        try:
            return await redis.llen(settings.celery_queue)
        finally:
            await redis.aclose()
    except Exception:  # noqa: BLE001 - broker unreachable
        return None


def _active_workers() -> int | None:
    """Best-effort Celery worker ping. Sync + short timeout; None on failure."""
    try:
        from app.tasks.celery_app import celery_app

        replies = celery_app.control.ping(timeout=0.75)
        return len(replies) if replies else 0
    except Exception:  # noqa: BLE001
        return None


@router.get("/status")
async def system_status(user: CurrentUser, db: DbSession) -> dict:
    rows = await db.execute(
        select(Job.status, func.count()).where(Job.user_id == user.id).group_by(Job.status)
    )
    by_status = {s.value: 0 for s in JobStatus}
    for status, count in rows.all():
        by_status[status.value if isinstance(status, JobStatus) else status] = count

    workers = _active_workers()
    return {
        "queue_depth": await _queue_depth(),
        "active_workers": workers,
        "worker_online": (workers or 0) > 0,
        "jobs_by_status": by_status,
    }
