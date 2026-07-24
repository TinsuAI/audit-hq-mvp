"""Badge truy nguồn cách đọc file (ADR #15) hiện ở trang Dữ liệu gốc.

Không "hộp đen": file lệch bố cục chuẩn phải nói rõ đọc bằng đẳng thức nào, cột xuất
khẩu / định mức chọn theo nhãn gì.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import Company, DataFile, Norm, SpBalance


def _setup():
    import app.database as dbmod
    from app.auth_users import seed_default_admin

    eng = dbmod.create_engine(
        "sqlite://", connect_args={"check_same_thread": False},
        poolclass=StaticPool, future=True,
    )
    ses = dbmod.sessionmaker(bind=eng, autoflush=False, autocommit=False, future=True)
    dbmod.engine, dbmod.SessionLocal = eng, ses
    Base.metadata.create_all(eng)
    with ses() as db:
        seed_default_admin(db, "admin", "admin")
        c = Company(code="DN_PROV", tax_id="1", name="DN bố cục lạ")
        db.add(c)
        db.flush()
        db.add(SpBalance(company_id=c.id, period_year=2025, product_code="SP1", export_qty=100.0))
        db.add(Norm(company_id=c.id, period_year=2025, product_code="SP1",
                    material_code="M1", norm_qty=1.5))
        db.add(DataFile(
            company_id=c.id, period_year=2025, slot="m15a",
            original_filename="TP.xlsx", stored_path="x/TP.xlsx", size_bytes=1,
            parse_status="ok", row_count=1, parse_layout="extended",
            parse_detail=json.dumps({
                "formula": "(11)=(5)+(6)+(7)-(8)-(9)-(10)", "matched": 43, "checked": 43,
                "match_rate": 1.0, "export_col": 10,
                "export_label": "lượng sp đăng ký tờ khai và xuất kho năm nay\nexport this year",
            }, ensure_ascii=False),
        ))
        db.add(DataFile(
            company_id=c.id, period_year=2025, slot="m16",
            original_filename="DM.xlsx", stored_path="x/DM.xlsx", size_bytes=1,
            parse_status="ok", row_count=1, parse_layout="labeled",
            parse_detail=json.dumps({
                "norm_col": 8, "technical_col": 7,
                "norm_label": "lượng nl, vt thực tế sử dụng\nactual bom",
            }, ensure_ascii=False),
        ))
        db.commit()
    return eng


def _teardown(eng):
    eng.dispose()
    import app.database as dbmod
    dbmod.engine, dbmod.SessionLocal = engine, SessionLocal


def test_extended_layout_note_shown_on_data_page():
    eng = _setup()
    try:
        with TestClient(app) as client:
            client.post("/login", data={"user": "admin", "password": "admin"},
                        follow_redirects=False)
            html = client.get("/companies/DN_PROV/data?year=2025&table=m15a").text
            assert "Bố cục mở rộng" in html
            assert "(11)=(5)+(6)+(7)-(8)-(9)-(10)" in html
            assert "43/43" in html
            # nhãn export xuống dòng phải được làm phẳng, không vỡ HTML
            assert "export this year" in html
            assert "\n" not in "lượng sp đăng ký tờ khai và xuất kho năm nay export this year"
    finally:
        _teardown(eng)


def test_labeled_norm_note_shown_on_data_page():
    eng = _setup()
    try:
        with TestClient(app) as client:
            client.post("/login", data={"user": "admin", "password": "admin"},
                        follow_redirects=False)
            html = client.get("/companies/DN_PROV/data?year=2025&table=m16").text
            assert "Chọn cột theo nhãn" in html
            assert "thực tế" in html
            assert "cột 8" in html
    finally:
        _teardown(eng)
