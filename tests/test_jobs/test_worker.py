"""Test worker loop: claim queued job, race safety, zombie recovery."""

from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.jobs import HANDLERS, enqueue_job, register_handler
from app.jobs.worker import claim_next_job, recover_zombie_jobs, run_worker_iteration
from app.models import User
from app.models.job import Job, JobKind, JobStatus
from app.models.user import ROLE_ADMIN


@pytest.fixture(autouse=True)
def _clear_handlers():
    HANDLERS.clear()
    yield
    HANDLERS.clear()


@pytest.fixture
def file_db(tmp_path):
    """File-based SQLite cho test concurrency (in-memory không share giữa threads)."""
    db_path = tmp_path / "jobs_test.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", future=True)
    Base.metadata.create_all(engine)
    Local = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    yield Local
    engine.dispose()


def _make_admin(Local) -> int:
    with Local() as s:
        u = User(username="admin", password_hash="x", role=ROLE_ADMIN)
        s.add(u)
        s.commit()
        return u.id


def test_claim_next_returns_oldest_queued(file_db) -> None:
    admin_id = _make_admin(file_db)
    with file_db() as s:
        j1_id = enqueue_job(s, kind=JobKind.RUN_CHECKS, payload={"n": 1}, created_by=admin_id).id
        time.sleep(0.01)
        j2_id = enqueue_job(s, kind=JobKind.RUN_CHECKS, payload={"n": 2}, created_by=admin_id).id

    with file_db() as s:
        claimed = claim_next_job(s)
        assert claimed is not None
        assert claimed.id == j1_id
        assert claimed.status == JobStatus.RUNNING.value

    # Second claim picks j2.
    with file_db() as s:
        claimed = claim_next_job(s)
        assert claimed is not None
        assert claimed.id == j2_id

    # Third claim returns None (queue empty).
    with file_db() as s:
        assert claim_next_job(s) is None


def test_claim_is_race_safe(file_db) -> None:
    """Hai worker thread cùng claim 1 job → chỉ 1 thread thắng."""
    admin_id = _make_admin(file_db)
    with file_db() as s:
        enqueue_job(s, kind=JobKind.RUN_CHECKS, payload={}, created_by=admin_id)

    results = []
    barrier = threading.Barrier(2)

    def worker():
        barrier.wait()
        with file_db() as s:
            j = claim_next_job(s)
            results.append(j.id if j else None)

    t1 = threading.Thread(target=worker)
    t2 = threading.Thread(target=worker)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    non_none = [r for r in results if r is not None]
    assert len(non_none) == 1, f"Expected exactly 1 claim, got {results}"


def test_run_worker_iteration_executes_and_completes(file_db) -> None:
    admin_id = _make_admin(file_db)
    register_handler(JobKind.RUN_CHECKS, lambda payload, db: {"echoed": payload["x"]})
    with file_db() as s:
        job = enqueue_job(s, kind=JobKind.RUN_CHECKS, payload={"x": 99}, created_by=admin_id)
        job_id = job.id

    processed = run_worker_iteration(file_db)
    assert processed is True

    with file_db() as s:
        j = s.get(Job, job_id)
        assert j.status == JobStatus.DONE.value
        assert j.result == {"echoed": 99}

    # No more queued jobs.
    assert run_worker_iteration(file_db) is False


def test_recover_zombie_jobs_marks_stale_running_as_failed(file_db) -> None:
    admin_id = _make_admin(file_db)
    long_ago = datetime.utcnow() - timedelta(hours=2)
    recent = datetime.utcnow() - timedelta(minutes=10)

    with file_db() as s:
        # Zombie: started 2h ago, still RUNNING → must be recovered.
        zombie = Job(
            kind=JobKind.RUN_CHECKS.value, payload={}, created_by=admin_id,
            status=JobStatus.RUNNING.value, started_at=long_ago,
        )
        # Healthy: started 10m ago, still RUNNING → must be left alone.
        healthy = Job(
            kind=JobKind.RUN_CHECKS.value, payload={}, created_by=admin_id,
            status=JobStatus.RUNNING.value, started_at=recent,
        )
        s.add_all([zombie, healthy])
        s.commit()
        zid, hid = zombie.id, healthy.id

    with file_db() as s:
        recovered = recover_zombie_jobs(s, older_than_seconds=3600)
        assert recovered == 1

    with file_db() as s:
        z = s.get(Job, zid)
        h = s.get(Job, hid)
        assert z.status == JobStatus.FAILED.value
        assert "interrupted" in (z.error or "").lower()
        assert z.finished_at is not None
        assert h.status == JobStatus.RUNNING.value  # unchanged
