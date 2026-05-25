"""Video-job use-cases: create+enqueue, list, fetch, scene editing, cancel, regenerate.

Orchestrates the job repository and the Celery enqueue client. Knows nothing
about how the GPU actually generates anything — that's the worker's job. This is
the seam between business logic and the inference layer.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.enums import JobStatus
from app.models.job import Job
from app.repositories.job_repo import JobRepository
from app.schemas.job import JobCreate
from app.schemas.scene import SceneUpdate
from app.tasks.celery_app import enqueue_video_job

log = get_logger(__name__)

#: statuses from which a job may be re-run / cancelled
_TERMINAL = {JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED}


class JobService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.jobs = JobRepository(session)

    async def create(self, user_id: uuid.UUID, data: JobCreate) -> Job:
        job = Job(
            user_id=user_id,
            title=data.title,
            script=data.script,
            style=data.style,
            aspect_ratio=data.aspect_ratio,
            status=JobStatus.PENDING,
        )
        await self.jobs.add(job)
        # commit happens at the request boundary; we need the row durable before
        # enqueue so the worker can read it. Flush already populated job.id.
        await self.session.commit()
        task_id = enqueue_video_job(str(job.id))
        await self.jobs.update_progress(job, status=JobStatus.QUEUED)
        log.info("job %s queued (celery task %s)", job.id, task_id)
        return job

    async def list(self, user_id: uuid.UUID, *, limit: int = 50, offset: int = 0) -> list[Job]:
        return await self.jobs.list_for_user(user_id, limit=limit, offset=offset)

    async def get(self, job_id: uuid.UUID, user_id: uuid.UUID) -> Job:
        job = await self.jobs.get_for_user(job_id, user_id)
        if not job:
            raise NotFoundError("Job not found.")
        return job

    async def cancel(self, job_id: uuid.UUID, user_id: uuid.UUID) -> Job:
        job = await self.get(job_id, user_id)
        if job.status in _TERMINAL:
            raise ValidationError(f"Job is already {job.status.value}; cannot cancel.")
        # NOTE: cooperative cancel — the worker checks status between stages.
        return await self.jobs.update_progress(job, status=JobStatus.CANCELLED)

    async def regenerate(self, job_id: uuid.UUID, user_id: uuid.UUID) -> Job:
        """Re-enqueue a finished/failed job (advanced feature: regeneration)."""
        job = await self.get(job_id, user_id)
        if job.status not in _TERMINAL:
            raise ValidationError("Job is still in progress.")
        await self.jobs.update_progress(
            job, status=JobStatus.PENDING, stage=None, pct=0.0, error=None
        )
        await self.session.commit()
        enqueue_video_job(str(job.id))
        return await self.jobs.update_progress(job, status=JobStatus.QUEUED)

    async def edit_scene(
        self, job_id: uuid.UUID, user_id: uuid.UUID, scene_index: int, patch: SceneUpdate
    ) -> Job:
        """Apply a partial scene edit (Phase 3 scene-editing UI). Only mutates the
        scene rows; the user then triggers regenerate to re-render with edits."""
        job = await self.get(job_id, user_id)
        scene = next((s for s in job.scenes if s.index == scene_index), None)
        if scene is None:
            raise NotFoundError(f"Scene {scene_index} not found on this job.")
        for field, value in patch.model_dump(exclude_unset=True).items():
            setattr(scene, field, value)
        await self.session.flush()
        return job
