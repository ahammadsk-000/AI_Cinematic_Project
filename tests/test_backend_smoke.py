"""Phase 2 smoke test: register -> login -> create job -> list -> fetch.

Runs fully in-process against in-memory SQLite (aiosqlite). The Celery enqueue
is monkeypatched so no Redis/broker is needed. This proves the clean-architecture
wiring (api -> service -> repo -> model) and JWT auth work end to end.
"""

from __future__ import annotations

import asyncio
import os

import pytest

# point settings at sqlite + dummy secret BEFORE importing the app
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["SECRET_KEY"] = "test-secret-key-please-ignore"
os.environ["ENVIRONMENT"] = "dev"

from httpx import ASGITransport, AsyncClient  # noqa: E402

import app.services.job_service as job_service_mod  # noqa: E402
from app.db.session import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def _reset_schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)


def test_full_flow(monkeypatch):
    # stub Celery enqueue: no broker in tests
    monkeypatch.setattr(job_service_mod, "enqueue_video_job", lambda job_id: "fake-task-id")

    async def scenario():
        await _reset_schema()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # register
            r = await client.post("/api/v1/auth/register", json={
                "email": "a@b.com", "password": "supersecret", "full_name": "Alice",
            })
            assert r.status_code == 201, r.text
            token = r.json()["access_token"]
            auth = {"Authorization": f"Bearer {token}"}

            # duplicate register -> 409
            r = await client.post("/api/v1/auth/register", json={
                "email": "a@b.com", "password": "supersecret",
            })
            assert r.status_code == 409, r.text

            # login via OAuth2 form
            r = await client.post("/api/v1/auth/login", data={
                "username": "a@b.com", "password": "supersecret",
            })
            assert r.status_code == 200, r.text

            # me (protected)
            r = await client.get("/api/v1/auth/me", headers=auth)
            assert r.status_code == 200 and r.json()["email"] == "a@b.com"

            # protected route without token -> 401
            r = await client.get("/api/v1/auth/me")
            assert r.status_code == 401

            # create job (enqueue stubbed)
            r = await client.post("/api/v1/jobs", headers=auth, json={
                "script": "A boy walks through a rainy cyberpunk city.",
                "title": "Cyber Boy", "style": "cyberpunk", "aspect_ratio": "9:16",
            })
            assert r.status_code == 201, r.text
            job = r.json()
            assert job["status"] == "queued"
            assert job["style"] == "cyberpunk"

            # list + fetch
            r = await client.get("/api/v1/jobs", headers=auth)
            assert r.status_code == 200 and len(r.json()) == 1
            jid = job["id"]
            r = await client.get(f"/api/v1/jobs/{jid}", headers=auth)
            assert r.status_code == 200 and r.json()["id"] == jid

        await engine.dispose()

    asyncio.run(scenario())
