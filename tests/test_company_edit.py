"""Trang sửa DN — GET prefill + POST cập nhật (name giữ hậu tố Demo, industry...)."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.pool import StaticPool

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import Company


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
        db.add(Company(code="DN_077", name="Cũ (Demo)", tax_id="111", industry="Cơ khí"))
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


def test_edit_form_prefills_and_locks_code():
    new_engine, _ = _setup_db()
    try:
        client = TestClient(app)
        _login(client)
        r = client.get("/companies/DN_077/edit")
        assert r.status_code == 200
        assert "DN_077" in r.text
        assert "Cơ khí" in r.text
        # Mã DN phải bị khoá (disabled), không cho sửa.
        assert "disabled" in r.text
    finally:
        _teardown(new_engine)


def test_edit_updates_fields_and_keeps_demo_suffix():
    new_engine, new_session = _setup_db()
    try:
        client = TestClient(app)
        _login(client)
        r = client.post(
            "/companies/DN_077/edit",
            data={"name": "Tiên Phong", "tax_id": "999", "address": "KCN X", "industry": "Dệt may"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert r.headers["location"] == "/companies/DN_077"
        with new_session() as db:
            c = db.scalar(select(Company).where(Company.code == "DN_077"))
            assert c.name == "Tiên Phong (Demo)"  # hậu tố tự thêm
            assert c.tax_id == "999"
            assert c.address == "KCN X"
            assert c.industry == "Dệt may"
    finally:
        _teardown(new_engine)


def test_edit_saves_first_bcqt_year():
    new_engine, new_session = _setup_db()
    try:
        client = TestClient(app)
        _login(client)
        r = client.post(
            "/companies/DN_077/edit",
            data={"name": "Tiên Phong", "first_bcqt_year": "2019"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        with new_session() as db:
            c = db.scalar(select(Company).where(Company.code == "DN_077"))
            assert c.first_bcqt_year == 2019
        # GET prefill lại đúng giá trị vừa lưu.
        assert 'value="2019"' in client.get("/companies/DN_077/edit").text
    finally:
        _teardown(new_engine)


def test_edit_blank_first_bcqt_year_saves_null():
    new_engine, new_session = _setup_db()
    try:
        with new_session() as db:
            c = db.scalar(select(Company).where(Company.code == "DN_077"))
            c.first_bcqt_year = 2019
            db.commit()
        client = TestClient(app)
        _login(client)
        r = client.post(
            "/companies/DN_077/edit",
            data={"name": "Tiên Phong", "first_bcqt_year": "  "},
            follow_redirects=False,
        )
        assert r.status_code == 303
        with new_session() as db:
            c = db.scalar(select(Company).where(Company.code == "DN_077"))
            # Trống nghĩa là "chưa biết" — NULL, không phải 0.
            assert c.first_bcqt_year is None
    finally:
        _teardown(new_engine)


def test_edit_rejects_invalid_first_bcqt_year():
    new_engine, new_session = _setup_db()
    try:
        with new_session() as db:
            c = db.scalar(select(Company).where(Company.code == "DN_077"))
            c.first_bcqt_year = 2019
            db.commit()
        client = TestClient(app)
        _login(client)
        for bad in ("hai nghìn", "19", "20255"):
            r = client.post(
                "/companies/DN_077/edit",
                data={"name": "Tiên Phong", "first_bcqt_year": bad},
                follow_redirects=False,
            )
            assert r.status_code == 400, bad
            with new_session() as db:
                c = db.scalar(select(Company).where(Company.code == "DN_077"))
                assert c.first_bcqt_year == 2019, bad  # giá trị cũ không bị ghi đè
                assert c.name == "Cũ (Demo)"
    finally:
        _teardown(new_engine)


def test_edit_unknown_code_404():
    new_engine, _ = _setup_db()
    try:
        client = TestClient(app)
        _login(client)
        assert client.get("/companies/NOPE/edit").status_code == 404
    finally:
        _teardown(new_engine)
