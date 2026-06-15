"""Cineforge FastAPI application entrypoint.

Phase 1 ships a minimal, runnable app: health check + CORS + logging + the v1
router mount point. Auth, jobs, and SSE endpoints are filled in during Phase 2.
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1.errors import register_exception_handlers
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.logging import get_logger, setup_logging
from app.db.session import engine
from app.models import Base

setup_logging()
log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Starting %s [env=%s]", settings.app_name, settings.environment)
    # Ensure the schema exists on boot. There are no Alembic migration scripts
    # yet, so create_all is the bootstrap in every environment. It is idempotent
    # (creates only missing tables; never drops or alters), so it is safe in prod.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    log.info("DB schema ensured (create_all).")

    # Start the stalled-job reaper (re-queues jobs whose GPU worker died).
    reaper_task: asyncio.Task | None = None
    if settings.enable_reaper:
        from app.services.reaper import run_reaper_loop

        reaper_task = asyncio.create_task(run_reaper_loop(settings.reaper_interval_s))

    yield

    if reaper_task:
        reaper_task.cancel()
    await engine.dispose()
    log.info("Shutting down %s", settings.app_name)


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    debug=settings.debug,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)


@app.get("/health", tags=["meta"])
async def health() -> dict:
    """Liveness probe — used by Render/Railway and the GPU worker heartbeat."""
    return {"status": "ok", "service": settings.app_name, "env": settings.environment}


app.include_router(api_router, prefix=settings.api_v1_prefix)

# Serve generated artifacts (final MP4s, scene images) written by the GPU worker.
# In split deploys this is backed by shared/object storage; locally it's the bind mount.
_media_root = os.path.join(settings.storage_root)
os.makedirs(_media_root, exist_ok=True)
app.mount("/media", StaticFiles(directory=_media_root), name="media")
