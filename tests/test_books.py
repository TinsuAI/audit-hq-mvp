"""2SỔ-1 (#18) — helper company_books/book_label + strip tổng quan theo sổ.

Gate hiển thị = DỮ LIỆU (book trên nvl/sp/norms), KHÔNG suy từ finding: sổ sạch
(0 finding, có mã NVL) vẫn là một sổ. Xem ADR #19 Revision — UI + upload.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool

from app.books import book_label, book_summary, company_books, is_multi_book
from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import Company, Finding, Norm, NvlBalance

from .conftest import add_nvl, add_sp


def test_book_label_known_fallback_null():
    assert book_label("EPE") == "Sổ EPE (chế xuất)"
    assert book_label("GC") == "Sổ GC (gia công)"
    assert book_label("XYZ") == "Sổ XYZ"       # mã lạ → fallback raw
    assert book_label(None) == "Chung (liên sổ)"


def test_company_books_gate_single_vs_multi(session, company):
    # Một sổ: mọi book null → gate tắt.
    add_nvl(session, company.id, material_code="M1", year=2025)
    session.commit()
    assert company_books(session, company.id, 2025) == []
    assert not is_multi_book(session, company.id, 2025)

    # Thêm 2 sổ khác nhau trên balances/norms.
    add_nvl(session, company.id, material_code="M2", book="EPE", year=2025)
    add_sp(session, company.id, product_code="P1", book="GC", year=2025)
    session.commit()
    assert company_books(session, company.id, 2025) == ["EPE", "GC"]
    assert is_multi_book(session, company.id, 2025)


def test_company_books_from_norms_too(session, company):
    session.add(Norm(
        company_id=company.id, period_year=2025, book="GC",
        product_code="P1", material_code="M1", norm_qty=1.0,
    ))
    add_nvl(session, company.id, material_code="M1", book="EPE", year=2025)
    session.commit()
    assert company_books(session, company.id, 2025) == ["EPE", "GC"]


def test_company_books_year_scoped(session, company):
    add_nvl(session, company.id, material_code="M1", book="EPE", year=2024)
    add_nvl(session, company.id, material_code="M2", book="GC", year=2024)
    add_nvl(session, company.id, material_code="M3", book="EPE", year=2025)
    session.commit()
    assert company_books(session, company.id, 2024) == ["EPE", "GC"]
    assert company_books(session, company.id, 2025) == ["EPE"]   # chỉ 1 sổ ở 2025
    assert not is_multi_book(session, company.id, 2025)


def test_book_summary_none_when_single_book(session, company):
    add_nvl(session, company.id, material_code="M1", year=2025)
    session.commit()
    assert book_summary(session, company.id, 2025) is None


def test_book_summary_counts_codes_findings_and_chung(session, company):
    # EPE: 2 mã NVL, 2 phát hiện. GC: 1 mã NVL, 0 phát hiện (sổ sạch). Chung: 3.
    add_nvl(session, company.id, material_code="A", book="EPE", year=2025)
    add_nvl(session, company.id, material_code="B", book="EPE", year=2025)
    add_nvl(session, company.id, material_code="C", book="GC", year=2025)
    for i in range(2):
        session.add(Finding(
            company_id=company.id, period_year=2025, check_code="C4.3",
            severity="warning", book="EPE", title=f"epe {i}",
        ))
    for i in range(3):
        session.add(Finding(
            company_id=company.id, period_year=2025, check_code="C1.1",
            severity="warning", book=None, title=f"chung {i}",
        ))
    # Combo book=NULL KHÔNG được đếm vào strip (đồng bộ severity_totals).
    session.add(Finding(
        company_id=company.id, period_year=2025, check_code="COMBO_X",
        severity="critical", book=None, title="combo",
    ))
    session.commit()

    summary = book_summary(session, company.id, 2025)
    assert summary is not None
    by_code = {c["code"]: c for c in summary["books"]}
    assert by_code["EPE"]["nvl_codes"] == 2
    assert by_code["EPE"]["findings"] == 2
    assert by_code["EPE"]["label"] == "Sổ EPE (chế xuất)"
    assert by_code["GC"]["nvl_codes"] == 1
    assert by_code["GC"]["findings"] == 0        # sổ sạch: đã đánh giá, không phải chưa chạy
    assert summary["chung"]["findings"] == 3     # combo không cộng vào


def _setup_db():
    import app.database as dbmod

    new_engine = dbmod.create_engine(
        "sqlite://", connect_args={"check_same_thread": False},
        poolclass=StaticPool, future=True,
    )
    new_session = dbmod.sessionmaker(bind=new_engine, autoflush=False, autocommit=False, future=True)
    dbmod.engine = new_engine
    dbmod.SessionLocal = new_session
    Base.metadata.create_all(new_engine)
    return new_engine, new_session


def _teardown(new_engine):
    new_engine.dispose()
    import app.database as dbmod
    dbmod.engine = engine
    dbmod.SessionLocal = SessionLocal


def _seed_multi_book(db, code="DN_2SO"):
    from app.auth_users import seed_default_admin

    seed_default_admin(db, "admin", "admin")
    c = Company(code=code, name="Pháp nhân 2 sổ", tax_id="0901051747")
    db.add(c)
    db.flush()
    db.add_all([
        NvlBalance(company_id=c.id, period_year=2025, book="EPE", material_code="A", unit="PCE"),
        NvlBalance(company_id=c.id, period_year=2025, book="EPE", material_code="B", unit="PCE"),
        NvlBalance(company_id=c.id, period_year=2025, book="GC", material_code="C", unit="PCE"),
    ])
    db.add_all([
        Finding(company_id=c.id, period_year=2025, check_code="C4.3",
                severity="warning", book="EPE", title="e"),
        Finding(company_id=c.id, period_year=2025, check_code="C1.1",
                severity="warning", book=None, title="c"),
    ])
    db.commit()
    return c


def test_strip_shown_for_multi_book_hidden_for_single():
    new_engine, new_session = _setup_db()
    try:
        with new_session() as db:
            _seed_multi_book(db, "DN_2SO")
            # Pháp nhân một sổ (mọi book null).
            single = Company(code="DN_1SO", name="Một sổ", tax_id="111")
            db.add(single)
            db.flush()
            db.add(NvlBalance(company_id=single.id, period_year=2025, material_code="Z", unit="PCE"))
            db.commit()

        client = TestClient(app)
        client.post("/login", data={"user": "admin", "password": "admin"}, follow_redirects=False)

        multi = client.get("/companies/DN_2SO?year=2025").text
        assert "Sổ EPE (chế xuất)" in multi
        assert "Sổ GC (gia công)" in multi
        assert "mã NVL" in multi
        assert "Chung (liên sổ)" in multi

        one = client.get("/companies/DN_1SO?year=2025").text
        assert "Sổ EPE" not in one       # single-book: không chrome theo sổ
        assert "mã NVL" not in one
    finally:
        _teardown(new_engine)
