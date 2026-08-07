"""Trang chi tiết phát hiện: nhãn tiếng Việt, số có đơn vị, link về dữ liệu gốc.

Trang này từng in khoá JSON thô (`m15_import`) làm nhãn và tên bảng DB
(`declaration_lines`) làm tiêu đề khối chứng cứ.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.models import Company, Finding, NvlBalance
from app.models.data_file import SLOT_LABEL_VI
from tests.conftest import AppDb


def _login(client: TestClient) -> None:
    r = client.post(
        "/login", data={"user": "admin", "password": "admin"}, follow_redirects=False
    )
    assert r.status_code == 303


def _seed_finding(new_session, **overrides) -> int:
    with new_session() as s:
        c = s.scalar(Company.__table__.select().limit(1).with_only_columns(Company.id))
        if c is None:
            company = Company(code="FDCO", tax_id="1", name="FD Co")
            s.add(company)
            s.flush()
            s.add(NvlBalance(
                company_id=company.id, period_year=2024, material_code="NVL-A",
                unit="KG", import_qty=1234.5, closing_qty=1234.5,
            ))
            c = company.id
        payload = {
            "company_id": c, "period_year": 2024, "check_code": "C1.1",
            "severity": "critical", "subject_type": "material_code",
            "subject_key": "NVL-A", "title": "Lệch nhập NVL NVL-A",
            "details": {
                "company_type": "GIA_CONG", "m15_import": 1234.5,
                "bcct_sum": 200.0, "diff_pct": 517.25, "unit": "KG",
                "import_codes": ["E21", "E23"],
            },
            "evidence_refs": [{
                "table": "nvl_balances",
                "filter": {"company_id": c, "period_year": 2024, "material_code": "NVL-A"},
            }, {
                "table": "declaration_lines",
                "filter": {
                    "company_id": c, "period_year": 2024, "item_code": "NVL-A",
                    "customs_code__in": ["E21", "E23"],
                },
            }],
        }
        payload.update(overrides)
        f = Finding(**payload)
        s.add(f)
        s.commit()
        return f.id


def _page(new_session, **overrides) -> str:
    fid = _seed_finding(new_session, **overrides)
    client = TestClient(app)
    _login(client)
    return client.get(f"/findings/{fid}").text


def test_detail_keys_render_as_vietnamese_labels(app_db: AppDb):
    page = _page(app_db.SessionLocal)
    assert "Số M15 đối chiếu" in page or "M15 nhập" in page
    assert "Chênh lệch" in page
    assert "m15_import" not in page, "khoá thô lọt ra màn hình"
    assert "diff_pct" not in page


def test_percentages_carry_the_symbol(app_db: AppDb):
    assert "+517,2 %" in _page(app_db.SessionLocal)


def test_enum_values_are_translated(app_db: AppDb):
    page = _page(app_db.SessionLocal)
    assert "Gia công" in page
    assert "GIA_CONG" not in page


def test_evidence_block_names_the_form_not_the_db_table(app_db: AppDb):
    page = _page(app_db.SessionLocal)
    # Tên loại tài liệu lấy từ bảng nhãn duy nhất (#98), không gõ lại ở test.
    assert SLOT_LABEL_VI["m15"] in page
    assert SLOT_LABEL_VI["bcct"] in page
    assert "nvl_balances" not in page
    assert "declaration_lines" not in page


def test_evidence_filter_reads_as_a_sentence_not_json(app_db: AppDb):
    page = _page(app_db.SessionLocal)
    assert "Mã NVL: NVL-A" in page
    assert "Loại hình: E21, E23" in page
    assert "company_id" not in page, "khoá kỹ thuật không cần in ra"


def test_evidence_block_links_to_the_filtered_raw_data(app_db: AppDb):
    page = _page(app_db.SessionLocal)
    assert "table=m15&amp;q=NVL-A" in page
    assert "table=bcct" in page and "customs=E21%2CE23" in page


def test_a_finding_without_details_does_not_break_the_page(app_db: AppDb):
    page = _page(app_db.SessionLocal, details=None, evidence_refs=None)
    assert "Chứng cứ truy nguồn" in page
