"""Test enqueue_job, handler registry, run_job dispatch."""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from app.jobs import HANDLERS, enqueue_job, register_handler, run_job
from app.models import User
from app.models.job import JobKind, JobStatus


@pytest.fixture(autouse=True)
def _clear_handlers():
    """Cô lập handler registry giữa các test."""
    saved = HANDLERS.copy()
    HANDLERS.clear()
    yield
    HANDLERS.clear()
    HANDLERS.update(saved)


def test_enqueue_creates_queued_row(session: Session, admin_user: User) -> None:
    job = enqueue_job(
        session,
        kind=JobKind.RUN_CHECKS,
        payload={"company_code": "HONG_AN", "year": 2024},
        created_by=admin_user.id,
        company_id=None,
        period_year=2024,
    )
    assert job.id is not None
    assert job.status == JobStatus.QUEUED
    assert job.payload["company_code"] == "HONG_AN"
    assert job.started_at is None


def test_register_handler_dedups(session: Session) -> None:
    register_handler(JobKind.RUN_CHECKS, lambda payload, db: {"ok": True})
    with pytest.raises(ValueError, match="đã đăng ký"):
        register_handler(JobKind.RUN_CHECKS, lambda payload, db: {"ok": True})


def test_run_job_success_marks_done(session: Session, admin_user: User) -> None:
    register_handler(JobKind.RUN_CHECKS, lambda payload, db: {"findings": 7, "echo": payload["x"]})
    job = enqueue_job(
        session, kind=JobKind.RUN_CHECKS, payload={"x": 42},
        created_by=admin_user.id, company_id=None, period_year=None,
    )
    run_job(session, job)

    session.refresh(job)
    assert job.status == JobStatus.DONE
    assert job.result == {"findings": 7, "echo": 42}
    assert job.error is None
    assert isinstance(job.started_at, datetime)
    assert isinstance(job.finished_at, datetime)
    assert job.finished_at >= job.started_at


def test_run_job_failure_captures_error(session: Session, admin_user: User) -> None:
    def boom(payload, db):
        raise RuntimeError("simulated failure: bad input")

    register_handler(JobKind.RUN_CHECKS, boom)
    job = enqueue_job(
        session, kind=JobKind.RUN_CHECKS, payload={},
        created_by=admin_user.id, company_id=None, period_year=None,
    )
    run_job(session, job)

    session.refresh(job)
    assert job.status == JobStatus.FAILED
    assert job.result is None
    assert job.error is not None
    assert "simulated failure" in job.error
    assert "RuntimeError" in job.error
    assert isinstance(job.finished_at, datetime)


def test_run_job_unknown_kind_fails(session: Session, admin_user: User) -> None:
    # Không register handler nào.
    job = enqueue_job(
        session, kind=JobKind.RUN_CHECKS, payload={},
        created_by=admin_user.id, company_id=None, period_year=None,
    )
    run_job(session, job)

    session.refresh(job)
    assert job.status == JobStatus.FAILED
    assert "Không có handler" in (job.error or "")
