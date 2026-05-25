"""Progress bus over Redis pub/sub.

The GPU worker PUBLISHES stage progress to ``job:{id}:progress``; the API's SSE
endpoint SUBSCRIBES and relays to the browser. This is the live channel; durable
state still lives in the Job row (updated in parallel) so refreshes are accurate.

ai_engine never imports this — the worker passes a thin callable satisfying the
ProgressReporter Protocol that forwards here.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator

import redis.asyncio as aioredis

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

_CHANNEL = "job:{job_id}:progress"


def channel(job_id: str) -> str:
    return _CHANNEL.format(job_id=job_id)


async def publish(redis: aioredis.Redis, job_id: str, event: dict) -> None:
    await redis.publish(channel(job_id), json.dumps(event, default=str))


async def subscribe(job_id: str) -> AsyncGenerator[dict, None]:
    """Yield progress events for a job until a terminal status arrives.

    Each event is a dict (see schemas.job.JobProgress). The generator closes the
    Redis connection on completion or client disconnect.
    """
    redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    pubsub = redis.pubsub()
    await pubsub.subscribe(channel(job_id))
    try:
        async for msg in pubsub.listen():
            if msg.get("type") != "message":
                continue
            try:
                event = json.loads(msg["data"])
            except (json.JSONDecodeError, TypeError):
                log.warning("dropping malformed progress event for job %s", job_id)
                continue
            yield event
            if event.get("status") in {"completed", "failed", "cancelled"}:
                break
    finally:
        await pubsub.unsubscribe(channel(job_id))
        await pubsub.aclose()
        await redis.aclose()


def get_redis() -> aioredis.Redis:
    """Sync factory for a publish-side client (used by request handlers)."""
    return aioredis.from_url(settings.redis_url, decode_responses=True)
