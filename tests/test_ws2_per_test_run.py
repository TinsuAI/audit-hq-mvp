"""WS2-2 per-test run — POST /companies/{code}/run-checks với `check` lặp lại.

Nút "Chạy lại {mã}" ở mỗi nhóm check → enqueue RUN_CHECKS {only:[mã], year} →
redirect /jobs/{id}. TestClient không vào context manager → worker không chạy →
job giữ `queued` để assert payload (ADR #18 Revision — WS2).
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
        db.add(Company(code="DN_WS2", name="Test", tax_id="111"))
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


def test_per_test_run_enqueues_only():
    new_engine, new_session = _setup_db()
    try:
        client = TestClient(app)
        _login(client)
        r = client.post(
            "/companies/DN_WS2/run-checks",
            data={"year": "2024", "check": ["C1.1", "C4.3"]},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert r.headers["location"].startswith("/jobs/")
        with new_session() as db:
            job = db.query(Job).order_by(Job.id.desc()).first()
            assert job.kind == JobKind.RUN_CHECKS.value
            assert job.payload["company_code"] == "DN_WS2"
            assert job.payload["year"] == 2024
            assert set(job.payload["only"]) == {"C1.1", "C4.3"}
            assert job.period_year == 2024
    finally:
        _teardown(new_engine)


def test_year_without_check_runs_full_year():
    new_engine, new_session = _setup_db()
    try:
        client = TestClient(app)
        _login(client)
        r = client.post(
            "/companies/DN_WS2/run-checks", data={"year": "2024"}, follow_redirects=False,
        )
        assert r.status_code == 303
        with new_session() as db:
            job = db.query(Job).order_by(Job.id.desc()).first()
            assert job.kind == JobKind.RUN_CHECKS.value
            assert "only" not in job.payload
    finally:
        _teardown(new_engine)


def test_company_detail_renders_run_modal():
    """Modal "Chọn test chạy" (native <dialog>) render kèm wiring data-open-modal."""
    new_engine, _ = _setup_db()
    try:
        client = TestClient(app)
        _login(client)
        r = client.get("/companies/DN_WS2?year=2024")
        assert r.status_code == 200
        assert 'data-open-modal="run-tests-modal"' in r.text
        assert 'id="run-tests-modal"' in r.text
        assert "modal-check-grid" in r.text
    finally:
        _teardown(new_engine)


def test_no_year_still_batch():
    new_engine, new_session = _setup_db()
    try:
        client = TestClient(app)
        _login(client)
        r = client.post("/companies/DN_WS2/run-checks", data={}, follow_redirects=False)
        assert r.status_code == 303
        with new_session() as db:
            job = db.query(Job).order_by(Job.id.desc()).first()
            assert job.kind == JobKind.BATCH_RUN.value
            assert "only" not in job.payload
    finally:
        _teardown(new_engine)
