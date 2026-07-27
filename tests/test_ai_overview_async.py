"""TQ-2 (ADR #21 mục 5-7) — sinh tổng quan chạy nền, worker chia theo loại job.

Điểm chịu lực: hàng đợi KIỂM TRA không bao giờ phải chờ một lời gọi LLM. ADR #18
bảo vệ tính chất đó bằng cách chạy đồng bộ trong request; vé này giữ tính chất
nhưng lấy lại job row, bằng cách cho worker kiểm tra LOẠI TRỪ job AI và thêm một
worker CHỈ nhận job AI.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.jobs import enqueue_job
from app.jobs.worker import claim_next_job, run_worker_iteration
from app.models import CheckOverview, Company, User
from app.models.job import AI_JOB_KINDS, Job, JobKind, JobStatus


@pytest.fixture
def factory():
    engine = create_engine(
        "sqlite:///:memory:", future=True,
        connect_args={"check_same_thread": False},
    )
    from sqlalchemy.pool import StaticPool

    engine.dispose()
    engine = create_engine(
        "sqlite://", future=True, poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    engine.dispose()


@pytest.fixture
def world(factory):
    with factory() as db:
        c = Company(code="DN_OV", slug="dn-ov", name="Overview Co", tax_id="1")
        u = User(username="off", password_hash="x", role="officer")
        db.add_all([c, u])
        db.commit()
        return {"company_id": c.id, "company_code": c.code, "user_id": u.id}


def _enqueue(db, kind, world, **payload):
    return enqueue_job(
        db, kind=kind, payload=payload, created_by=world["user_id"],
        company_id=world["company_id"], period_year=2025,
    )


# ───────────────────────── claim theo loại ─────────────────────────

def test_check_worker_does_not_claim_ai_jobs(factory, world):
    with factory() as db:
        _enqueue(db, JobKind.AI_OVERVIEW, world, check_code="C1.1")
        claimed = claim_next_job(db, exclude_kinds=AI_JOB_KINDS)
        assert claimed is None


def test_ai_worker_does_not_claim_check_jobs(factory, world):
    with factory() as db:
        _enqueue(db, JobKind.RUN_CHECKS, world, company_code="DN_OV", year=2025)
        assert claim_next_job(db, kinds=AI_JOB_KINDS) is None


def test_long_ai_job_does_not_hold_up_a_waiting_check_job(factory, world):
    """Job AI xếp hàng TRƯỚC vẫn không chặn job kiểm tra đang chờ."""
    with factory() as db:
        ai = _enqueue(db, JobKind.AI_OVERVIEW, world, check_code="C1.1")
        run = _enqueue(db, JobKind.RUN_CHECKS, world, company_code="DN_OV", year=2025)
        # Worker AI cầm job AI (nó sẽ chạy lâu).
        assert claim_next_job(db, kinds=AI_JOB_KINDS).id == ai.id
        # Worker kiểm tra vẫn lấy được job kiểm tra ngay.
        assert claim_next_job(db, exclude_kinds=AI_JOB_KINDS).id == run.id


def test_each_worker_claims_its_own_kind(factory, world):
    with factory() as db:
        run = _enqueue(db, JobKind.RUN_CHECKS, world, company_code="DN_OV", year=2025)
        ai = _enqueue(db, JobKind.AI_OVERVIEW, world, check_code="C1.1")
        assert claim_next_job(db, exclude_kinds=AI_JOB_KINDS).id == run.id
        assert claim_next_job(db, kinds=AI_JOB_KINDS).id == ai.id


# ───────────────────────── xếp hàng + không nhân đôi ─────────────────────────

def test_start_overview_job_creates_running_row(factory, world):
    from app.ai.overview import start_overview_job

    with factory() as db:
        company = db.get(Company, world["company_id"])
        job_id, existing = start_overview_job(
            db, company=company, period_year=2025, check_code="C1.1",
            created_by=world["user_id"], username="off",
        )
        assert existing is False
        ov = db.scalar(select(CheckOverview))
        assert ov.status == CheckOverview.STATUS_RUNNING
        assert ov.job_id == job_id
        assert ov.content == ""


def test_second_click_returns_the_same_job(factory, world):
    """Bấm hai lần liên tiếp → ĐÚNG một job, không hai lời gọi tính tiền."""
    from app.ai.overview import start_overview_job

    with factory() as db:
        company = db.get(Company, world["company_id"])
        first, _ = start_overview_job(
            db, company=company, period_year=2025, check_code="C1.1",
            created_by=world["user_id"],
        )
        second, existing = start_overview_job(
            db, company=company, period_year=2025, check_code="C1.1",
            created_by=world["user_id"],
        )
        assert (second, existing) == (first, True)
        assert len(db.scalars(select(Job)).all()) == 1


def test_click_after_job_finished_makes_a_new_job(factory, world):
    from app.ai.overview import start_overview_job

    with factory() as db:
        company = db.get(Company, world["company_id"])
        first, _ = start_overview_job(
            db, company=company, period_year=2025, check_code="C1.1",
            created_by=world["user_id"],
        )
        job = db.get(Job, first)
        job.status = JobStatus.DONE.value
        db.commit()
        second, existing = start_overview_job(
            db, company=company, period_year=2025, check_code="C1.1",
            created_by=world["user_id"],
        )
        assert existing is False
        assert second != first


# ───────────────────────── handler ─────────────────────────

def test_handler_result_carries_no_money(factory, world, monkeypatch):
    """`/jobs/{id}` in nguyên `result` cho MỌI cán bộ → result không được có tiền."""
    import app.ai.overview as ov_mod

    def _fake_generate(db, *, company, period_year, check_code, created_by=None):
        row = db.scalar(select(CheckOverview))
        row.content = "nhận định giả"
        row.status = CheckOverview.STATUS_DONE
        row.cost_usd = 0.42
        row.tokens_in = 100
        db.commit()
        return row

    monkeypatch.setattr(ov_mod, "generate_check_overview", _fake_generate)
    with factory() as db:
        company = db.get(Company, world["company_id"])
        ov_mod.start_overview_job(
            db, company=company, period_year=2025, check_code="C1.1",
            created_by=world["user_id"],
        )
        result = ov_mod.run_overview_job(
            {"company_code": "DN_OV", "year": 2025, "check_code": "C1.1"}, db
        )
    flat = str(result).lower()
    assert "cost" not in flat and "token" not in flat and "0.42" not in flat
    assert result["check_code"] == "C1.1"


def test_handler_marks_row_failed_and_reraises(factory, world, monkeypatch):
    import app.ai.overview as ov_mod

    def _boom(db, *, company, period_year, check_code, created_by=None):
        raise RuntimeError("provider 500")

    monkeypatch.setattr(ov_mod, "generate_check_overview", _boom)
    with factory() as db:
        company = db.get(Company, world["company_id"])
        ov_mod.start_overview_job(
            db, company=company, period_year=2025, check_code="C1.1",
            created_by=world["user_id"],
        )
        with pytest.raises(RuntimeError):
            ov_mod.run_overview_job(
                {"company_code": "DN_OV", "year": 2025, "check_code": "C1.1"}, db
            )
        ov = db.scalar(select(CheckOverview))
        assert ov.status == CheckOverview.STATUS_FAILED
        assert "provider 500" in ov.error


def test_worker_iteration_runs_ai_job_through_registered_handler(factory, world, monkeypatch):
    import app.ai.overview as ov_mod
    from app.jobs import HANDLERS

    def _fake_generate(db, *, company, period_year, check_code, created_by=None):
        row = db.scalar(select(CheckOverview))
        row.content = "xong"
        row.status = CheckOverview.STATUS_DONE
        db.commit()
        return row

    monkeypatch.setattr(ov_mod, "generate_check_overview", _fake_generate)
    monkeypatch.setitem(HANDLERS, JobKind.AI_OVERVIEW.value, ov_mod.run_overview_job)

    with factory() as db:
        company = db.get(Company, world["company_id"])
        job_id, _ = ov_mod.start_overview_job(
            db, company=company, period_year=2025, check_code="C1.1",
            created_by=world["user_id"],
        )
    assert run_worker_iteration(factory, kinds=AI_JOB_KINDS) is True
    with factory() as db:
        assert db.get(Job, job_id).status == JobStatus.DONE.value
        assert db.scalar(select(CheckOverview)).content == "xong"
