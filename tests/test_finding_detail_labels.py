"""Trang chi tiết phát hiện: nhãn tiếng Việt, số có đơn vị, link về dữ liệu gốc.

Trang này từng in khoá JSON thô (`m15_import`) làm nhãn và tên bảng DB
(`declaration_lines`) làm tiêu đề khối chứng cứ.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.main import app
from app.models import Company, Finding, NvlBalance


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


def test_detail_keys_render_as_vietnamese_labels():
    _engine, new_session = _setup_db()
    page = _page(new_session)
    assert "Số M15 đối chiếu" in page or "M15 nhập" in page
    assert "Chênh lệch" in page
    assert "m15_import" not in page, "khoá thô lọt ra màn hình"
    assert "diff_pct" not in page


def test_percentages_carry_the_symbol():
    _engine, new_session = _setup_db()
    assert "+517,2 %" in _page(new_session)


def test_enum_values_are_translated():
    _engine, new_session = _setup_db()
    page = _page(new_session)
    assert "Gia công" in page
    assert "GIA_CONG" not in page


def test_evidence_block_names_the_form_not_the_db_table():
    _engine, new_session = _setup_db()
    page = _page(new_session)
    assert "Mẫu 15 — Cân đối NVL" in page
    assert "BCCT — Tờ khai chi tiết" in page
    assert "nvl_balances" not in page
    assert "declaration_lines" not in page


def test_evidence_filter_reads_as_a_sentence_not_json():
    _engine, new_session = _setup_db()
    page = _page(new_session)
    assert "Mã NVL: NVL-A" in page
    assert "Loại hình: E21, E23" in page
    assert "company_id" not in page, "khoá kỹ thuật không cần in ra"


def test_evidence_block_links_to_the_filtered_raw_data():
    _engine, new_session = _setup_db()
    page = _page(new_session)
    assert "table=m15&amp;q=NVL-A" in page
    assert "table=bcct" in page and "customs=E21%2CE23" in page


def test_a_finding_without_details_does_not_break_the_page():
    _engine, new_session = _setup_db()
    page = _page(new_session, details=None, evidence_refs=None)
    assert "Chứng cứ truy nguồn" in page
