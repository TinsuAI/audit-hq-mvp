"""`/diagnose-ai` chạy ở hàng đợi, không trong request.

Lời gọi LLM chẩn đoán cấu trúc file mất ~120 s với bộ file 006, còn Cloudflare cắt
kết nối ở 100 giây → cán bộ luôn thấy 524 đúng lúc cần chẩn đoán nhất. Cùng lớp lỗi
mà #74 đã sửa cho việc nạp, cùng cách sửa: route xếp job rồi chuyển sang `/jobs/{id}`.

Job chẩn đoán thuộc nhóm `AI_JOB_KINDS` — worker kiểm tra loại trừ nhóm này, nên hàng
đợi chạy kiểm tra không bao giờ phải chờ một lời gọi LLM.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool

import app.database as dbmod
from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import Company
from app.models.job import AI_JOB_KINDS, Job, JobKind
from app.settings import settings


@pytest.fixture
def env(tmp_path, monkeypatch):
    new_engine = dbmod.create_engine(
        "sqlite://", connect_args={"check_same_thread": False},
        poolclass=StaticPool, future=True,
    )
    new_session = dbmod.sessionmaker(bind=new_engine, autoflush=False, autocommit=False, future=True)
    dbmod.engine = new_engine
    dbmod.SessionLocal = new_session
    Base.metadata.create_all(new_engine)
    with new_session() as db:
        from app.auth_users import seed_default_admin
        seed_default_admin(db, "admin", "admin")
        db.add(Company(code="DN_DIAG", name="Diag", tax_id="1"))
        db.commit()
    prev_root = settings.raw_data_path
    settings.raw_data_path = str(tmp_path)

    # Guard AI bật sẵn: test này nói về hàng đợi, không về cấu hình.
    import app.ai.config as aicfg
    monkeypatch.setattr(aicfg, "get_setting", lambda k: True if k in ("enabled", "api_key") else "x")

    client = TestClient(app)
    client.post("/login", data={"user": "admin", "password": "admin"}, follow_redirects=False)
    try:
        yield client
    finally:
        settings.raw_data_path = prev_root
        new_engine.dispose()
        dbmod.engine = engine
        dbmod.SessionLocal = SessionLocal


def test_diagnose_ai_enqueues_a_job_and_redirects(env):
    r = env.post(
        "/companies/DN_DIAG/diagnose-ai",
        data={"year": "2024"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    with dbmod.SessionLocal() as db:
        job = db.query(Job).order_by(Job.id.desc()).first()
        assert job is not None
        assert job.kind == JobKind.AI_DIAGNOSE.value
        assert job.payload["company_code"] == "DN_DIAG"
        assert job.payload["year"] == 2024
    assert r.headers["location"] == f"/jobs/{job.id}"


def test_diagnose_ai_does_not_call_the_llm_inside_the_request(env, monkeypatch):
    """Điểm cốt lõi: request phải trả ngay, LLM để worker gọi."""
    called = []
    import app.ai.ingest_doctor as doctor
    monkeypatch.setattr(
        doctor, "diagnose_with_ai",
        lambda *a, **k: called.append(1) or "không bao giờ tới đây",
    )
    env.post("/companies/DN_DIAG/diagnose-ai", data={"year": "2024"}, follow_redirects=False)
    assert called == []


def test_diagnose_job_is_in_the_ai_queue_group(env):
    """Cùng nhóm với tổng quan AI → không chặn hàng đợi chạy kiểm tra."""
    assert JobKind.AI_DIAGNOSE.value in AI_JOB_KINDS


def test_running_the_job_stores_the_ai_text_in_the_result(env, monkeypatch):
    import app.ai.ingest_doctor as doctor
    monkeypatch.setattr(doctor, "diagnose_with_ai", lambda *a, **k: "Cột 24 là Đơn giá, không phải Số lượng.")

    env.post("/companies/DN_DIAG/diagnose-ai", data={"year": "2024"}, follow_redirects=False)
    from tests.helpers import drain_jobs
    drain_jobs()

    with dbmod.SessionLocal() as db:
        job = db.query(Job).order_by(Job.id.desc()).first()
        assert job.status == "done"
        assert job.result["ai_result"] == "Cột 24 là Đơn giá, không phải Số lượng."
        assert job.result["company_code"] == "DN_DIAG"


def test_job_page_shows_the_ai_diagnosis_as_its_own_block(env, monkeypatch):
    """Chẩn đoán dài nhiều đoạn — ép vào một ô bảng là không đọc được."""
    import app.ai.ingest_doctor as doctor
    text = "Trang tính đầu không phải BCCT.\n\nCột 24 là Đơn giá, không phải Số lượng."
    monkeypatch.setattr(doctor, "diagnose_with_ai", lambda *a, **k: text)

    r = env.post("/companies/DN_DIAG/diagnose-ai", data={"year": "2024"}, follow_redirects=False)
    from tests.helpers import drain_jobs
    drain_jobs()

    html = env.get(r.headers["location"]).text
    assert "Trang tính đầu không phải BCCT." in html
    assert "Cột 24 là Đơn giá" in html
    # Khối riêng, KHÔNG phải một dòng bảng mang nhãn thô `ai_result`.
    assert "ai-diagnosis" in html
    assert "<th scope=\"row\">ai_result</th>" not in html


def test_llm_failure_lands_on_the_job_not_a_500(env, monkeypatch):
    """AI hỏng thì job ghi lỗi; cán bộ đọc được lý do, trang không sập."""
    import app.ai.ingest_doctor as doctor

    def boom(*a, **k):
        raise RuntimeError("API 401")

    monkeypatch.setattr(doctor, "diagnose_with_ai", boom)
    env.post("/companies/DN_DIAG/diagnose-ai", data={"year": "2024"}, follow_redirects=False)
    from tests.helpers import drain_jobs
    drain_jobs()

    with dbmod.SessionLocal() as db:
        job = db.query(Job).order_by(Job.id.desc()).first()
        assert job.status == "done"
        assert "API 401" in job.result["ai_result"]


def test_ai_disabled_is_refused_before_a_job_is_created(env, monkeypatch):
    import app.ai.config as aicfg
    monkeypatch.setattr(aicfg, "get_setting", lambda k: False)
    r = env.post("/companies/DN_DIAG/diagnose-ai", data={"year": "2024"}, follow_redirects=False)
    assert r.status_code == 503
    with dbmod.SessionLocal() as db:
        assert db.query(Job).filter_by(kind=JobKind.AI_DIAGNOSE.value).count() == 0
