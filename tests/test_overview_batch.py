"""TQ-5 (ADR #21 mục 9) — nút gộp cả năm + dừng khi hết ngân sách.

Hai tính chất chịu lực: commit TỪNG kiểm tra (job dừng giữa chừng vẫn giữ phần
đã sinh), và hết ngân sách thì job kết thúc HOÀN TẤT chứ không `failed` — những
tổng quan đã sinh vẫn đúng, còn `failed` mời cán bộ bấm lại một nút chắc chắn
không làm gì.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import AiUsage, CheckOverview, CheckRun, Company, Finding, User


@pytest.fixture
def factory():
    engine = create_engine(
        "sqlite://", future=True, poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    engine.dispose()


@pytest.fixture
def world(factory):
    from app.ai.config import bust_cache, set_setting

    with factory() as db:
        c = Company(code="DN_B", slug="dn-b", name="Batch Co", tax_id="1")
        u = User(username="off", password_hash="x", role="officer")
        db.add_all([c, u])
        db.flush()
        for code in ("C1.1", "C1.4", "C2.1"):
            db.add(Finding(
                company_id=c.id, period_year=2025, check_code=code, severity="critical",
                subject_key="M1", title=f"{code}", details={},
            ))
        # Meta-finding tổ hợp KHÔNG phải một bài kiểm tra.
        db.add(Finding(
            company_id=c.id, period_year=2025, check_code="COMBO_HS_GAMING",
            severity="critical", subject_key="X", title="combo", details={},
        ))
        bust_cache()
        set_setting("daily_budget_usd", 10.0, "test", db=db)
        db.commit()
        ids = {"company_id": c.id, "user_id": u.id}
    yield ids
    bust_cache()


def _fake_generate(cost=0.0):
    """Thay lời gọi LLM: ghi nội dung + ghi sổ chi phí như đường thật."""
    from app.ai.usage import record_usage

    def _gen(db, *, company, period_year, check_code, created_by=None):
        row = db.scalar(
            select(CheckOverview).where(
                CheckOverview.company_id == company.id,
                CheckOverview.period_year == period_year,
                CheckOverview.check_code == check_code,
            )
        )
        if row is None:
            row = CheckOverview(
                company_id=company.id, period_year=period_year, check_code=check_code,
                based_on_data_version=0,
            )
            db.add(row)
        row.content = f"nhận định {check_code}"
        row.status = CheckOverview.STATUS_DONE
        if cost:
            record_usage(db, kind=AiUsage.KIND_OVERVIEW, ref=check_code, model="m",
                         tokens_in=1, tokens_out=1, cost_usd=cost, user=created_by)
        db.commit()
        return row

    return _gen


# ───────────────────────── chọn mục tiêu ─────────────────────────

def test_targets_are_checks_with_findings_excluding_combos(factory, world):
    from app.ai.overview import checks_needing_overview

    with factory() as db:
        assert checks_needing_overview(db, world["company_id"], 2025) == ["C1.1", "C1.4", "C2.1"]


def test_fresh_overview_is_skipped(factory, world):
    from app.ai.overview import checks_needing_overview

    with factory() as db:
        db.add(CheckOverview(
            company_id=world["company_id"], period_year=2025, check_code="C1.1",
            content="đã có", based_on_data_version=0, status=CheckOverview.STATUS_DONE,
        ))
        db.commit()
        assert checks_needing_overview(db, world["company_id"], 2025) == ["C1.4", "C2.1"]


def test_stale_overview_is_regenerated(factory, world):
    """Chạy lại kiểm tra sau khi sinh → tổng quan cũ, phải nằm trong danh sách."""
    from datetime import datetime, timedelta

    from app.ai.overview import checks_needing_overview

    with factory() as db:
        generated = datetime.utcnow() - timedelta(hours=2)
        db.add(CheckOverview(
            company_id=world["company_id"], period_year=2025, check_code="C1.1",
            content="cũ", based_on_data_version=0, status=CheckOverview.STATUS_DONE,
            generated_at=generated, based_on_run_at=generated,
        ))
        db.add(CheckRun(
            company_id=world["company_id"], period_year=2025, check_code="C1.1",
            ran_at=datetime.utcnow(), finding_count=1, data_version=0,
        ))
        db.commit()
        assert "C1.1" in checks_needing_overview(db, world["company_id"], 2025)


# ───────────────────────── chạy lượt gộp ─────────────────────────

def test_batch_generates_every_missing_check(factory, world, monkeypatch):
    import app.ai.overview as ov

    monkeypatch.setattr(ov, "generate_check_overview", _fake_generate())
    with factory() as db:
        result = ov.run_overview_batch_job(
            {"company_code": "DN_B", "year": 2025, "username": "off"}, db
        )
        assert result["da_tao"] == 3
        assert result["dung_vi"] is None
        assert len(db.scalars(select(CheckOverview)).all()) == 3


def test_batch_stops_on_exhausted_budget_without_failing(factory, world, monkeypatch):
    """Hết ngân sách giữa chừng → dừng, KHÔNG ném lỗi; phần đã sinh giữ nguyên."""
    import app.ai.overview as ov

    # Trần $10, mỗi lần gọi tốn $6 → lần 1 qua, lần 2 qua (spent 6 < 10),
    # tới lần 3 spent = 12 ≥ 10 → dừng.
    monkeypatch.setattr(ov, "generate_check_overview", _fake_generate(cost=6.0))
    with factory() as db:
        result = ov.run_overview_batch_job(
            {"company_code": "DN_B", "year": 2025, "username": "off"}, db
        )
    assert result["dung_vi"] == "hết ngân sách ngày"
    assert result["da_tao"] == 2
    assert result["bo_qua"] == 1
    with factory() as db:
        # Phần đã sinh CÒN NGUYÊN — commit từng kiểm tra.
        assert len(db.scalars(select(CheckOverview)).all()) == 2


def test_batch_result_reports_counts_and_reason(factory, world, monkeypatch):
    import app.ai.overview as ov

    monkeypatch.setattr(ov, "generate_check_overview", _fake_generate())
    with factory() as db:
        result = ov.run_overview_batch_job(
            {"company_code": "DN_B", "year": 2025, "username": "off"}, db
        )
    assert set(result) >= {"da_tao", "bo_qua", "loi", "dung_vi"}
    # Kết quả in nguyên ra /jobs/{id} cho mọi cán bộ → không được có tiền.
    flat = str(result).lower()
    assert "cost" not in flat and "token" not in flat


def test_one_failing_check_does_not_kill_the_batch(factory, world, monkeypatch):
    import app.ai.overview as ov

    ok = _fake_generate()

    def _sometimes(db, *, company, period_year, check_code, created_by=None):
        if check_code == "C1.4":
            raise RuntimeError("provider 500")
        return ok(db, company=company, period_year=period_year,
                  check_code=check_code, created_by=created_by)

    monkeypatch.setattr(ov, "generate_check_overview", _sometimes)
    with factory() as db:
        result = ov.run_overview_batch_job(
            {"company_code": "DN_B", "year": 2025, "username": "off"}, db
        )
    assert result["da_tao"] == 2
    assert result["loi"] == 1
    assert result["checks_loi"] == ["C1.4"]


def test_batch_on_company_with_no_findings_is_a_no_op(factory, world, monkeypatch):
    import app.ai.overview as ov

    monkeypatch.setattr(ov, "generate_check_overview", _fake_generate())
    with factory() as db:
        result = ov.run_overview_batch_job(
            {"company_code": "DN_B", "year": 2099, "username": "off"}, db
        )
    assert result["da_tao"] == 0
    assert result["bo_qua"] == 0


def test_batch_job_kind_goes_to_the_ai_worker(factory, world):
    """Lượt gộp chạy trên worker AI → hàng đợi kiểm tra không bị chặn."""
    from app.jobs import enqueue_job
    from app.jobs.worker import claim_next_job
    from app.models.job import AI_JOB_KINDS, JobKind

    with factory() as db:
        batch = enqueue_job(
            db, kind=JobKind.AI_OVERVIEW_BATCH,
            payload={"company_code": "DN_B", "year": 2025},
            created_by=world["user_id"], company_id=world["company_id"], period_year=2025,
        )
        run = enqueue_job(
            db, kind=JobKind.RUN_CHECKS, payload={"company_code": "DN_B", "year": 2025},
            created_by=world["user_id"], company_id=world["company_id"], period_year=2025,
        )
        assert claim_next_job(db, kinds=AI_JOB_KINDS).id == batch.id
        assert claim_next_job(db, exclude_kinds=AI_JOB_KINDS).id == run.id
