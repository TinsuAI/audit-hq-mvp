"""Trang danh sách DN đọc điểm từ max(CompanyYearScore), không drift theo cache
`companies.risk_score` (regression cho bug DN_002 list=30 vs detail=28)."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import Company, CompanyYearScore


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
    return new_engine, new_session


def _teardown(new_engine):
    new_engine.dispose()
    import app.database as dbmod
    dbmod.engine = engine
    dbmod.SessionLocal = SessionLocal


def _login(client: TestClient) -> None:
    r = client.post("/login", data={"user": "admin", "password": "admin"}, follow_redirects=False)
    assert r.status_code == 303


def test_list_shows_max_cys_not_stale_risk_score():
    new_engine, new_session = _setup_db()
    try:
        with new_session() as db:
            c = Company(code="DN_A", name="A", tax_id="1", risk_score=30)  # cache STALE
            db.add(c)
            db.flush()
            db.add(CompanyYearScore(company_id=c.id, period_year=2024, score=28, tier="t", breakdown={}))
            db.add(CompanyYearScore(company_id=c.id, period_year=2025, score=28, tier="t", breakdown={}))
            db.commit()
        client = TestClient(app)
        _login(client)
        r = client.get("/companies")
        assert r.status_code == 200
        assert ">28</span>" in r.text          # điểm hiển thị = max(CYS)
        assert ">30</span>" not in r.text       # KHÔNG dùng cache stale
    finally:
        _teardown(new_engine)


def test_list_ranks_by_max_cys_not_risk_score():
    new_engine, new_session = _setup_db()
    try:
        with new_session() as db:
            lo = Company(code="DN_LO", name="Lo", tax_id="1", risk_score=999)  # cache cao giả
            hi = Company(code="DN_HI", name="Hi", tax_id="2", risk_score=1)     # cache thấp giả
            db.add_all([lo, hi])
            db.flush()
            db.add(CompanyYearScore(company_id=lo.id, period_year=2024, score=10, tier="t", breakdown={}))
            db.add(CompanyYearScore(company_id=hi.id, period_year=2024, score=50, tier="t", breakdown={}))
            db.commit()
        client = TestClient(app)
        _login(client)
        r = client.get("/companies")
        assert r.status_code == 200
        # DN_HI (max CYS 50) đứng trước DN_LO (10) bất kể risk_score cache.
        assert r.text.index("DN_HI") < r.text.index("DN_LO")
    finally:
        _teardown(new_engine)
