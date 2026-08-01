"""Màn dữ liệu gốc: bộ lọc + cột nguồn file + link sâu từ phát hiện.

Cán bộ đang phải mở Excel để kiểm số. Ba thứ khép vòng đó: lọc được đúng dòng
cần xem, biết dòng đó đến từ file nào, và đi thẳng từ phát hiện sang bảng đã lọc
sẵn thay vì gõ lại mã.
"""

from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.main import app
from app.models import Company, DeclarationLine, Finding, NvlBalance


def _setup_db():
    import app.database as dbmod
    from app.app_settings import invalidate_cache
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


def _seed(new_session):
    with new_session() as s:
        c = Company(code="RAWCO", tax_id="1", name="Raw Co")
        s.add(c)
        s.flush()
        s.add_all([
            NvlBalance(
                company_id=c.id, period_year=2024, material_code="NVL-A", unit="KG",
                opening_qty=0, import_qty=1234.5, closing_qty=1234.5,
                source_file="/srv/data/PILOT/2024/BCQT/Bao cao quyet toan 2024.xlsx",
            ),
            NvlBalance(
                company_id=c.id, period_year=2024, material_code="NVL-B", unit="KG",
                book="EPE", import_qty=10, closing_qty=10,
                source_file="/srv/data/PILOT/2024/BCQT/So EPE.xlsx",
            ),
            DeclarationLine(
                company_id=c.id, period_year=2024, declaration_no="103000001",
                declaration_date=date(2024, 3, 12), customs_code="E31",
                item_code="NVL-A", hs_code="39269099", quantity=120, unit="KG",
                unit_price=0.0125, currency="USD", value_total=1250000,
                source_file="/srv/data/PILOT/2024/HANG_CHI_TIET/BaoCaoToKhai.xls",
            ),
            DeclarationLine(
                company_id=c.id, period_year=2024, declaration_no="103000002",
                declaration_date=date(2024, 9, 30), customs_code="E62",
                item_code="NVL-A", hs_code="39269099", quantity=80, unit="KG",
                source_file="/srv/data/PILOT/2024/HANG_CHI_TIET/BaoCaoToKhai.xls",
            ),
        ])
        s.commit()
        return c.id


def test_source_file_column_shows_the_file_name_not_the_server_path():
    _engine, new_session = _setup_db()
    _seed(new_session)
    client = TestClient(app)
    _login(client)
    page = client.get("/companies/RAWCO/data?year=2024&table=m15").text
    assert "Bao cao quyet toan 2024.xlsx" in page
    assert "/srv/data" not in page, "đường dẫn máy chủ không có lý do gì phải in ra"


def test_filter_by_declaration_number():
    _engine, new_session = _setup_db()
    _seed(new_session)
    client = TestClient(app)
    _login(client)
    page = client.get(
        "/companies/RAWCO/data?year=2024&table=bcct&decl_no=103000001"
    ).text
    assert "103000001" in page
    assert "103000002" not in page


def test_filter_by_customs_code_accepts_a_set():
    """Link từ phát hiện truyền cả tập loại hình mà check đã cộng."""
    _engine, new_session = _setup_db()
    _seed(new_session)
    client = TestClient(app)
    _login(client)
    one = client.get("/companies/RAWCO/data?year=2024&table=bcct&customs=E31").text
    assert "103000001" in one and "103000002" not in one
    both = client.get("/companies/RAWCO/data?year=2024&table=bcct&customs=E31,E62").text
    assert "103000001" in both and "103000002" in both


def test_filter_by_date_range():
    _engine, new_session = _setup_db()
    _seed(new_session)
    client = TestClient(app)
    _login(client)
    page = client.get(
        "/companies/RAWCO/data?year=2024&table=bcct"
        "&date_from=2024-01-01&date_to=2024-06-30"
    ).text
    assert "103000001" in page
    assert "103000002" not in page


def test_filter_by_book_applies_to_settlement_tables():
    _engine, new_session = _setup_db()
    _seed(new_session)
    client = TestClient(app)
    _login(client)
    page = client.get("/companies/RAWCO/data?year=2024&table=m15&book=EPE").text
    assert "NVL-B" in page
    assert "NVL-A" not in page


def test_switching_table_tab_keeps_the_code_filter():
    """Đổi tab mà mất bộ lọc thì cán bộ phải gõ lại mã — đúng thứ đang bực."""
    _engine, new_session = _setup_db()
    _seed(new_session)
    client = TestClient(app)
    _login(client)
    page = client.get("/companies/RAWCO/data?year=2024&table=m15&q=NVL-A").text
    assert "table=bcct&amp;q=NVL-A" in page or "table=bcct&q=NVL-A" in page


def test_numbers_follow_the_vietnamese_convention():
    _engine, new_session = _setup_db()
    _seed(new_session)
    client = TestClient(app)
    _login(client)
    page = client.get("/companies/RAWCO/data?year=2024&table=m15").text
    assert "1.234,50" in page


def test_unit_price_keeps_four_decimals():
    _engine, new_session = _setup_db()
    _seed(new_session)
    client = TestClient(app)
    _login(client)
    page = client.get("/companies/RAWCO/data?year=2024&table=bcct").text
    assert "0,0125" in page, "đơn giá cắt còn 2 chữ số là mất giá trị thật"


def test_raw_data_link_points_at_the_table_the_check_actually_read():
    """C1.2 có mã NVL nhưng bằng chứng ở tờ khai — link phải sang BCCT, không M15."""
    from app.routes.companies import raw_data_url

    _engine, new_session = _setup_db()
    cid = _seed(new_session)
    with new_session() as s:
        company = s.get(Company, cid)
        f = Finding(
            company_id=cid, period_year=2024, check_code="C1.2", severity="critical",
            subject_type="material_code", subject_key="NVL-A", title="x",
            details={"import_codes": ["E31", "E62"]},
            evidence_refs=[{"table": "declaration_lines", "filter": {"item_code": "NVL-A"}}],
        )
        url = raw_data_url(company, 2024, f)
    assert "table=bcct" in url
    assert "q=NVL-A" in url
    assert "customs=E31%2CE62" in url


def test_raw_data_link_has_no_book_param_for_declarations():
    """`declaration_lines` không có cột `book` — truyền vào là lọc rỗng."""
    from app.routes.companies import raw_data_url

    _engine, new_session = _setup_db()
    cid = _seed(new_session)
    with new_session() as s:
        company = s.get(Company, cid)
        f = Finding(
            company_id=cid, period_year=2024, check_code="C1.2", severity="critical",
            subject_key="NVL-A", book="EPE", title="x",
            evidence_refs=[{"table": "declaration_lines", "filter": {}}],
        )
        url = raw_data_url(company, 2024, f)
    assert "book=" not in url


def test_raw_data_link_carries_the_book_for_settlement_tables():
    from app.routes.companies import raw_data_url

    _engine, new_session = _setup_db()
    cid = _seed(new_session)
    with new_session() as s:
        company = s.get(Company, cid)
        f = Finding(
            company_id=cid, period_year=2024, check_code="C2.1", severity="critical",
            subject_key="NVL-B", book="EPE", title="x",
            evidence_refs=[{"table": "nvl_balances", "filter": {}}],
        )
        url = raw_data_url(company, 2024, f)
    assert "table=m15" in url and "book=EPE" in url


def test_raw_data_link_is_none_when_the_table_is_unknown():
    """Phát hiện tổ hợp trỏ vào bảng `findings` — không có dữ liệu gốc để mở."""
    from app.routes.companies import raw_data_url

    _engine, new_session = _setup_db()
    cid = _seed(new_session)
    with new_session() as s:
        company = s.get(Company, cid)
        combo = Finding(
            company_id=cid, period_year=2024, check_code="COMBO_HS_GAMING",
            severity="critical", subject_key="NVL-A", title="x",
            evidence_refs=[{"table": "findings", "filter": {"id": 1}}],
        )
        no_subject = Finding(
            company_id=cid, period_year=2024, check_code="C2.1", severity="critical",
            subject_key=None, title="x",
            evidence_refs=[{"table": "nvl_balances", "filter": {}}],
        )
        assert raw_data_url(company, 2024, combo) is None
        assert raw_data_url(company, 2024, no_subject) is None


def test_finding_row_offers_the_raw_data_link():
    _engine, new_session = _setup_db()
    cid = _seed(new_session)
    with new_session() as s:
        s.add(Finding(
            company_id=cid, period_year=2024, check_code="C1.1", severity="critical",
            subject_type="material_code", subject_key="NVL-A", title="x",
            details={"m15_import": 1234.5, "bcct_sum": 200.0, "diff_pct": 517.2},
            evidence_refs=[{"table": "nvl_balances", "filter": {}}],
        ))
        s.commit()
    client = TestClient(app)
    _login(client)
    page = client.get("/companies/RAWCO?year=2024").text
    assert "Dữ liệu gốc →" in page
    assert "table=m15" in page
