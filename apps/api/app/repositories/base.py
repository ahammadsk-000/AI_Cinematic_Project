"""Generic async repository. Concrete repos subclass and add query methods.

The repository layer is the ONLY layer permitted to touch SQLAlchemy
(docs/ARCHITECTURE.md §3). Services depend on these, never on the session
directly. Sessions are committed at the request boundary (db.session.get_db), so
repos flush but do not commit.
"""

from __future__ import annotations

import uuid
from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, id_: uuid.UUID) -> ModelT | None:
        return await self.session.get(self.model, id_)

    async def list(self, *, limit: int = 50, offset: int = 0) -> list[ModelT]:
        res = await self.session.execute(
            select(self.model).limit(limit).offset(offset)
        )
        return list(res.scalars().all())

    async def add(self, obj: ModelT) -> ModelT:
        self.session.add(obj)
        await self.session.flush()   # populate PK/defaults without committing
        return obj

    async def delete(self, obj: ModelT) -> None:
        await self.session.delete(obj)
        await self.session.flush()
