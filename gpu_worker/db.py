"""Sync DB access for the worker.

Shares the ORM schema with the backend (imports app.models — the single source of
truth) but uses its own SYNC engine because Celery tasks are synchronous. Requires
apps/api on PYTHONPATH (the Colab/Kaggle notebooks and docker set this up).
"""

from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from gpu_worker.config import load_worker_config

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "postgres", "::1", None}


def _sync_url_with_ssl(url: str) -> str:
    """Cloud Postgres (Supabase/Neon) requires TLS. Append sslmode=require for
    psycopg2 when the host is remote. Local/SQLite untouched."""
    if not url.startswith("postgresql"):
        return url
    u = make_url(url)
    if u.host in _LOCAL_HOSTS or "sslmode" in (u.query or {}):
        return url
    # NOTE: str(url)/render_as_string() default to hide_password=True, replacing
    # the password with '***' which breaks auth. Must pass hide_password=False.
    return u.set(query={**u.query, "sslmode": "require"}).render_as_string(hide_password=False)


_cfg = load_worker_config()
_engine = create_engine(_sync_url_with_ssl(_cfg.sync_database_url), pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=_engine, class_=Session, expire_on_commit=False)


@contextmanager
def session_scope() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
