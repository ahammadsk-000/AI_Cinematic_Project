from __future__ import annotations

import asyncio
import json
import uuid

from fastapi import APIRouter, Query, status
from sse_starlette.sse import EventSourceResponse

from app.api.v1.deps import CurrentUser, JobSvc
from app.models.enums import JobStatus
from app.schemas.job import JobCreate, JobDetail, JobRead
from app.schemas.scene import SceneUpdate
from app.services import progress as progress_bus

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("", response_model=JobRead, status_code=status.HTTP_201_CREATED)
async def create_job(data: JobCreate, user: CurrentUser, jobs: JobSvc) -> JobRead:
    """Create a video job and enqueue it for the GPU worker."""
    job = await jobs.create(user.id, data)
    return JobRead.model_validate(job)


@router.get("", response_model=list[JobRead])
async def list_jobs(
    user: CurrentUser,
    jobs: JobSvc,
    limit: int = Query(50, le=100),
    offset: int = Query(0, ge=0),
) -> list[JobRead]:
    rows = await jobs.list(user.id, limit=limit, offset=offset)
    return [JobRead.model_validate(j) for j in rows]


@router.get("/{job_id}", response_model=JobDetail)
async def get_job(job_id: uuid.UUID, user: CurrentUser, jobs: JobSvc) -> JobDetail:
    job = await jobs.get(job_id, user.id)
    return JobDetail.model_validate(job)


@router.post("/{job_id}/cancel", response_model=JobRead)
async def cancel_job(job_id: uuid.UUID, user: CurrentUser, jobs: JobSvc) -> JobRead:
    job = await jobs.cancel(job_id, user.id)
    return JobRead.model_validate(job)


@router.post("/{job_id}/regenerate", response_model=JobRead)
async def regenerate_job(job_id: uuid.UUID, user: CurrentUser, jobs: JobSvc) -> JobRead:
    job = await jobs.regenerate(job_id, user.id)
    return JobRead.model_validate(job)


@router.patch("/{job_id}/scenes/{scene_index}", response_model=JobDetail)
async def edit_scene(
    job_id: uuid.UUID,
    scene_index: int,
    patch: SceneUpdate,
    user: CurrentUser,
    jobs: JobSvc,
) -> JobDetail:
    job = await jobs.edit_scene(job_id, user.id, scene_index, patch)
    return JobDetail.model_validate(job)


@router.get("/{job_id}/stream")
async def stream_progress(job_id: uuid.UUID, user: CurrentUser, jobs: JobSvc):
    """Server-Sent Events stream of live generation progress.

    Validates ownership first, then relays Redis pub/sub events. Emits the
    current persisted state immediately so a late subscriber isn't blank, then
    closes when the job reaches a terminal status.
    """
    job = await jobs.get(job_id, user.id)

    async def event_generator():
        # 1) immediate snapshot from durable state
        yield {
            "event": "snapshot",
            "data": JobRead.model_validate(job).model_dump_json(),
        }
        if job.status in {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}:
            return
        # 2) live relay
        try:
            async for event in progress_bus.subscribe(str(job_id)):
                yield {"event": "progress", "data": json.dumps(event, default=str)}
        except asyncio.CancelledError:  # client disconnected
            return

    return EventSourceResponse(event_generator())
