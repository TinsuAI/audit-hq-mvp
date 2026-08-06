"""POST /companies/{code}/documents/period — sửa kỳ báo cáo (custom date)."""

from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.pool import StaticPool

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import Company, CompanyPeriod


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
        db.add(Company(code="DN_077", name="Cơ khí Test", tax_id="111"))
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


def _period(session, code, year=2025):
    with session() as db:
        c = db.scalar(select(Company).where(Company.code == code))
        return db.scalar(
            select(CompanyPeriod).where(
                CompanyPeriod.company_id == c.id, CompanyPeriod.period_year == year
            )
        )


def test_set_period_saves_manual_window():
    new_engine, new_session = _setup_db()
    try:
        client = TestClient(app)
        _login(client)
        r = client.post(
            "/companies/DN_077/documents/period",
            data={"year": 2025, "period_from": "2025-04-01", "period_to": "2026-03-31"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        cp = _period(new_session, "DN_077")
        assert cp is not None
        assert cp.period_from == date(2025, 4, 1)
        assert cp.period_to == date(2026, 3, 31)
        assert cp.is_manual is True
    finally:
        _teardown(new_engine)


def test_from_after_to_rejected():
    new_engine, new_session = _setup_db()
    try:
        client = TestClient(app)
        _login(client)
        r = client.post(
            "/companies/DN_077/documents/period",
            data={"year": 2025, "period_from": "2026-03-31", "period_to": "2025-04-01"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert "error" in r.headers["location"]
        assert _period(new_session, "DN_077") is None
    finally:
        _teardown(new_engine)


def test_reset_clears_manual_flag():
    new_engine, new_session = _setup_db()
    try:
        client = TestClient(app)
        _login(client)
        client.post(
            "/companies/DN_077/documents/period",
            data={"year": 2025, "period_from": "2025-04-01", "period_to": "2026-03-31"},
            follow_redirects=False,
        )
        r = client.post(
            "/companies/DN_077/documents/period",
            data={"year": 2025, "reset": "1"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        cp = _period(new_session, "DN_077")
        assert cp is not None and cp.is_manual is False
    finally:
        _teardown(new_engine)


def test_documents_page_shows_custom_window():
    new_engine, new_session = _setup_db()
    try:
        with new_session() as db:
            c = db.scalar(select(Company).where(Company.code == "DN_077"))
            db.add(
                CompanyPeriod(
                    company_id=c.id,
                    period_year=2025,
                    period_from=date(2025, 4, 1),
                    period_to=date(2026, 3, 31),
                    is_manual=True,
                )
            )
            db.commit()
        client = TestClient(app)
        _login(client)
        r = client.get("/companies/DN_077/documents")
        assert r.status_code == 200
        assert "Kỳ báo cáo" in r.text
        assert "01/04/2025 – 31/03/2026" in r.text
        assert "sửa tay" in r.text
    finally:
        _teardown(new_engine)


def test_company_detail_shows_fiscal_window_label():
    new_engine, new_session = _setup_db()
    try:
        from app.models import NvlBalance
        with new_session() as db:
            c = db.scalar(select(Company).where(Company.code == "DN_077"))
            db.add(NvlBalance(company_id=c.id, period_year=2025, material_code="X", unit="PCE"))
            db.add(CompanyPeriod(
                company_id=c.id, period_year=2025,
                period_from=date(2025, 4, 1), period_to=date(2026, 3, 31), is_manual=False,
            ))
            db.commit()
        client = TestClient(app)
        _login(client)
        r = client.get("/companies/DN_077?year=2025")
        assert r.status_code == 200
        assert "năm tài chính" in r.text
        assert "01/04/2025 – 31/03/2026" in r.text
    finally:
        _teardown(new_engine)


def test_unknown_company_404():
    new_engine, _ = _setup_db()
    try:
        client = TestClient(app)
        _login(client)
        r = client.post(
            "/companies/NOPE/documents/period",
            data={"year": 2025, "period_from": "2025-04-01", "period_to": "2026-03-31"},
            follow_redirects=False,
        )
        assert r.status_code == 404
    finally:
        _teardown(new_engine)


# --- #66: cửa sổ phải hợp lệ với nhãn kỳ -------------------------------------


def test_window_from_another_year_is_rejected():
    """Ca HIEP_QUANG: kỳ 2024 không được nhận cửa sổ nằm trọn trong 2022."""
    new_engine, new_session = _setup_db()
    try:
        client = TestClient(app)
        _login(client)
        r = client.post(
            "/companies/DN_077/documents/period",
            data={"year": 2024, "period_from": "2022-01-01", "period_to": "2022-12-31"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert "error" in r.headers["location"]
        assert _period(new_session, "DN_077") is None
    finally:
        _teardown(new_engine)


def test_window_longer_than_15_months_is_rejected():
    new_engine, new_session = _setup_db()
    try:
        client = TestClient(app)
        _login(client)
        r = client.post(
            "/companies/DN_077/documents/period",
            data={"year": 2025, "period_from": "2025-01-01", "period_to": "2026-06-30"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert "error" in r.headers["location"]
        assert _period(new_session, "DN_077") is None
    finally:
        _teardown(new_engine)


def test_merged_period_of_15_months_is_accepted():
    """Kỳ đầu/cuối gộp tới 15 tháng là hợp pháp — không được chặn nhầm."""
    new_engine, new_session = _setup_db()
    try:
        client = TestClient(app)
        _login(client)
        r = client.post(
            "/companies/DN_077/documents/period",
            data={"year": 2025, "period_from": "2025-10-01", "period_to": "2026-12-31"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert "error" not in r.headers["location"]
        cp = _period(new_session, "DN_077")
        assert cp is not None and cp.period_to == date(2026, 12, 31)
    finally:
        _teardown(new_engine)


def test_window_identical_to_another_period_is_rejected():
    new_engine, new_session = _setup_db()
    try:
        client = TestClient(app)
        _login(client)
        client.post(
            "/companies/DN_077/documents/period",
            data={"year": 2025, "period_from": "2025-01-01", "period_to": "2025-12-31"},
            follow_redirects=False,
        )
        r = client.post(
            "/companies/DN_077/documents/period",
            data={"year": 2026, "period_from": "2025-01-01", "period_to": "2025-12-31"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert "error" in r.headers["location"]
        with new_session() as db:
            rows = db.query(CompanyPeriod).all()
        assert [r.period_year for r in rows] == [2025]
    finally:
        _teardown(new_engine)
