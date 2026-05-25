"""Phase 7 tests — GPU-tier auto-tuning, worker heartbeat, and the stalled-job
reaper. All on CPU; Redis is faked and the DB is a temp sqlite file (so the
reaper's multiple async sessions share state)."""

from __future__ import annotations

import os
import sys
import tempfile
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "ai_engine"))
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT))

# temp file DB (shared across the reaper's async sessions) + test secret
_DB_FILE = Path(tempfile.gettempdir()) / "cineforge_reaper_test.db"
_DB_FILE.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_DB_FILE.as_posix()}"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["ENVIRONMENT"] = "dev"


# --------------------------------------------------------------------------- #
# GPU tiers (pure)
# --------------------------------------------------------------------------- #
def test_detect_tier_thresholds():
    from ai_engine.utils.gpu_tiers import detect_tier

    assert detect_tier(0).name == "cpu"
    assert detect_tier(6).name == "low"
    assert detect_tier(15).name == "t4"
    assert detect_tier(40).name == "high"


def test_apply_tier_clamps_down_only():
    from ai_engine.interfaces import GenerationConfig
    from ai_engine.utils.gpu_tiers import TIERS, apply_tier

    cfg = GenerationConfig(width=1024, height=576, frames_per_clip=16, steps=28)
    apply_tier(cfg, TIERS["low"])      # low caps longest edge at 768
    assert max(cfg.width, cfg.height) <= 768
    assert cfg.width % 8 == 0 and cfg.height % 8 == 0
    assert cfg.frames_per_clip <= TIERS["low"].frames_per_clip
    assert cfg.steps <= TIERS["low"].steps

    # never scales UP a smaller explicit request
    small = GenerationConfig(width=512, height=288, frames_per_clip=8, steps=18)
    apply_tier(small, TIERS["high"])
    assert small.width == 512 and small.frames_per_clip == 8


# --------------------------------------------------------------------------- #
# worker heartbeat
# --------------------------------------------------------------------------- #
def test_reporter_writes_self_expiring_heartbeat(monkeypatch):
    import gpu_worker.progress as progress_mod

    sets = []

    class FakeRedis:
        def set(self, key, val, ex=None):
            sets.append((key, val, ex))

        def delete(self, key):
            sets.append(("DEL", key, None))

        def publish(self, *a):
            pass

    monkeypatch.setattr(progress_mod.redis.Redis, "from_url", classmethod(lambda cls, *a, **k: FakeRedis()))
    from gpu_worker.config import WorkerConfig

    rep = progress_mod.RedisDBReporter(WorkerConfig(), "j1")
    rep.beat()
    key, _, ex = sets[-1]
    assert key == "job:j1:heartbeat"
    assert ex == progress_mod.HEARTBEAT_TTL_S      # TTL set so a dead worker's key vanishes
    rep.clear_heartbeat()
    assert sets[-1][0] == "DEL"


# --------------------------------------------------------------------------- #
# reaper (end-to-end against sqlite)
# --------------------------------------------------------------------------- #
class FakeAsyncRedis:
    """heartbeats: set of job-id strings considered 'alive'."""

    def __init__(self, alive: set[str]):
        self.alive = alive

    async def exists(self, key: str) -> int:
        jid = key.split(":")[1]
        return 1 if jid in self.alive else 0

    async def aclose(self):
        pass


@pytest.mark.anyio
async def test_reaper_requeues_jobs_without_heartbeat(monkeypatch):
    import app.services.reaper as reaper_mod
    from app.db.session import engine
    from app.models import Base
    from app.models.enums import JobStatus
    from app.models.job import Job
    from app.models.user import User
    from app.db.session import SessionLocal

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    # seed: one user, two RUNNING jobs — one with a live heartbeat, one stalled
    alive_id, dead_id = uuid.uuid4(), uuid.uuid4()
    async with SessionLocal() as s:
        u = User(email="r@b.com", hashed_password="x")
        s.add(u)
        await s.flush()
        for jid in (alive_id, dead_id):
            s.add(Job(id=jid, user_id=u.id, title="t", script="s", status=JobStatus.RUNNING))
        await s.commit()

    enqueued: list[str] = []
    monkeypatch.setattr(reaper_mod, "enqueue_video_job", lambda jid: enqueued.append(jid))

    fake_redis = FakeAsyncRedis(alive={str(alive_id)})
    n = await reaper_mod.reap_once(fake_redis)

    assert n == 1
    assert enqueued == [str(dead_id)]          # only the heartbeat-less job re-enqueued
    async with SessionLocal() as s:
        assert (await s.get(Job, dead_id)).status == JobStatus.QUEUED
        assert (await s.get(Job, alive_id)).status == JobStatus.RUNNING

    await engine.dispose()


@pytest.fixture
def anyio_backend():
    return "asyncio"
