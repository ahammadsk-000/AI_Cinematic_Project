from __future__ import annotations

import uuid

from sqlalchemy import select

from app.models.enums import JobStatus
from app.models.job import Job
from app.repositories.base import BaseRepository


class JobRepository(BaseRepository[Job]):
    model = Job

    async def list_for_user(
        self, user_id: uuid.UUID, *, limit: int = 50, offset: int = 0
    ) -> list[Job]:
        res = await self.session.execute(
            select(Job)
            .where(Job.user_id == user_id)
            .order_by(Job.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(res.scalars().all())

    async def get_for_user(self, job_id: uuid.UUID, user_id: uuid.UUID) -> Job | None:
        res = await self.session.execute(
            select(Job).where(Job.id == job_id, Job.user_id == user_id)
        )
        return res.scalar_one_or_none()

    async def list_by_status(self, status: JobStatus, *, limit: int = 200) -> list[Job]:
        res = await self.session.execute(
            select(Job).where(Job.status == status).limit(limit)
        )
        return list(res.scalars().all())

    async def update_progress(
        self,
        job: Job,
        *,
        status: JobStatus | None = None,
        stage: str | None = None,
        pct: float | None = None,
        error: str | None = None,
        result_path: str | None = None,
    ) -> Job:
        """Persist a progress tick. Used by the SSE consumer / worker callback so
        a page refresh shows current state even when the live stream was missed."""
        if status is not None:
            job.status = status
        if stage is not None:
            job.current_stage = stage
        if pct is not None:
            job.progress_pct = pct
        if error is not None:
            job.error = error
        if result_path is not None:
            job.result_path = result_path
        await self.session.flush()
        return job
