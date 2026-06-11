"""Đổi trạng thái finding → điểm tính lại ngay (recompute_company_year + route)."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.pool import StaticPool

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import Company, CompanyYearScore, Finding, NvlBalance
from app.pipeline.recompute import recompute_company_year

# ─────────────────────────── unit: helper ───────────────────────────

def test_recompute_drops_score_when_finding_rejected(session, company):
    session.add_all([
        NvlBalance(company_id=company.id, period_year=2024, material_code="NVL_1"),
        NvlBalance(company_id=company.id, period_year=2024, material_code="NVL_2"),
    ])
    f = Finding(company_id=company.id, period_year=2024, check_code="C2.3",
                severity="critical", subject_key="NVL_1", title="Tồn âm", status="new")
    session.add(f)
    session.commit()

    cys = recompute_company_year(session, company.id, 2024)
    session.commit()
    assert cys.score > 0
    before = cys.score

    # Cán bộ "Loại trừ" finding → recompute → điểm phải giảm về 0 (không còn finding tính).
    f.status = "rejected"
    session.flush()
    cys2 = recompute_company_year(session, company.id, 2024)
    session.commit()
    assert cys2.score < before
    assert cys2.score == 0
    # company.risk_score đồng bộ theo.
    session.refresh(company)
    assert company.risk_score == cys2.score


# ─────────────────────────── route end-to-end ───────────────────────────

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
            NvlBalance(company_id=c.id, period_year=2024, material_code="NVL_1"),
            NvlBalance(company_id=c.id, period_year=2024, material_code="NVL_2"),
        ])
        db.add_all([
            Finding(company_id=c.id, period_year=2024, check_code="C2.3", severity="critical",
                    subject_key="NVL_1", title="Tồn âm 1", status="new"),
            Finding(company_id=c.id, period_year=2024, check_code="C2.3", severity="critical",
                    subject_key="NVL_2", title="Tồn âm 2", status="new"),
        ])
        db.flush()
        recompute_company_year(db, c.id, 2024)
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


def test_status_route_recomputes_score_immediately():
    new_engine, new_session = _setup_db()
    try:
        client = TestClient(app)
        _login(client)
        with new_session() as db:
            fid = db.scalar(
                select(Finding.id).where(Finding.subject_key == "NVL_1")
            )
            before = db.scalar(select(CompanyYearScore.score))
        assert before and before > 0

        r = client.post(
            f"/findings/{fid}/status",
            data={"status": "rejected", "notes": "trùng lặp"},
            follow_redirects=False,
        )
        assert r.status_code == 303

        with new_session() as db:
            after = db.scalar(select(CompanyYearScore.score))
            company = db.scalar(select(Company).where(Company.code == "DN_077"))
        assert after < before          # điểm giảm ngay sau khi Loại trừ
        assert company.risk_score == after
    finally:
        _teardown(new_engine)
