"""Setting quy ước phân cách số + trang admin đổi nó.

Đổi setting phải ĐỔI NGAY con số trên màn hình (cache bị bust trong cùng
process), nếu không cán bộ bấm lưu rồi tưởng không ăn.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool

from app.app_settings import (
    DEFAULT_NUMBER_FORMAT,
    ValidationError,
    get_number_format,
    invalidate_cache,
    set_number_format,
)
from app.database import Base
from app.main import app
from app.models import Company, Finding


def _setup_db():
    import app.database as dbmod
    from app.auth_users import seed_default_admin

    new_engine = dbmod.create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    new_session = dbmod.sessionmaker(
        bind=new_engine, autoflush=False, autocommit=False, future=True
    )
    dbmod.engine = new_engine
    dbmod.SessionLocal = new_session
    Base.metadata.create_all(new_engine)
    with new_session() as db:
        seed_default_admin(db, "admin", "admin")
    invalidate_cache()
    return new_engine, new_session


def _login(client: TestClient) -> None:
    r = client.post(
        "/login", data={"user": "admin", "password": "admin"}, follow_redirects=False
    )
    assert r.status_code == 303


def test_default_is_vietnamese(session) -> None:
    invalidate_cache()
    assert get_number_format(session) == "vi" == DEFAULT_NUMBER_FORMAT


def test_saving_changes_what_the_reader_gets(session) -> None:
    invalidate_cache()
    set_number_format("en", updated_by="admin", db=session)
    assert get_number_format(session) == "en"
    invalidate_cache()


def test_invalid_style_is_refused(session) -> None:
    with pytest.raises(ValidationError):
        set_number_format("fr", updated_by="admin", db=session)


def test_admin_page_saves_and_the_finding_table_follows() -> None:
    """Cổng thật: đổi setting ở admin → số trên bảng phát hiện đổi theo."""
    _engine, new_session = _setup_db()
    try:
        with new_session() as s:
            c = Company(code="FMTCO", tax_id="1", name="Formatting Co")
            s.add(c)
            s.flush()
            s.add(Finding(
                company_id=c.id, period_year=2024, check_code="C1.6",
                severity="warning", subject_type="material_code", subject_key="NVL1",
                title="x", details={"m15_repurpose": 1234.5},
            ))
            s.commit()

        client = TestClient(app)
        _login(client)

        page = client.get("/companies/FMTCO?year=2024").text
        assert "1.234,50" in page, "mặc định phải là quy ước Việt Nam"

        r = client.post(
            "/admin/hien-thi", data={"number_format": "en"}, follow_redirects=False
        )
        assert r.status_code == 303

        page = client.get("/companies/FMTCO?year=2024").text
        assert "1,234.50" in page, "đổi setting nhưng bảng không đổi theo"
    finally:
        invalidate_cache()


def test_admin_page_requires_admin() -> None:
    _engine, _new_session = _setup_db()
    try:
        client = TestClient(app)
        r = client.get("/admin/hien-thi", follow_redirects=False)
        assert r.status_code in (302, 303, 401, 403)
    finally:
        invalidate_cache()
