"""2SỔ-3 (#21) — lọc theo sổ: segmented control + empty-state sổ sạch.

View-filter thuần: chỉ thu hẹp danh sách finding (đếm + dòng). `book=chung` →
Finding.book IS NULL. Điểm năm · strip · export · run GIỮ toàn pháp nhân. Lọc trúng
sổ sạch (0 finding, có mã NVL) → empty-state riêng. Xem ADR #19 Revision — UI + upload.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import Company, CompanyYearScore, Finding, NvlBalance


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


def _seed(db, code="DN_F"):
    """EPE: 2 mã NVL, 2 finding. GC: 1 mã NVL, 0 finding (sổ sạch). Chung: 1 finding."""
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
                severity="warning", book="EPE", subject_key="A", title="epe_finding_1"),
        Finding(company_id=c.id, period_year=2025, check_code="C4.3",
                severity="warning", book="EPE", subject_key="B", title="epe_finding_2"),
        Finding(company_id=c.id, period_year=2025, check_code="C1.1",
                severity="critical", book=None, subject_key="X", title="chung_finding_1"),
    ])
    db.add(CompanyYearScore(company_id=c.id, period_year=2025, score=42, tier="Cần rà soát", breakdown={}))
    db.commit()
    return c


def test_filter_epe_shows_only_epe():
    new_engine, new_session = _setup_db()
    try:
        with new_session() as db:
            _seed(db, "DN_F")
        client = TestClient(app)
        _login(client)
        html = client.get("/companies/DN_F?year=2025&book=EPE").text
        assert "epe_finding_1" in html
        assert "chung_finding_1" not in html      # Chung KHÔNG bị kéo vào sổ EPE
        # Segmented control có, "Sổ EPE" active.
        assert "book-filter" in html
        assert 'book=EPE" class="active"' in html
    finally:
        _teardown(new_engine)


def test_filter_chung_is_book_null():
    new_engine, new_session = _setup_db()
    try:
        with new_session() as db:
            _seed(db, "DN_F")
        client = TestClient(app)
        _login(client)
        html = client.get("/companies/DN_F?year=2025&book=chung").text
        assert "chung_finding_1" in html
        assert "epe_finding_1" not in html
    finally:
        _teardown(new_engine)


def test_filter_clean_book_empty_state():
    new_engine, new_session = _setup_db()
    try:
        with new_session() as db:
            _seed(db, "DN_F")
        client = TestClient(app)
        _login(client)
        html = client.get("/companies/DN_F?year=2025&book=GC").text
        # Sổ sạch: empty-state "đã được đánh giá — 0 phát hiện trên N mã NVL".
        assert "đã được đánh giá" in html
        assert "0 phát hiện" in html
        assert "1 mã NVL" in html
        # KHÁC state no-data / not-run (score card vẫn full-entity → không "Chưa chạy").
        assert "không có phát hiện nào" not in html
        assert "Chưa chạy kiểm tra" not in html
    finally:
        _teardown(new_engine)


def test_score_and_strip_unchanged_by_filter():
    new_engine, new_session = _setup_db()
    try:
        with new_session() as db:
            _seed(db, "DN_F")
        client = TestClient(app)
        _login(client)
        # Điểm năm (42) hiện ở MỌI bộ lọc — book là lăng kính, không đổi chủ thể.
        for q in ("", "&book=EPE", "&book=GC", "&book=chung"):
            html = client.get(f"/companies/DN_F?year=2025{q}").text
            assert "42" in html                       # điểm năm full-entity
            assert "Sổ GC (gia công)" in html         # strip full-entity (kể cả lọc EPE)
            assert "Sổ EPE (chế xuất)" in html
    finally:
        _teardown(new_engine)


def test_compose_with_check_focus():
    new_engine, new_session = _setup_db()
    try:
        with new_session() as db:
            _seed(db, "DN_F")
        client = TestClient(app)
        _login(client)
        html = client.get("/companies/DN_F?year=2025&book=EPE&check=C4.3").text
        assert "epe_finding_1" in html
        assert "epe_finding_2" in html
        assert "chung_finding_1" not in html
    finally:
        _teardown(new_engine)


def test_invalid_book_treated_as_all():
    new_engine, new_session = _setup_db()
    try:
        with new_session() as db:
            _seed(db, "DN_F")
        client = TestClient(app)
        _login(client)
        html = client.get("/companies/DN_F?year=2025&book=ZZZ").text
        assert "epe_finding_1" in html
        assert "chung_finding_1" in html              # mã lạ → coi như tất cả
        assert 'class="active">Tất cả' in html
    finally:
        _teardown(new_engine)


def test_clean_book_empty_state_not_run_does_not_claim_evaluated():
    """Pháp nhân nhiều sổ ĐÃ nạp nhưng CHƯA chạy kiểm tra → lọc sổ KHÔNG được báo
    'đã được đánh giá' (0 mã ≠ đánh giá-sạch khi chưa chạy). Xem ADR #19 (strip)."""
    new_engine, new_session = _setup_db()
    try:
        with new_session() as db:
            c = Company(code="DN_NR", name="Chưa chạy", tax_id="0901051747")
            db.add(c)
            db.flush()
            db.add_all([  # 2 sổ có mã NVL, KHÔNG finding, KHÔNG year_score → chưa chạy
                NvlBalance(company_id=c.id, period_year=2025, book="EPE", material_code="A", unit="PCE"),
                NvlBalance(company_id=c.id, period_year=2025, book="GC", material_code="C", unit="PCE"),
            ])
            db.commit()
        client = TestClient(app)
        _login(client)
        html = client.get("/companies/DN_NR?year=2025&book=GC").text
        assert "đã được đánh giá" not in html      # KHÔNG khẳng định đánh giá-sạch
        assert "chưa chạy kiểm tra" in html.lower()  # đúng trạng thái chưa chạy
    finally:
        _teardown(new_engine)


def test_single_book_no_segmented_control():
    new_engine, new_session = _setup_db()
    try:
        with new_session() as db:
            c = Company(code="DN_1", name="Một sổ", tax_id="111")
            db.add(c)
            db.flush()
            db.add(NvlBalance(company_id=c.id, period_year=2025, material_code="Z", unit="PCE"))
            db.add(Finding(company_id=c.id, period_year=2025, check_code="C4.3",
                           severity="warning", book=None, subject_key="Z", title="x"))
            db.commit()
        client = TestClient(app)
        _login(client)
        html = client.get("/companies/DN_1?year=2025").text
        assert "book-filter" not in html
    finally:
        _teardown(new_engine)
