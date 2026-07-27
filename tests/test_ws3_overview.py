"""WS3 overview — aggregate, staleness, sinh (stub LLM), route.

- `build_overview_aggregate`: đếm severity + top-N subject/tiêu đề, KHÔNG nạp dòng.
- `overview_is_stale`: stale ⇔ ran_at dời HOẶC data_version dời (xử None hai đầu).
- `generate_check_overview`: ghi content + telemetry + snapshot; overwrite-upsert 1 dòng.
- Route `/overview`: guard AI + redirect + audit; company_detail render panel + badge stale.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.pool import StaticPool

from app.ai.overview_stats import build_stats
from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import CheckOverview, CheckRun, Company, CompanyPeriod, Finding


def _seed_finding(session, company_id, code, subject, sev="critical", title="t"):
    session.add(Finding(
        company_id=company_id, period_year=2024, check_code=code, severity=sev,
        subject_type="material_code", subject_key=subject, title=title,
    ))


# ─────────────────────────── aggregate ───────────────────────────

def test_build_aggregate_counts_and_top(session, company):
    _seed_finding(session, company.id, "C1.1", "MAT1", "critical", "Âm tồn")
    _seed_finding(session, company.id, "C1.1", "MAT1", "warning", "Lệch nhẹ")
    _seed_finding(session, company.id, "C1.1", "MAT2", "critical", "Âm tồn")
    _seed_finding(session, company.id, "C2.1", "MAT9", "info", "khác check")
    session.commit()

    from app.ai.overview import build_overview_aggregate

    agg = build_overview_aggregate(session, company.id, 2024, "C1.1")
    assert agg["total_findings"] == 3
    assert agg["severity_totals"] == {"critical": 2, "warning": 1, "info": 0}
    # MAT1 xuất hiện 2 lần → đứng đầu top_subjects.
    assert agg["top_subjects"][0] == {"subject_key": "MAT1", "count": 2}
    subjects = {s["subject_key"] for s in agg["top_subjects"]}
    assert subjects == {"MAT1", "MAT2"}  # KHÔNG lẫn MAT9 (check khác)
    assert agg["check_code"] == "C1.1"


# ─────────────────────────── staleness ───────────────────────────

def _ov(based_run_at, based_dv):
    return CheckOverview(
        company_id=1, period_year=2024, check_code="C1.1", content="x",
        based_on_run_at=based_run_at, based_on_data_version=based_dv,
    )


def test_stale_false_when_nothing_moved():
    from app.ai.overview import overview_is_stale

    t = datetime(2026, 1, 1, 10, 0)
    assert overview_is_stale(_ov(t, 3), current_ran_at=t, current_data_version=3) is False


def test_stale_true_when_ran_at_moved():
    from app.ai.overview import overview_is_stale

    t0 = datetime(2026, 1, 1, 10, 0)
    t1 = datetime(2026, 1, 1, 11, 0)
    assert overview_is_stale(_ov(t0, 3), current_ran_at=t1, current_data_version=3) is True


def test_stale_true_when_data_version_moved():
    from app.ai.overview import overview_is_stale

    t = datetime(2026, 1, 1, 10, 0)
    assert overview_is_stale(_ov(t, 3), current_ran_at=t, current_data_version=4) is True


def test_stale_handles_none_based_run_at():
    from app.ai.overview import overview_is_stale

    t = datetime(2026, 1, 1, 10, 0)
    # Overview sinh khi chưa có check_runs (based None); giờ có dòng chạy → stale.
    assert overview_is_stale(_ov(None, 0), current_ran_at=t, current_data_version=0) is True
    # Chưa từng chạy (cả hai None/0) → không stale.
    assert overview_is_stale(_ov(None, 0), current_ran_at=None, current_data_version=0) is False


# ─────────────────────────── generate (stub LLM) ───────────────────────────

class _FakeUsage:
    prompt_tokens = 12
    completion_tokens = 34


class _FakeMsg:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMsg(content)


class _FakeResp:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]
        self.usage = _FakeUsage()


@pytest.fixture
def _stub_llm(monkeypatch):
    import app.ai.overview as ov

    monkeypatch.setattr(ov, "make_client", lambda: None)
    monkeypatch.setattr(ov, "make_fallback_client", lambda: None)
    monkeypatch.setattr(ov, "fallback_model_for", lambda slot: None)
    monkeypatch.setattr(
        ov, "get_setting",
        lambda key, db=None: {
            "model_default": "test-model", "temperature": 0.2, "max_tokens": 500,
        }.get(key, ""),
    )

    calls = {"n": 0}

    def _fake_call(**kwargs):
        calls["n"] += 1
        resp = _FakeResp(f"Tổng quan test #{calls['n']}.")
        return (resp, "test-model") if kwargs.get("return_model") else resp

    monkeypatch.setattr(ov, "call_with_fallback", _fake_call)
    return calls


def test_generate_records_content_telemetry_snapshot(session, company, _stub_llm):
    _seed_finding(session, company.id, "C1.1", "MAT1")
    session.add(CheckRun(
        company_id=company.id, period_year=2024, check_code="C1.1",
        ran_at=datetime(2026, 1, 1, 9, 0), finding_count=1, status="ok", data_version=5,
    ))
    session.add(CompanyPeriod(company_id=company.id, period_year=2024, data_version=5))
    session.commit()

    from app.ai.overview import generate_check_overview

    ov = generate_check_overview(
        session, company=company, period_year=2024, check_code="C1.1"
    )
    assert ov.content == "Tổng quan test #1."
    assert ov.model == "test-model"
    assert ov.tokens_in == 12 and ov.tokens_out == 34
    assert ov.cost_usd is not None
    assert ov.latency_ms is not None
    # Snapshot nền lúc sinh.
    assert ov.based_on_run_at == datetime(2026, 1, 1, 9, 0)
    assert ov.based_on_data_version == 5


def test_generate_overwrites_single_row(session, company, _stub_llm):
    _seed_finding(session, company.id, "C1.1", "MAT1")
    session.commit()

    from app.ai.overview import generate_check_overview

    generate_check_overview(session, company=company, period_year=2024, check_code="C1.1")
    generate_check_overview(session, company=company, period_year=2024, check_code="C1.1")

    rows = session.scalars(
        select(CheckOverview).where(
            CheckOverview.company_id == company.id, CheckOverview.check_code == "C1.1"
        )
    ).all()
    assert len(rows) == 1  # overwrite-upsert, không version history
    assert rows[0].content == "Tổng quan test #2."  # bản mới ghi đè


def test_load_overviews_with_staleness(session, company, _stub_llm):
    _seed_finding(session, company.id, "C1.1", "MAT1")
    session.add(CheckRun(
        company_id=company.id, period_year=2024, check_code="C1.1",
        ran_at=datetime(2026, 1, 1, 9, 0), finding_count=1, status="ok", data_version=0,
    ))
    session.commit()

    from app.ai.overview import generate_check_overview, load_overviews_with_staleness

    generate_check_overview(session, company=company, period_year=2024, check_code="C1.1")

    loaded = load_overviews_with_staleness(session, company.id, 2024, ["C1.1"])
    assert "C1.1" in loaded
    assert loaded["C1.1"]["stale"] is False

    # Chạy lại (ran_at dời) → stale.
    run = session.scalar(
        select(CheckRun).where(CheckRun.company_id == company.id)
    )
    run.ran_at = datetime(2026, 2, 1, 9, 0)
    session.commit()

    loaded = load_overviews_with_staleness(session, company.id, 2024, ["C1.1"])
    assert loaded["C1.1"]["stale"] is True


# ─────────────────────────── route ───────────────────────────

def _setup_db():
    import app.database as dbmod
    from app.auth_users import seed_default_admin

    new_engine = dbmod.create_engine(
        "sqlite://", connect_args={"check_same_thread": False},
        poolclass=StaticPool, future=True,
    )
    new_session = dbmod.sessionmaker(
        bind=new_engine, autoflush=False, autocommit=False, future=True
    )
    dbmod.engine = new_engine
    dbmod.SessionLocal = new_session
    Base.metadata.create_all(new_engine)
    with new_session() as db:
        seed_default_admin(db, "admin", "admin")
        c = Company(code="DN_OV", name="Overview DN", tax_id="111")
        db.add(c)
        db.flush()
        db.add(Finding(
            company_id=c.id, period_year=2024, check_code="C1.1", severity="critical",
            subject_type="material_code", subject_key="MAT1", title="Âm tồn",
        ))
        db.commit()
    return new_engine, new_session


def _teardown(new_engine):
    import app.database as dbmod
    new_engine.dispose()
    dbmod.engine = engine
    dbmod.SessionLocal = SessionLocal


def _login(client):
    r = client.post("/login", data={"user": "admin", "password": "admin"},
                    follow_redirects=False)
    assert r.status_code == 303


def _enable_ai(monkeypatch):
    import app.ai.config as cfg
    import app.ai.limits as lim
    monkeypatch.setattr(
        cfg, "get_setting",
        lambda key, db=None: {"enabled": True, "api_key": "k"}.get(key, ""),
    )
    monkeypatch.setattr(lim, "check_rate_limit", lambda *a, **k: None)
    monkeypatch.setattr(lim, "check_daily_budget", lambda *a, **k: None)


def test_overview_route_enqueues_and_redirects_to_the_anchor(monkeypatch):
    """TQ-2: route XẾP HÀNG job rồi quay về đúng chỗ đang đọc, không sinh tại chỗ.

    (Trước TQ-2 route gọi `generate_check_overview` đồng bộ; test này từng stub
    hàm đó. Nay stub sẽ không bao giờ được gọi, nên phải khẳng định job.)
    """
    from app.models.job import Job, JobKind, JobStatus

    new_engine, new_session = _setup_db()
    try:
        _enable_ai(monkeypatch)
        client = TestClient(app)
        _login(client)
        r = client.post("/companies/DN_OV/overview",
                        data={"year": "2024", "check": "C1.1"}, follow_redirects=False)
        assert r.status_code == 303
        assert "msg=" in r.headers["location"]
        assert "#group-C1.1" in r.headers["location"]
        # KHÔNG chuyển sang /jobs/{id} — tổng quan nằm trong nhóm đang mở.
        assert "/jobs/" not in r.headers["location"]
        with new_session() as db:
            c = db.scalar(select(Company).where(Company.code == "DN_OV"))
            job = db.scalar(select(Job))
            assert job.kind == JobKind.AI_OVERVIEW.value
            assert job.status == JobStatus.QUEUED.value
            assert job.payload["check_code"] == "C1.1"
            ov_row = db.scalar(
                select(CheckOverview).where(CheckOverview.company_id == c.id)
            )
            # Dòng tồn tại NGAY, mang trạng thái đang chạy + job.
            assert ov_row.status == CheckOverview.STATUS_RUNNING
            assert ov_row.job_id == job.id

        # Bấm lại khi job còn chờ → vẫn ĐÚNG một job.
        r2 = client.post("/companies/DN_OV/overview",
                         data={"year": "2024", "check": "C1.1"}, follow_redirects=False)
        assert r2.status_code == 303
        with new_session() as db:
            assert len(db.scalars(select(Job)).all()) == 1
    finally:
        _teardown(new_engine)


def test_overview_route_ai_disabled_shows_error(monkeypatch):
    new_engine, new_session = _setup_db()
    try:
        import app.ai.config as cfg
        monkeypatch.setattr(cfg, "get_setting", lambda key, db=None: False)

        client = TestClient(app)
        _login(client)
        r = client.post("/companies/DN_OV/overview",
                        data={"year": "2024", "check": "C1.1"}, follow_redirects=False)
        assert r.status_code == 303
        assert "error=" in r.headers["location"]
        with new_session() as db:
            c = db.scalar(select(Company).where(Company.code == "DN_OV"))
            assert db.scalar(
                select(CheckOverview).where(CheckOverview.company_id == c.id)
            ) is None
    finally:
        _teardown(new_engine)


def test_company_detail_renders_overview_and_stale_badge(monkeypatch):
    new_engine, new_session = _setup_db()
    try:
        with new_session() as db:
            c = db.scalar(select(Company).where(Company.code == "DN_OV"))
            # check_run mới hơn overview → stale.
            db.add(CheckRun(
                company_id=c.id, period_year=2024, check_code="C1.1",
                ran_at=datetime(2026, 2, 1, 9, 0), finding_count=1, status="ok",
                data_version=0,
            ))
            db.add(CheckOverview(
                company_id=c.id, period_year=2024, check_code="C1.1",
                content="Nội dung tổng quan mẫu.",
                based_on_run_at=datetime(2026, 1, 1, 9, 0), based_on_data_version=0,
            ))
            db.commit()

        client = TestClient(app)
        _login(client)
        html = client.get("/companies/DN_OV?year=2024").text
        assert "Nội dung tổng quan mẫu." in html
        assert "Tổng quan đã cũ" in html  # badge stale
        # Mốc based_on (lần chạy overview dựa vào) phải hiện khi stale — ADR §(4).
        assert "dựa trên lần chạy 01/01/2026 09:00" in html
    finally:
        _teardown(new_engine)


def test_percentile_field_shows_vietnamese_label_not_raw_key(monkeypatch):
    """Ô phân vị phải hiện nhãn tiếng Việt, không in khoá `details` thô ra màn hình."""
    new_engine, new_session = _setup_db()
    try:
        with new_session() as db:
            c = db.scalar(select(Company).where(Company.code == "DN_OV"))
            for i, qty in enumerate((10, 20, 30)):
                db.add(Finding(
                    company_id=c.id, period_year=2024, check_code="C1.6",
                    severity="critical", subject_type="material_code",
                    subject_key=f"MAT{i}", title="Chuyển MĐSD",
                    details={"m15_repurpose": qty},
                ))
            db.flush()
            db.add(CheckOverview(
                company_id=c.id, period_year=2024, check_code="C1.6",
                content="Nội dung tổng quan mẫu.",
                based_on_run_at=None, based_on_data_version=0,
                aggregate_json=build_stats(
                    db, company_id=c.id, period_year=2024, check_code="C1.6"
                ),
            ))
            db.commit()

        client = TestClient(app)
        _login(client)
        html = client.get("/companies/DN_OV?year=2024").text
        assert "Lượng chuyển mục đích sử dụng" in html
        assert "m15_repurpose" not in html
    finally:
        _teardown(new_engine)
