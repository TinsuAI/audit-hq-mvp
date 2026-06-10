"""POST /api/chat/run-checks — cán bộ xác nhận chạy kiểm tra từ đề xuất AI.

Đây là điểm con-người-bấm-nút: chỉ endpoint này (do cán bộ kích hoạt) mới enqueue
job; AI chỉ đề xuất. TestClient không vào context manager → worker thread không
chạy → job giữ nguyên trạng thái queued để assert.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import Company, Job
from app.models.job import JobKind


def _setup_db():
    import app.database as dbmod
    from app.auth_users import seed_default_admin

    new_engine = dbmod.create_engine(
        "sqlite://", connect_args={"check_same_thread": False},
        poolclass=StaticPool, future=True,
    )
    new_session = dbmod.sessionmaker(bind=new_engine, autoflush=False, autocommit=False, future=True)
    dbmod.engine = new_engine
    dbmod.SessionLocal = new_session
    Base.metadata.create_all(new_engine)
    with new_session() as db:
        seed_default_admin(db, "admin", "admin")
        db.add(Company(code="DN_077", name="Test (Demo)", tax_id="111"))
        db.commit()
    return new_engine, new_session


def _teardown(new_engine):
    new_engine.dispose()
    import app.database as dbmod
    dbmod.engine = engine
    dbmod.SessionLocal = SessionLocal


def _login(client: TestClient) -> None:
    r = client.post("/login", data={"user": "admin", "password": "admin"}, follow_redirects=False)
    assert r.status_code == 303


def test_run_checks_enqueues_batch_when_no_year():
    new_engine, new_session = _setup_db()
    try:
        client = TestClient(app)
        _login(client)
        r = client.post("/api/chat/run-checks", json={"company_code": "DN_077"})
        assert r.status_code == 200
        body = r.json()
        assert body["status_url"] == f"/jobs/{body['job_id']}"
        with new_session() as db:
            job = db.get(Job, body["job_id"])
            assert job.kind == JobKind.BATCH_RUN.value
            assert job.payload == {"company_code": "DN_077"}
            assert job.period_year is None
    finally:
        _teardown(new_engine)


def test_run_checks_enqueues_single_year():
    new_engine, new_session = _setup_db()
    try:
        client = TestClient(app)
        _login(client)
        r = client.post("/api/chat/run-checks", json={"company_code": "DN_077", "year": 2024})
        assert r.status_code == 200
        with new_session() as db:
            job = db.get(Job, r.json()["job_id"])
            assert job.kind == JobKind.RUN_CHECKS.value
            assert job.payload == {"company_code": "DN_077", "year": 2024}
            assert job.period_year == 2024
    finally:
        _teardown(new_engine)


def test_run_checks_requires_auth():
    new_engine, _ = _setup_db()
    try:
        client = TestClient(app)  # không login
        r = client.post(
            "/api/chat/run-checks", json={"company_code": "DN_077"}, follow_redirects=False,
        )
        # require_user → 303 redirect về /login khi chưa đăng nhập.
        assert r.status_code == 303
        assert r.headers["location"] == "/login"
    finally:
        _teardown(new_engine)


def test_run_checks_unknown_company():
    new_engine, _ = _setup_db()
    try:
        client = TestClient(app)
        _login(client)
        r = client.post("/api/chat/run-checks", json={"company_code": "NOPE"})
        assert r.status_code == 404
    finally:
        _teardown(new_engine)
