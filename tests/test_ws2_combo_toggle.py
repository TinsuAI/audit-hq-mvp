"""WS2-4 — toggle combos_enabled (admin) + ẩn/hiện combo ở company_detail.

Default OFF: combo bị ẩn ở company_detail dù còn COMBO_* trong DB. Admin bật →
hiện. Toggle lazy per-run cho recompute; render gate theo setting sống (ADR #18
Revision — WS2).
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool

from app.app_settings import get_combos_enabled, invalidate_cache
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
    invalidate_cache()
    with new_session() as db:
        seed_default_admin(db, "admin", "admin")
        c = Company(code="DN_CMB", name="Test", tax_id="1")
        db.add(c)
        db.flush()
        db.add(Finding(
            company_id=c.id, period_year=2024, check_code="COMBO_FORGED_NORM",
            severity="critical", subject_type="material_code", subject_key="MAT_X",
            title="[MAT_X] combo test",
        ))
        db.commit()
    return new_engine, new_session


def _teardown(new_engine):
    new_engine.dispose()
    import app.database as dbmod
    dbmod.engine = engine
    dbmod.SessionLocal = SessionLocal
    invalidate_cache()


def _login(client: TestClient) -> None:
    r = client.post("/login", data={"user": "admin", "password": "admin"}, follow_redirects=False)
    assert r.status_code == 303


def test_toggle_sets_and_clears_flag():
    new_engine, new_session = _setup_db()
    try:
        client = TestClient(app)
        _login(client)
        assert get_combos_enabled(new_session()) is False  # default

        r = client.post("/admin/checks/combos-toggle", data={"enabled": "1"}, follow_redirects=False)
        assert r.status_code == 303
        assert get_combos_enabled() is True

        r = client.post("/admin/checks/combos-toggle", data={}, follow_redirects=False)
        assert r.status_code == 303
        assert get_combos_enabled() is False
    finally:
        _teardown(new_engine)


def test_company_detail_hides_combo_when_off():
    new_engine, _ = _setup_db()
    try:
        client = TestClient(app)
        _login(client)
        # OFF mặc định: dù có COMBO_* trong DB, section combo bị ẩn.
        r = client.get("/companies/DN_CMB?year=2024")
        assert r.status_code == 200
        assert "Phát hiện kết hợp" not in r.text

        # Bật → hiện.
        client.post("/admin/checks/combos-toggle", data={"enabled": "1"}, follow_redirects=False)
        r = client.get("/companies/DN_CMB?year=2024")
        assert r.status_code == 200
        assert "Phát hiện kết hợp" in r.text
    finally:
        _teardown(new_engine)
