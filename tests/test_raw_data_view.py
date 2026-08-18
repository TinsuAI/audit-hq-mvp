"""Màn dữ liệu gốc: bộ lọc + cột nguồn file + link sâu từ phát hiện.

Cán bộ đang phải mở Excel để kiểm số. Ba thứ khép vòng đó: lọc được đúng dòng
cần xem, biết dòng đó đến từ file nào, và đi thẳng từ phát hiện sang bảng đã lọc
sẵn thay vì gõ lại mã.
"""

from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

from app.main import app
from app.models import Company, DeclarationLine, Finding, NvlBalance
from tests.conftest import AppDb


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


def test_source_file_column_shows_the_file_name_not_the_server_path(app_db: AppDb):
    new_session = app_db.SessionLocal
    _seed(new_session)
    client = TestClient(app)
    _login(client)
    page = client.get("/companies/RAWCO/data?year=2024&table=m15").text
    assert "Bao cao quyet toan 2024.xlsx" in page
    assert "/srv/data" not in page, "đường dẫn máy chủ không có lý do gì phải in ra"


def test_filter_by_declaration_number(app_db: AppDb):
    new_session = app_db.SessionLocal
    _seed(new_session)
    client = TestClient(app)
    _login(client)
    page = client.get(
        "/companies/RAWCO/data?year=2024&table=bcct&decl_no=103000001"
    ).text
    assert "103000001" in page
    assert "103000002" not in page


def test_filter_by_customs_code_accepts_a_set(app_db: AppDb):
    """Link từ phát hiện truyền cả tập loại hình mà check đã cộng."""
    new_session = app_db.SessionLocal
    _seed(new_session)
    client = TestClient(app)
    _login(client)
    one = client.get("/companies/RAWCO/data?year=2024&table=bcct&customs=E31").text
    assert "103000001" in one and "103000002" not in one
    both = client.get("/companies/RAWCO/data?year=2024&table=bcct&customs=E31,E62").text
    assert "103000001" in both and "103000002" in both


def test_filter_by_date_range(app_db: AppDb):
    new_session = app_db.SessionLocal
    _seed(new_session)
    client = TestClient(app)
    _login(client)
    page = client.get(
        "/companies/RAWCO/data?year=2024&table=bcct"
        "&date_from=2024-01-01&date_to=2024-06-30"
    ).text
    assert "103000001" in page
    assert "103000002" not in page


def test_filter_by_book_applies_to_settlement_tables(app_db: AppDb):
    new_session = app_db.SessionLocal
    _seed(new_session)
    client = TestClient(app)
    _login(client)
    page = client.get("/companies/RAWCO/data?year=2024&table=m15&book=EPE").text
    assert "NVL-B" in page
    assert "NVL-A" not in page


def test_m16_filter_matches_both_the_product_code_and_the_material_code(app_db: AppDb):
    """Mẫu 16 là bảng CẶP — tra mã TP ở đây phải ra dòng, không ra bảng rỗng.

    C4.9 (thiếu định mức) trỏ sang chính bảng này bằng mã TP; lọc một cột thôi thì
    link đó mở ra bảng rỗng, đọc như "không có định mức nào" trong khi mã TP nằm ở
    cột bên cạnh.
    """
    from app.models import Norm

    new_session = app_db.SessionLocal
    _seed(new_session)
    with new_session() as s:
        cid = s.query(Company).filter_by(code="RAWCO").one().id
        s.add_all([
            Norm(company_id=cid, period_year=2024, product_code="TP-9",
                 material_code="NVL-A", norm_qty=2.0),
            Norm(company_id=cid, period_year=2024, product_code="TP-8",
                 material_code="NVL-Z", norm_qty=1.0),
        ])
        s.commit()
    client = TestClient(app)
    _login(client)

    by_product = client.get("/companies/RAWCO/data?year=2024&table=m16&q=TP-9").text
    assert "NVL-A" in by_product
    assert "NVL-Z" not in by_product

    by_material = client.get("/companies/RAWCO/data?year=2024&table=m16&q=NVL-Z").text
    assert "TP-8" in by_material
    assert "TP-9" not in by_material


def test_switching_table_tab_keeps_the_code_filter(app_db: AppDb):
    """Đổi tab mà mất bộ lọc thì cán bộ phải gõ lại mã — đúng thứ đang bực."""
    new_session = app_db.SessionLocal
    _seed(new_session)
    client = TestClient(app)
    _login(client)
    page = client.get("/companies/RAWCO/data?year=2024&table=m15&q=NVL-A").text
    assert "table=bcct&amp;q=NVL-A" in page or "table=bcct&q=NVL-A" in page


def test_numbers_follow_the_vietnamese_convention(app_db: AppDb):
    new_session = app_db.SessionLocal
    _seed(new_session)
    client = TestClient(app)
    _login(client)
    page = client.get("/companies/RAWCO/data?year=2024&table=m15").text
    assert "1.234,50" in page


def test_unit_price_keeps_four_decimals(app_db: AppDb):
    new_session = app_db.SessionLocal
    _seed(new_session)
    client = TestClient(app)
    _login(client)
    page = client.get("/companies/RAWCO/data?year=2024&table=bcct").text
    assert "0,0125" in page, "đơn giá cắt còn 2 chữ số là mất giá trị thật"


def test_raw_data_link_points_at_the_table_the_check_actually_read(app_db: AppDb):
    """C1.2 có mã NVL nhưng bằng chứng ở tờ khai — link phải sang BCCT, không M15."""
    from app.routes.companies import raw_data_url

    new_session = app_db.SessionLocal
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


def test_raw_data_link_has_no_book_param_for_declarations(app_db: AppDb):
    """`declaration_lines` không có cột `book` — truyền vào là lọc rỗng."""
    from app.routes.companies import raw_data_url

    new_session = app_db.SessionLocal
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


def test_raw_data_link_carries_the_book_for_settlement_tables(app_db: AppDb):
    from app.routes.companies import raw_data_url

    new_session = app_db.SessionLocal
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


def test_raw_data_link_is_none_when_the_table_is_unknown(app_db: AppDb):
    """Phát hiện tổ hợp trỏ vào bảng `findings` — không có dữ liệu gốc để mở."""
    from app.routes.companies import raw_data_url

    new_session = app_db.SessionLocal
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


def test_finding_row_offers_the_raw_data_link(app_db: AppDb):
    new_session = app_db.SessionLocal
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
