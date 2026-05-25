"""Async SQLAlchemy engine + session factory + FastAPI dependency.

One engine per process. ``get_db`` yields a session scoped to a request and
guarantees commit-on-success / rollback-on-error semantics at the dependency
boundary so services don't each repeat that bookkeeping.

Cloud Postgres note: managed providers (Supabase, Neon, …) require TLS and often
sit behind a connection pooler (pgbouncer/Supavisor) that breaks asyncpg's
prepared-statement cache. For a non-local Postgres host we therefore enable SSL
(encrypt, no cert verify == sslmode=require) and disable the statement cache.
Local/SQLite are untouched.
"""

from __future__ import annotations

import ssl as _ssl
from collections.abc import AsyncGenerator

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "postgres", "::1", None}


def _connect_args(url: str) -> dict:
    """asyncpg connect args for a cloud Postgres. Empty for local/SQLite."""
    if "+asyncpg" not in url:
        return {}
    host = make_url(url).host
    if host in _LOCAL_HOSTS:
        return {}
    ctx = _ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = _ssl.CERT_NONE  # == sslmode=require: encrypt, skip CA verify
    return {"ssl": ctx, "statement_cache_size": 0}  # cache=0 → safe behind pgbouncer


engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,   # survive Supabase/Render idle-connection drops
    future=True,
    connect_args=_connect_args(settings.database_url),
)

SessionLocal = async_sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
