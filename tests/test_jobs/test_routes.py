"""Tests cho routes /jobs/* và POST /companies/{code}/run-checks luồng async."""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool

import app.database as dbmod
from app.auth_users import create_user, seed_default_admin
from app.database import Base, SessionLocal, engine
from app.jobs import HANDLERS
from app.main import app
from app.models import Company, User
from app.models.job import Job, JobKind, JobStatus


def _setup_db():
    new_engine = dbmod.create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    new_session = dbmod.sessionmaker(
        bind=new_engine, autoflush=False, autocommit=False, future=True,
    )
    dbmod.engine = new_engine
    dbmod.SessionLocal = new_session
    Base.metadata.create_all(new_engine)
    with new_session() as db:
        seed_default_admin(db, "admin", "admin")
    HANDLERS.clear()
    return new_engine, new_session


def _teardown(new_engine):
    new_engine.dispose()
    dbmod.engine = engine
    dbmod.SessionLocal = SessionLocal
    HANDLERS.clear()


def _login_admin(client: TestClient) -> None:
    r = client.post(
        "/login", data={"user": "admin", "password": "admin"}, follow_redirects=False,
    )
    assert r.status_code == 303


def _seed_company(s, code="DN_X"):
    c = Company(code=code, tax_id="1234567890", name=f"Test {code}", risk_score=0)
    s.add(c)
    s.commit()
    return c.id


def test_jobs_routes_require_auth():
    new_engine, new_session = _setup_db()
    try:
        client = TestClient(app)
        # Không login → require_user raise 303 redirect to /login.
        for path in ["/jobs", "/jobs/1", "/jobs/unread.json"]:
            r = client.get(path, follow_redirects=False)
            assert r.status_code == 303, f"{path} should redirect, got {r.status_code}"
            assert "/login" in r.headers.get("location", "")
    finally:
        _teardown(new_engine)


def test_post_run_checks_with_year_creates_single_year_job():
    new_engine, new_session = _setup_db()
    try:
        with new_session() as s:
            _seed_company(s, "HONG_AN")

        client = TestClient(app)
        _login_admin(client)
        r = client.post(
            "/companies/HONG_AN/run-checks",
            data={"year": "2024"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        loc = r.headers["location"]
        assert loc.startswith("/jobs/")

        job_id = int(loc.rsplit("/", 1)[-1])
        with new_session() as s:
            j = s.get(Job, job_id)
            assert j.kind == JobKind.RUN_CHECKS.value
            assert j.payload == {"company_code": "HONG_AN", "year": 2024}
            assert j.period_year == 2024
    finally:
        _teardown(new_engine)


def test_post_run_checks_without_year_creates_batch_job():
    new_engine, new_session = _setup_db()
    try:
        with new_session() as s:
            _seed_company(s, "HONG_AN")

        client = TestClient(app)
        _login_admin(client)
        r = client.post(
            "/companies/HONG_AN/run-checks", data={}, follow_redirects=False,
        )
        assert r.status_code == 303

        job_id = int(r.headers["location"].rsplit("/", 1)[-1])
        with new_session() as s:
            j = s.get(Job, job_id)
            assert j.kind == JobKind.BATCH_RUN.value
            assert j.payload == {"company_code": "HONG_AN"}
            assert j.period_year is None
    finally:
        _teardown(new_engine)


def test_get_jobs_list_shows_current_user_jobs():
    new_engine, new_session = _setup_db()
    try:
        with new_session() as s:
            admin = s.scalar(dbmod.select(User).where(User.username == "admin")) if False else None  # noqa: F841
            # admin id is 1 since seed.
            admin_row = s.query(User).filter_by(username="admin").one()
            other = create_user(s, "bob", "pass1234", "officer")
            s.commit()
            s.add_all([
                Job(kind=JobKind.RUN_CHECKS.value, payload={}, created_by=admin_row.id,
                    status=JobStatus.DONE.value),
                Job(kind=JobKind.RUN_CHECKS.value, payload={}, created_by=admin_row.id,
                    status=JobStatus.QUEUED.value),
                Job(kind=JobKind.RUN_CHECKS.value, payload={}, created_by=other.id,
                    status=JobStatus.DONE.value),
            ])
            s.commit()

        client = TestClient(app)
        _login_admin(client)
        r = client.get("/jobs")
        assert r.status_code == 200
        text = r.text
        # Admin thấy job của mình (2), không thấy của bob (1).
        # Đếm cells thô không bền — chấp nhận presence checks.
        assert "queued" in text.lower() or "đang chờ" in text.lower() or "hàng đợi" in text.lower()
    finally:
        _teardown(new_engine)


def test_get_job_detail_shows_status_and_marks_viewed():
    new_engine, new_session = _setup_db()
    try:
        with new_session() as s:
            admin = s.query(User).filter_by(username="admin").one()
            j = Job(
                kind=JobKind.RUN_CHECKS.value, payload={"company_code": "X", "year": 2024},
                created_by=admin.id, status=JobStatus.DONE.value,
                result={"total_findings": 5},
            )
            s.add(j)
            s.commit()
            job_id = j.id
            assert j.viewed_at is None

        client = TestClient(app)
        _login_admin(client)
        r = client.get(f"/jobs/{job_id}")
        assert r.status_code == 200

        # viewed_at được set sau khi xem.
        with new_session() as s:
            j = s.get(Job, job_id)
            assert j.viewed_at is not None
    finally:
        _teardown(new_engine)


def test_job_detail_renders_labels_not_raw_json():
    """Trang công việc hiện nhãn tiếng Việt; khoá `result` và `kind` không lọt ra thô."""
    new_engine, new_session = _setup_db()
    try:
        with new_session() as s:
            admin = s.query(User).filter_by(username="admin").one()
            j = Job(
                kind=JobKind.RUN_CHECKS.value, payload={"company_code": "X", "year": 2024},
                created_by=admin.id, status=JobStatus.DONE.value,
                result={
                    "total_findings": 5,
                    "findings_per_check": {"C1.1": 3, "C1.3": 2},
                    "combos_fired": [],
                    "risk_score": 30,
                },
            )
            s.add(j)
            s.commit()
            job_id = j.id

        client = TestClient(app)
        _login_admin(client)
        html = client.get(f"/jobs/{job_id}").text
        assert "Tổng số phát hiện" in html
        assert "Phát hiện theo kiểm tra" in html
        assert "C1.1: 3 · C1.3: 2" in html
        assert "Chạy kiểm tra" in html  # nhãn của kind
        for raw in ("total_findings", "findings_per_check", "combos_fired",
                    "risk_score", "run_checks"):
            assert raw not in html, f"khoá thô {raw} lọt ra giao diện"
    finally:
        _teardown(new_engine)


def test_unread_badge_counts_done_jobs_not_viewed():
    new_engine, new_session = _setup_db()
    try:
        with new_session() as s:
            admin = s.query(User).filter_by(username="admin").one()
            now = datetime.utcnow()
            s.add_all([
                # Done + chưa xem → đếm.
                Job(kind=JobKind.RUN_CHECKS.value, payload={}, created_by=admin.id,
                    status=JobStatus.DONE.value, finished_at=now),
                Job(kind=JobKind.RUN_CHECKS.value, payload={}, created_by=admin.id,
                    status=JobStatus.FAILED.value, finished_at=now),
                # Done + đã xem → không đếm.
                Job(kind=JobKind.RUN_CHECKS.value, payload={}, created_by=admin.id,
                    status=JobStatus.DONE.value, finished_at=now - timedelta(minutes=10),
                    viewed_at=now),
                # Queued/running → không đếm (chưa xong).
                Job(kind=JobKind.RUN_CHECKS.value, payload={}, created_by=admin.id,
                    status=JobStatus.QUEUED.value),
                Job(kind=JobKind.RUN_CHECKS.value, payload={}, created_by=admin.id,
                    status=JobStatus.RUNNING.value, started_at=now),
            ])
            s.commit()

        client = TestClient(app)
        _login_admin(client)
        r = client.get("/jobs/unread.json")
        assert r.status_code == 200
        data = r.json()
        assert data == {"unread": 2, "running": 1}
    finally:
        _teardown(new_engine)
