"""Test schema và defaults của bảng `jobs`."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.models import User
from app.models.job import Job, JobKind, JobStatus


def test_job_table_schema(session: Session) -> None:
    inspector = inspect(session.bind)
    assert "jobs" in inspector.get_table_names()
    cols = {c["name"]: c for c in inspector.get_columns("jobs")}
    assert set(cols) >= {
        "id", "kind", "payload", "status", "result", "error",
        "created_by", "company_id", "period_year",
        "started_at", "finished_at", "created_at", "viewed_at",
    }


def test_job_indexes_present(session: Session) -> None:
    inspector = inspect(session.bind)
    idx_cols = {tuple(ix["column_names"]) for ix in inspector.get_indexes("jobs")}
    assert ("status", "created_at") in idx_cols
    assert ("created_by", "status") in idx_cols


def test_job_defaults(session: Session, admin_user: User) -> None:
    j = Job(
        kind=JobKind.RUN_CHECKS,
        payload={"company_code": "HONG_AN", "year": 2024},
        created_by=admin_user.id,
        company_id=None,
        period_year=2024,
    )
    session.add(j)
    session.commit()

    fetched = session.scalar(select(Job).where(Job.id == j.id))
    assert fetched is not None
    assert fetched.status == JobStatus.QUEUED
    assert fetched.result is None
    assert fetched.error is None
    assert fetched.started_at is None
    assert fetched.finished_at is None
    assert fetched.viewed_at is None
    assert isinstance(fetched.created_at, datetime)
    assert fetched.payload == {"company_code": "HONG_AN", "year": 2024}


def test_job_kind_values() -> None:
    assert JobKind.RUN_CHECKS.value == "run_checks"
    assert JobKind.INGEST_AND_RUN.value == "ingest_and_run"
    assert JobKind.BATCH_RUN.value == "batch_run"


def test_job_status_values() -> None:
    assert {s.value for s in JobStatus} == {"queued", "running", "done", "failed"}
