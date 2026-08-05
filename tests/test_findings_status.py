"""Test route POST /findings/{id}/status — đánh dấu finding."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import Company, Finding


def _setup_db():
    """In-memory SQLite shared across the test client and direct queries."""
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
    return new_engine, new_session


def _login(client: TestClient) -> None:
    response = client.post(
        "/login",
        data={"user": "admin", "password": "admin"},
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_update_finding_status_persists_status_and_notes():
    new_engine, new_session = _setup_db()
    try:
        # Seed: 1 company + 1 finding.
        with new_session() as s:
            c = Company(code="TESTCO", tax_id="1", name="Test")
            s.add(c)
            s.flush()
            f = Finding(
                company_id=c.id,
                period_year=2024,
                check_code="C2.1",
                severity="critical",
                subject_type="material_code",
                subject_key="X",
                title="Test finding",
            )
            s.add(f)
            s.commit()
            finding_id = f.id

        client = TestClient(app)
        _login(client)
        response = client.post(
            f"/findings/{finding_id}/status",
            data={"status": "confirmed", "notes": "Đã kiểm tra với DN"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert "/companies/TESTCO?year=2024" in response.headers["location"]

        with new_session() as s:
            updated = s.get(Finding, finding_id)
            assert updated.status == "confirmed"
            assert updated.notes == "Đã kiểm tra với DN"
    finally:
        new_engine.dispose()
        # Restore original engine references (tests outside this module use disk DB).
        import app.database as dbmod
        dbmod.engine = engine
        dbmod.SessionLocal = SessionLocal


def test_update_finding_status_rejects_invalid_status():
    new_engine, new_session = _setup_db()
    try:
        with new_session() as s:
            c = Company(code="TESTCO", tax_id="1", name="Test")
            s.add(c)
            s.flush()
            f = Finding(
                company_id=c.id, period_year=2024, check_code="C2.1",
                severity="critical", title="x",
            )
            s.add(f)
            s.commit()
            finding_id = f.id

        client = TestClient(app)
        _login(client)
        response = client.post(
            f"/findings/{finding_id}/status",
            data={"status": "garbage", "notes": ""},
            follow_redirects=False,
        )
        assert response.status_code == 400
    finally:
        new_engine.dispose()
        import app.database as dbmod
        dbmod.engine = engine
        dbmod.SessionLocal = SessionLocal


def test_update_finding_requires_login():
    client = TestClient(app)
    response = client.post(
        "/findings/1/status",
        data={"status": "confirmed", "notes": ""},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/login"

def test_recompute_does_not_open_a_nested_session_and_lose_the_write():
    """Hồi quy: `recompute_company_year` từng làm mất chính UPDATE vừa ghi.

    `tier_for` gọi `get_tiers()` không truyền db → cache trống thì mở
    `SessionLocal()` riêng; session lồng đó `close()` phát ROLLBACK. Khi hai
    session dùng chung một connection (SQLite in-memory + StaticPool) thì
    `finding.status` đang treo bị huỷ theo. Test gọi thẳng hàm, không qua HTTP,
    để hỏng ở tầng nào cũng lộ.
    """
    from app.app_settings import invalidate_cache
    from app.pipeline.recompute import recompute_company_year

    new_engine, new_session = _setup_db()
    try:
        with new_session() as s:
            c = Company(code="RECO", tax_id="1", name="Reco")
            s.add(c)
            s.flush()
            f = Finding(
                company_id=c.id, period_year=2024, check_code="C2.1",
                severity="critical", subject_key="X", title="x",
            )
            s.add(f)
            s.commit()
            finding_id, company_id = f.id, c.id

        invalidate_cache()  # cache trống = điều kiện làm lộ lỗi
        with new_session() as s:
            s.get(Finding, finding_id).status = "confirmed"
            s.flush()
            recompute_company_year(s, company_id, 2024)
            s.commit()

        with new_session() as s:
            assert s.get(Finding, finding_id).status == "confirmed"
    finally:
        invalidate_cache()
        new_engine.dispose()
        import app.database as dbmod
        dbmod.engine = engine
        dbmod.SessionLocal = SessionLocal
