"""GET /api/chat/export-query — xuất Excel tùy biến từ SQL (guard chạy lại ở endpoint)."""

from __future__ import annotations

import io
from urllib.parse import quote

import openpyxl
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import Company, Finding


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
        c = Company(code="DN_077", name="Test (Demo)", tax_id="111")
        db.add(c)
        db.flush()
        db.add_all([
            Finding(company_id=c.id, period_year=2024, check_code="C2.3",
                    severity="critical", subject_key="A", title="t", status="new"),
            Finding(company_id=c.id, period_year=2024, check_code="C3.2",
                    severity="warning", subject_key="B", title="t", status="new"),
        ])
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


def test_export_query_returns_xlsx():
    new_engine, _ = _setup_db()
    try:
        client = TestClient(app)
        _login(client)
        sql = "SELECT severity, COUNT(*) n FROM v_findings WHERE company_code='DN_077' GROUP BY severity"
        r = client.get(f"/api/chat/export-query?sql={quote(sql)}&title={quote('Phân bố')}")
        assert r.status_code == 200
        assert "spreadsheetml" in r.headers["content-type"]
        wb = openpyxl.load_workbook(io.BytesIO(r.content))
        flat = "\n".join(
            str(c.value) for row in wb["Kết quả"].iter_rows() for c in row if c.value
        )
        assert "severity" in flat
        assert "v_findings" in flat  # câu SQL embed để truy nguồn
    finally:
        _teardown(new_engine)


def test_export_query_rejects_sensitive_table():
    new_engine, _ = _setup_db()
    try:
        client = TestClient(app)
        _login(client)
        r = client.get(f"/api/chat/export-query?sql={quote('SELECT * FROM users')}")
        assert r.status_code == 400
    finally:
        _teardown(new_engine)


def test_export_query_requires_auth():
    new_engine, _ = _setup_db()
    try:
        client = TestClient(app)  # không login
        r = client.get(
            f"/api/chat/export-query?sql={quote('SELECT 1 FROM v_findings')}",
            follow_redirects=False,
        )
        assert r.status_code == 303
    finally:
        _teardown(new_engine)
