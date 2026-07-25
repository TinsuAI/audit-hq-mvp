"""2SỔ-2 (#20) — nhãn sổ trên findings: dòng split per-check + pill + finding_detail.

Chỉ pháp nhân nhiều sổ. Một sổ (002/006) → KHÔNG split, KHÔNG pill, KHÔNG field.
Combo COMBO_* (book=NULL) hiện dưới "Chung". Xem ADR #19 Revision — UI + upload.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.pool import StaticPool

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import Company, Finding, NvlBalance


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


def _login(client):
    client.post("/login", data={"user": "admin", "password": "admin"}, follow_redirects=False)


def _seed_multi_book(db, code="DN_MB"):
    c = Company(code=code, name="Pháp nhân 2 sổ", tax_id="0901051747")
    db.add(c)
    db.flush()
    db.add_all([
        NvlBalance(company_id=c.id, period_year=2025, book="EPE", material_code="A", unit="PCE"),
        NvlBalance(company_id=c.id, period_year=2025, book="GC", material_code="C", unit="PCE"),
    ])
    # C4.3 nội-sổ: 2 EPE. C1.1 cross-layer: book=NULL (Chung).
    db.add_all([
        Finding(company_id=c.id, period_year=2025, check_code="C4.3",
                severity="warning", book="EPE", subject_key="A", title="epe1"),
        Finding(company_id=c.id, period_year=2025, check_code="C4.3",
                severity="warning", book="EPE", subject_key="A2", title="epe2"),
        Finding(company_id=c.id, period_year=2025, check_code="C1.1",
                severity="critical", book=None, subject_key="X", title="chung1"),
    ])
    db.commit()
    return c


def test_multi_book_shows_split_and_pills():
    new_engine, new_session = _setup_db()
    try:
        with new_session() as db:
            _seed_multi_book(db, "DN_MB")
        client = TestClient(app)
        _login(client)
        html = client.get("/companies/DN_MB?year=2025").text

        # Dòng split per-check: C4.3 → "Sổ: EPE 2"; C1.1 → "Sổ: Chung 1".
        assert "Sổ: " in html
        assert "EPE 2" in html
        assert "Chung 1" in html
        # Pill mỗi dòng finding.
        assert "book-pill" in html
        assert ">EPE<" in html or "EPE</span>" in html
        assert ">Chung<" in html or "Chung</span>" in html
    finally:
        _teardown(new_engine)


def test_single_book_no_split_no_pill():
    new_engine, new_session = _setup_db()
    try:
        with new_session() as db:
            c = Company(code="DN_SB", name="Một sổ", tax_id="111")
            db.add(c)
            db.flush()
            db.add(NvlBalance(company_id=c.id, period_year=2025, material_code="Z", unit="PCE"))
            db.add(Finding(company_id=c.id, period_year=2025, check_code="C4.3",
                           severity="warning", book=None, subject_key="Z", title="x"))
            db.commit()
        client = TestClient(app)
        _login(client)
        html = client.get("/companies/DN_SB?year=2025").text
        assert "book-pill" not in html
        assert "book-split" not in html
        assert "Sổ: " not in html
    finally:
        _teardown(new_engine)


def test_finding_detail_book_field_multi_vs_single():
    new_engine, new_session = _setup_db()
    try:
        with new_session() as db:
            _seed_multi_book(db, "DN_MB")
            epe_fid = db.scalar(select(Finding).where(Finding.book == "EPE")).id
            chung_fid = db.scalar(select(Finding).where(Finding.book.is_(None))).id
            # Single-book finding.
            sb = Company(code="DN_SB", name="Một sổ", tax_id="111")
            db.add(sb)
            db.flush()
            db.add(NvlBalance(company_id=sb.id, period_year=2025, material_code="Z", unit="PCE"))
            db.flush()
            sb_f = Finding(company_id=sb.id, period_year=2025, check_code="C4.3",
                           severity="warning", book=None, subject_key="Z", title="x")
            db.add(sb_f)
            db.commit()
            sb_fid = sb_f.id
        client = TestClient(app)
        _login(client)

        epe = client.get(f"/findings/{epe_fid}").text
        assert "Sổ quyết toán" in epe
        assert "Sổ EPE (chế xuất)" in epe

        chung = client.get(f"/findings/{chung_fid}").text
        assert "Sổ quyết toán" in chung
        assert "Chung (liên sổ)" in chung

        single = client.get(f"/findings/{sb_fid}").text
        assert "Sổ quyết toán" not in single      # một sổ → không field
    finally:
        _teardown(new_engine)


def test_combo_finding_shows_chung_pill():
    from app.app_settings import invalidate_cache, set_combos_enabled

    new_engine, new_session = _setup_db()
    try:
        with new_session() as db:
            c = _seed_multi_book(db, "DN_MB")
            db.add(Finding(company_id=c.id, period_year=2025, check_code="COMBO_FORGED_NORM",
                           severity="critical", book=None, subject_key="A", title="combo x"))
            db.commit()
            set_combos_enabled(True, "test", db)
        client = TestClient(app)
        _login(client)
        html = client.get("/companies/DN_MB?year=2025").text
        # Combo card head có pill Chung (multi-book), không special-case.
        assert "combo-card-head" in html
        assert 'book-pill chung' in html
    finally:
        with new_session() as db:
            set_combos_enabled(False, "test", db)
        invalidate_cache()
        _teardown(new_engine)
