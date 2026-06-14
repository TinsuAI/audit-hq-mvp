"""P2 — siết auth cho thí điểm thật: rate-limit login, nhật ký truy cập,
validate magic-byte upload, và trang tự đổi mật khẩu (tuỳ chọn, KHÔNG ép)."""

from __future__ import annotations

import io
import types

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.pool import StaticPool

from app import login_guard
from app.audit import ACTION_EXPORT, log_access
from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import AccessEvent, Company
from app.routes.companies import _looks_like_excel, _write_upload_stream


@pytest.fixture(autouse=True)
def _reset_login_guard():
    login_guard.reset_all()
    yield
    login_guard.reset_all()


def _setup_db():
    import app.database as dbmod
    from app.auth_users import create_user, seed_default_admin

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
        a = Company(code="DN_001", name="A", tax_id="1")
        db.add(a)
        db.flush()
        off = create_user(db, "off1", "officerpw", "officer")
        off.companies = [a]
        db.commit()
    return new_engine, new_session


def _teardown(new_engine):
    new_engine.dispose()
    import app.database as dbmod
    dbmod.engine = engine
    dbmod.SessionLocal = SessionLocal


# ─────────────────────── tự đổi mật khẩu (không ép) ───────────────────────

def test_login_not_forced_to_change():
    """Đăng nhập vào thẳng trang chủ — KHÔNG bị ép đổi mật khẩu."""
    new_engine, _ = _setup_db()
    try:
        client = TestClient(app)
        r = client.post(
            "/login", data={"user": "off1", "password": "officerpw"}, follow_redirects=False
        )
        assert r.status_code == 303 and r.headers["location"] == "/"
        assert client.get("/companies", follow_redirects=False).status_code == 200
    finally:
        _teardown(new_engine)


def test_self_service_change_password_works():
    new_engine, _ = _setup_db()
    try:
        client = TestClient(app)
        client.post("/login", data={"user": "admin", "password": "admin"}, follow_redirects=False)
        r = client.post(
            "/change-password",
            data={"new_password": "newadmin123", "confirm_password": "newadmin123"},
            follow_redirects=False,
        )
        assert r.status_code == 303 and r.headers["location"] == "/"
        # Mật khẩu cũ hỏng, mật khẩu mới đăng nhập được.
        fresh = TestClient(app)
        login_guard.reset_all()
        assert fresh.post(
            "/login", data={"user": "admin", "password": "admin"}, follow_redirects=False
        ).status_code == 401
        assert fresh.post(
            "/login", data={"user": "admin", "password": "newadmin123"}, follow_redirects=False
        ).status_code == 303
    finally:
        _teardown(new_engine)


def test_change_password_rejects_mismatch_and_short():
    new_engine, _ = _setup_db()
    try:
        client = TestClient(app)
        client.post("/login", data={"user": "admin", "password": "admin"}, follow_redirects=False)
        assert client.post(
            "/change-password",
            data={"new_password": "longenough1", "confirm_password": "different1"},
            follow_redirects=False,
        ).status_code == 400
        assert client.post(
            "/change-password",
            data={"new_password": "short", "confirm_password": "short"},
            follow_redirects=False,
        ).status_code == 400
    finally:
        _teardown(new_engine)


# ─────────────────────────── rate-limit login ───────────────────────────

def test_login_lockout_after_repeated_failures():
    new_engine, _ = _setup_db()
    try:
        client = TestClient(app)
        for _ in range(login_guard.MAX_FAILS):
            r = client.post(
                "/login", data={"user": "admin", "password": "wrong"}, follow_redirects=False
            )
            assert r.status_code == 401
        # Vượt ngưỡng → khoá, kể cả mật khẩu đúng cũng bị chặn.
        locked = client.post(
            "/login", data={"user": "admin", "password": "admin"}, follow_redirects=False
        )
        assert locked.status_code == 429
        # Reset → đăng nhập lại được.
        login_guard.reset_all()
        ok = client.post(
            "/login", data={"user": "admin", "password": "admin"}, follow_redirects=False
        )
        assert ok.status_code == 303
    finally:
        _teardown(new_engine)


# ─────────────────────────── nhật ký truy cập ───────────────────────────

def test_log_access_creates_row(session):
    log_access(session, username="bob", action=ACTION_EXPORT, company_code="DN_001", detail="year=2024")
    row = session.scalar(select(AccessEvent))
    assert row.username == "bob" and row.action == ACTION_EXPORT and row.company_code == "DN_001"


def test_export_route_writes_audit_event():
    new_engine, new_session = _setup_db()
    try:
        client = TestClient(app)
        client.post("/login", data={"user": "admin", "password": "admin"}, follow_redirects=False)
        r = client.get("/companies/DN_001/export?year=2024")
        assert r.status_code == 200
        with new_session() as db:
            ev = db.scalar(select(AccessEvent).where(AccessEvent.action == ACTION_EXPORT))
            assert ev is not None and ev.company_code == "DN_001" and ev.username == "admin"
    finally:
        _teardown(new_engine)


def test_audit_page_admin_only():
    new_engine, new_session = _setup_db()
    try:
        with new_session() as db:
            db.add(AccessEvent(username="admin", action=ACTION_EXPORT, company_code="DN_001"))
            db.commit()
        admin = TestClient(app)
        admin.post("/login", data={"user": "admin", "password": "admin"}, follow_redirects=False)
        r = admin.get("/admin/audit")
        assert r.status_code == 200 and "DN_001" in r.text
        # Officer không được vào trang quản trị.
        off = TestClient(app)
        off.post("/login", data={"user": "off1", "password": "officerpw"}, follow_redirects=False)
        assert off.get("/admin/audit").status_code == 403
    finally:
        _teardown(new_engine)


# ─────────────────────────── magic-byte upload ───────────────────────────

def test_looks_like_excel():
    assert _looks_like_excel(b"PK\x03\x04xxxx", ".xlsx")
    assert not _looks_like_excel(b"hello world", ".xlsx")
    assert _looks_like_excel(b"\xd0\xcf\x11\xe0aaaa", ".xls")
    assert not _looks_like_excel(b"PK\x03\x04", ".xls")
    assert not _looks_like_excel(b"PK\x03\x04", ".csv")


def test_write_upload_rejects_mislabeled(tmp_path):
    fake = types.SimpleNamespace(file=io.BytesIO(b"this is plain text, not excel"))
    dest = tmp_path / "x.xlsx"
    with pytest.raises(HTTPException) as ei:
        _write_upload_stream(fake, dest, expected_ext=".xlsx")
    assert ei.value.status_code == 400
    assert not dest.exists()  # file rác đã được dọn


def test_write_upload_accepts_valid_magic(tmp_path):
    fake = types.SimpleNamespace(file=io.BytesIO(b"PK\x03\x04" + b"\x00" * 200))
    dest = tmp_path / "x.xlsx"
    n = _write_upload_stream(fake, dest, expected_ext=".xlsx")
    assert n == 204 and dest.exists()
