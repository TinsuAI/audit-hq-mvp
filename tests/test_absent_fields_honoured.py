"""Lời khai "không có trong file" phải được TÔN TRỌNG tới tận dòng Tầng 1.

Ba lỗi trung thực do audit Rams 2026-08-08 phát hiện (nguyên tắc #6 chấm 0):

A. Cán bộ khai vắng → cổng check trả "chưa đánh giá được", NHƯNG adapter vẫn đọc cột
   mặc định và ghi giá trị vào dòng Tầng 1. Màn dữ liệu gốc hiện số của đúng cột mà
   hệ thống bảo là không có — hai màn nói ngược nhau.
B. Gửi biểu mẫu từ file không dựng ô đó → lời khai đã lưu bị XOÁ, không báo gì.
C. Chọn "— chưa gán —" cho trường máy đã đặt → lượt parse sau gán lại cột mặc định
   và giao diện quay về "Đã gán", cũng không báo gì.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from openpyxl import Workbook

from app.adapters.m16 import parse_m16
from app.models import Company, DataFile, DataFileStatus
from app.pipeline.saved_map import apply_absent_fields, load_column_map, save_column_map


def _m16(path: Path) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = "BCTT39"
    for _ in range(10):
        ws.append([None] * 9)
    ws.append([None, "Mã sản phẩm", "Tên sản phẩm", "ĐVT SP", "Mã nguyên liệu",
               "Tên nguyên liệu", "ĐVT NVL", "Lượng NL, VT thực tế sử dụng", "Ghi chú"])
    for i in range(3):
        ws.append([i + 1, "SP1" if i == 0 else None, "TP" if i == 0 else None,
                   "PCE" if i == 0 else None, f"MAT{i}", "NPL", "KG", 1.5, "x"])
    path.parent.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    wb.save(buf)
    path.write_bytes(buf.getvalue())
    return path


# --- A. Lời khai vắng phải tới tận dòng Tầng 1 -------------------------------


def test_absent_field_is_not_read_into_tier_one(tmp_path):
    parsed = parse_m16(_m16(tmp_path / "dm.xlsx"), sheet="BCTT39")
    sig = parsed.provenance.detail["form_signature"]
    assert parsed.rows[0].note == "x", "tiền đề: chưa khai vắng thì vẫn đọc"
    assert "note" in parsed.provenance.detail["column_map"]

    apply_absent_fields(parsed, "m16", {sig: ["note"]})

    # Không còn giá trị nào của cột đó đi vào dòng Tầng 1.
    assert all(r.note is None for r in parsed.rows)
    # Và màn gán cột không còn coi nó là cột đang đọc.
    assert "note" not in parsed.provenance.detail["column_map"]
    assert "note" not in parsed.provenance.evidence


def test_absent_statement_for_another_signature_is_ignored(tmp_path):
    """Map lưu theo vân tay — lời khai của bố cục KHÁC không được áp nhầm."""
    parsed = parse_m16(_m16(tmp_path / "dm.xlsx"), sheet="BCTT39")
    apply_absent_fields(parsed, "m16", {"vân-tay-khác": ["note"]})
    assert parsed.rows[0].note == "x"


def test_row_key_is_never_dropped_even_if_a_stale_map_says_absent(tmp_path):
    """Thiếu khoá dòng thì không dựng được dòng nào. Đường xác nhận đã từ chối biểu
    mẫu như vậy; map cũ còn sót thì BỎ QUA, không được làm hỏng lượt parse."""
    parsed = parse_m16(_m16(tmp_path / "dm.xlsx"), sheet="BCTT39")
    sig = parsed.provenance.detail["form_signature"]
    apply_absent_fields(parsed, "m16", {sig: ["material_code", "norm_qty", "note"]})

    assert parsed.rows[0].material_code == "MAT0"
    assert parsed.rows[0].norm_qty == 1.5
    assert "material_code" in parsed.provenance.detail["column_map"]
    assert parsed.rows[0].note is None       # trường không phải khoá dòng vẫn bị gỡ


def test_no_absent_statement_changes_nothing(tmp_path):
    parsed = parse_m16(_m16(tmp_path / "dm.xlsx"), sheet="BCTT39")
    before = dict(parsed.provenance.detail["column_map"])
    apply_absent_fields(parsed, "m16", None)
    assert parsed.provenance.detail["column_map"] == before
    assert parsed.rows[0].note == "x"


# --- B. Không được xoá âm thầm lời khai đã lưu -------------------------------


def _company(db) -> Company:
    c = db.query(Company).first()
    if c is None:
        c = Company(code="DN_HON", name="Hon")
        db.add(c)
        db.commit()
    return c


def test_saving_without_an_absent_statement_keeps_the_stored_one(app_db):
    """`absent_fields=None` nghĩa là "biểu mẫu này không hỏi về trường vắng" —
    KHÔNG phải "cán bộ vừa bỏ hết". Ghi đè thành rỗng là mất dữ liệu im lặng."""
    db = app_db.SessionLocal()
    company = _company(db)
    save_column_map(db, company.id, "m16", "sig", {"material_code": 4},
                    absent_fields=["note"])
    db.commit()

    # Lượt lưu sau đến từ trang không dựng ô "không có trong file".
    save_column_map(db, company.id, "m16", "sig", {"material_code": 4})
    db.commit()

    assert load_column_map(db, company.id, "m16", "sig").absent_fields_obj == ["note"]


def test_an_explicit_empty_statement_does_clear_it(app_db):
    """Bỏ tick thật thì phải xoá thật — phân biệt bằng `[]` với `None`."""
    db = app_db.SessionLocal()
    company = _company(db)
    save_column_map(db, company.id, "m16", "sig2", {"material_code": 4},
                    absent_fields=["note"])
    db.commit()
    save_column_map(db, company.id, "m16", "sig2", {"material_code": 4},
                    absent_fields=[])
    db.commit()
    assert load_column_map(db, company.id, "m16", "sig2").absent_fields_obj == []


# --- C. "— chưa gán —" không được im lặng gán lại ----------------------------

_REL = "DN_HON/2025/DINH_MUC"


@pytest.fixture
def env(app_db, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app
    from app.settings import settings
    monkeypatch.setattr(settings, "preview_cache_path", tmp_path / "kho", raising=False)
    (app_db.raw_root / _REL).mkdir(parents=True, exist_ok=True)
    with app_db.SessionLocal() as db:
        db.add(Company(code="DN_HON", name="Hon", tax_id="1"))
        db.commit()
    client = TestClient(app)
    client.post("/login", data={"user": "admin", "password": "admin"}, follow_redirects=False)
    return client, app_db.raw_root


def _register(app_db, detail: dict) -> tuple[int, str]:
    rel = f"{_REL}/dm.xlsx"
    _m16(app_db.raw_root / rel)
    with app_db.SessionLocal() as db:
        c = db.query(Company).filter_by(code="DN_HON").one()
        row = DataFile(
            company_id=c.id, period_year=2025, slot="m16",
            original_filename="dm.xlsx", stored_path=rel,
            size_bytes=(app_db.raw_root / rel).stat().st_size,
            parse_status=DataFileStatus.OK, row_count=3,
            parse_detail=json.dumps(detail, ensure_ascii=False),
        )
        db.add(row)
        db.commit()
        return row.id, c.slug or c.code


_DETAIL = {
    "sheet": "BCTT39", "form_signature": "sig-c",
    "column_map": {"product_code": 1, "material_code": 4, "norm_qty": 7, "note": 8},
    "column_choices": [{"index": i, "header": f"c{i}", "samples": ["x"]} for i in range(9)],
}


def test_blank_never_silently_unassigns_a_column(env, app_db):
    """Ô trống = "giữ nguyên". Muốn thôi đọc một cột thì tick "Không có trong file" —
    đường đó bền vững và tới được Tầng 1. Trước bản vá, ô trống gỡ cột khỏi map rồi
    lượt parse sau gán lại cột mặc định, giao diện hiện "Đã gán", không báo gì."""
    client, _ = env
    fid, slug = _register(app_db, _DETAIL)
    client.post(
        f"/companies/{slug}/documents/file/{fid}",
        data={"_field_major": "1", "col_product_code": "1", "col_material_code": "4",
              "col_norm_qty": "7", "col_note": ""},
        follow_redirects=False,
    )
    with app_db.SessionLocal() as db:
        c = db.query(Company).filter_by(code="DN_HON").one()
        saved = load_column_map(db, c.id, "m16", "sig-c")
    assert saved.column_map_obj.get("note") == 8, "ô trống không được gỡ cột"
    assert saved.absent_fields_obj == []


def test_the_screen_does_not_offer_an_option_that_would_be_reverted(env, app_db):
    """Trường ĐÃ gán thì không được mời chọn "— chưa gán —": chọn xong nó quay lại
    ngay lượt sau. Trường CHƯA gán thì mục đó là trạng thái thật, giữ."""
    client, _ = env
    fid, slug = _register(app_db, _DETAIL)
    html = client.get(f"/companies/{slug}/documents/file/{fid}").text
    block = html.split('name="col_note"')[1].split("</select>")[0]
    assert "— chưa gán —" not in block, "note đã gán mà vẫn mời bỏ gán"

    detail = dict(_DETAIL, column_map={"product_code": 1, "material_code": 4, "norm_qty": 7})
    fid2, _ = _register(app_db, detail)
    html2 = client.get(f"/companies/{slug}/documents/file/{fid2}").text
    block2 = html2.split('name="col_note"')[1].split("</select>")[0]
    assert "— chưa gán —" in block2, "note chưa gán thì phải nêu đúng trạng thái đó"
