"""Ba trạng thái gán + trường xác nhận vắng (#112, spec #116 story 5-6, 10-13).

Khẳng định ở hai seam có người gọi thật: hàm dựng màn (`file_read_basis`) và hàm ghi
map (`save_column_map`). Không khẳng định trên hình dạng dict nội bộ.
"""

from __future__ import annotations

import json

import pytest

from app.adapters.declared_fields import row_key_fields
from app.models import Company, DataFile, DataFileStatus
from app.pipeline.file_page import ABSENT, ASSIGNED, UNASSIGNED, file_read_basis
from app.pipeline.saved_map import load_column_map, save_column_map

_M16_DETAIL = {
    "sheet": "BCTT39",
    "form_signature": "sig-m16",
    # Bố cục DINHMUC: không có cột `note`, nên trường đó không có vị trí mặc định.
    "column_map": {
        "product_code": 1, "product_name": 3, "material_code": 4,
        "material_name": 5, "material_unit": 6, "norm_qty": 7,
    },
    "columns": [
        {"field": "material_code", "label": "Mã NVL",
         "evidence": "header-matched", "review": "verified"},
    ],
}


def _file_row(**kw) -> DataFile:
    row = DataFile(
        company_id=1, period_year=2025, slot="m16",
        original_filename="dm.xlsx", stored_path="X/2025/DINH_MUC/dm.xlsx",
        size_bytes=1, parse_status=DataFileStatus.OK,
    )
    for k, v in kw.items():
        setattr(row, k, v)
    return row


def test_a_field_with_no_default_position_arrives_unassigned():
    """Bố cục DINHMUC không có cột `note` → trường tới màn ở trạng thái *chưa gán*.
    Không bịa vị trí, và cũng không biến mất khỏi màn."""
    basis = file_read_basis(_file_row(parse_detail=json.dumps(_M16_DETAIL)))
    by_field = {c.field: c for c in basis.columns}
    assert by_field["note"].state == UNASSIGNED
    assert by_field["note"].columns == ()
    assert by_field["material_code"].state == ASSIGNED


def test_officer_confirmation_moves_the_field_to_absent():
    basis = file_read_basis(
        _file_row(parse_detail=json.dumps(_M16_DETAIL)),
        absent_fields=["note"],
    )
    by_field = {c.field: c for c in basis.columns}
    assert by_field["note"].state == ABSENT
    assert by_field["note"].is_absent is True
    # Cán bộ đã kết luận → không còn là việc phải soát.
    assert by_field["note"].needs_review is False


def test_every_declared_field_gets_a_row_even_when_the_machine_placed_none():
    """File máy đặt được 0 trường vẫn gán được tay — không còn biểu mẫu rỗng (#95)."""
    detail = {"sheet": "BCTT39", "form_signature": "sig-x", "column_map": {}}
    basis = file_read_basis(_file_row(parse_detail=json.dumps(detail)))
    fields = {c.field for c in basis.columns}
    assert {"product_code", "material_code", "norm_qty", "note"} <= fields
    assert all(c.state == UNASSIGNED for c in basis.columns)


def test_missing_row_keys_and_missing_required_are_reported_separately():
    """Hai hậu quả khác nhau nên hai cảnh báo khác nhau (ADR #28)."""
    detail = {"sheet": "BCTT39", "form_signature": "sig-x", "column_map": {}}
    basis = file_read_basis(_file_row(parse_detail=json.dumps(detail)))
    assert "Mã SP" in basis.missing_row_keys
    assert "Định mức thực tế" in basis.missing_row_keys
    # ĐVT bắt buộc theo biểu nhưng KHÔNG phải khoá dòng → nhánh cảnh báo, không từ chối.
    assert "ĐVT SP" in basis.missing_required
    assert "ĐVT SP" not in basis.missing_row_keys


def test_column_choices_reach_the_screen():
    detail = dict(_M16_DETAIL, column_choices=[
        {"index": 4, "header": "Mã nguyên liệu", "samples": ["MAT1", "MAT2"]},
    ])
    basis = file_read_basis(_file_row(parse_detail=json.dumps(detail)))
    assert basis.has_choices is True
    assert basis.choices[0]["header"] == "Mã nguyên liệu"


def test_a_file_parsed_before_this_slice_has_no_choices():
    """Tiến lên, không backfill: file cũ không có ảnh chụp cột → màn rơi về ô nhập chỉ số."""
    basis = file_read_basis(_file_row(parse_detail=json.dumps(_M16_DETAIL)))
    assert basis.has_choices is False


# --- Bất biến hai tập rời nhau, khẳng định ở MỘT chỗ -------------------------


def _company(db) -> Company:
    c = db.query(Company).first()
    if c is None:
        c = Company(code="DN_T112", name="T112")
        db.add(c)
        db.commit()
    return c


def test_saving_a_field_as_both_mapped_and_absent_is_rejected(app_db):
    db = app_db.SessionLocal()
    company = _company(db)
    with pytest.raises(ValueError, match="chỉ ở đúng một trạng thái"):
        save_column_map(
            db, company.id, "m16", "sig-clash",
            {"note": 8}, absent_fields=["note"],
        )


def test_absent_fields_round_trip(app_db):
    db = app_db.SessionLocal()
    company = _company(db)
    save_column_map(
        db, company.id, "m16", "sig-rt",
        {"material_code": 4}, absent_fields=["note", "note"],
    )
    db.commit()
    saved = load_column_map(db, company.id, "m16", "sig-rt")
    assert saved.absent_fields_obj == ["note"]          # đã khử trùng lặp
    assert not (set(saved.absent_fields_obj) & set(saved.column_map_obj))


def test_rows_with_no_absent_statement_stay_exactly_as_they_were(app_db):
    """Hàng cũ (trước migration) = NULL: chưa ai xác nhận vắng trường nào."""
    db = app_db.SessionLocal()
    company = _company(db)
    save_column_map(db, company.id, "m16", "sig-legacy", {"material_code": 4})
    db.commit()
    saved = load_column_map(db, company.id, "m16", "sig-legacy")
    assert saved.absent_fields is None
    assert saved.absent_fields_obj == []


def test_row_keys_are_the_ones_that_reject_the_file():
    assert row_key_fields("m16") == {"product_code", "material_code", "norm_qty"}


# --- Seam 2: route HTTP của màn gán (spec #116) ------------------------------

_REL_DIR = "DN_T112/2025/DINH_MUC"


@pytest.fixture
def env(app_db, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app
    from app.settings import settings
    monkeypatch.setattr(settings, "preview_cache_path", tmp_path / "kho-dem", raising=False)
    (app_db.raw_root / _REL_DIR).mkdir(parents=True, exist_ok=True)
    with app_db.SessionLocal() as db:
        db.add(Company(code="DN_T112", name="T112", tax_id="1"))
        db.commit()
    client = TestClient(app)
    client.post("/login", data={"user": "admin", "password": "admin"}, follow_redirects=False)
    return client, app_db.raw_root


def _register(app_db, detail: dict, name: str = "dm.xlsx") -> tuple[int, str]:
    from tests.excel_fixtures import write_xlsx

    rel = f"{_REL_DIR}/{name}"
    write_xlsx(app_db.raw_root / rel, [["Mã SP", "Mã NVL", "ĐM"], ["SP1", "MAT1", 1.5]])
    with app_db.SessionLocal() as db:
        c = db.query(Company).filter_by(code="DN_T112").one()
        row = DataFile(
            company_id=c.id, period_year=2025, slot="m16",
            original_filename=name, stored_path=rel,
            size_bytes=(app_db.raw_root / rel).stat().st_size,
            parse_status="parsed", row_count=1,
            parse_detail=json.dumps(detail, ensure_ascii=False),
        )
        db.add(row)
        db.commit()
        return row.id, c.slug or c.code


def test_screen_offers_an_input_for_every_declared_field(env, app_db):
    """File máy đặt được 0 trường vẫn gán được tay: mọi trường khai có ô chọn cột."""
    client, _root = env
    detail = {
        "sheet": "BCTT39", "form_signature": "sig-empty", "column_map": {},
        "column_choices": [
            {"index": i, "header": f"cot{i}", "samples": ["a"]} for i in range(3)
        ],
    }
    fid, slug = _register(app_db, detail)
    html = client.get(f"/companies/{slug}/documents/file/{fid}").text
    for field in ("product_code", "product_name", "product_unit", "material_code",
                  "material_name", "material_unit", "norm_qty", "note"):
        assert f'name="col_{field}"' in html, f"thiếu ô chọn cột cho {field}"


def test_screen_survives_a_very_wide_sheet(env, app_db):
    """52/170 trang tính đo được vượt 40 cột; trang rộng nhất là 257."""
    detail = {
        "sheet": "BCTT39", "form_signature": "sig-wide", "column_map": {},
        "column_choices": [
            {"index": i, "header": f"cot{i}", "samples": ["x"]} for i in range(257)
        ],
    }
    client, _root = env
    fid, slug = _register(app_db, detail, name="wide.xlsx")
    r = client.get(f"/companies/{slug}/documents/file/{fid}")
    assert r.status_code == 200
    assert 'value="256"' in r.text


def test_confirming_absent_writes_it_and_rejects_a_missing_row_key(env, app_db):
    client, _root = env
    detail = {
        "sheet": "BCTT39", "form_signature": "sig-post",
        "column_map": {"product_code": 1, "material_code": 4, "norm_qty": 7},
        "column_choices": [
            {"index": i, "header": f"cot{i}", "samples": ["x"]} for i in range(9)
        ],
    }
    fid, slug = _register(app_db, detail, name="post.xlsx")

    # Thiếu khoá dòng → TỪ CHỐI, không ghi gì.
    r = client.post(
        f"/companies/{slug}/documents/file/{fid}",
        data={"_field_major": "1", "col_product_code": "",
              "col_material_code": "4", "col_norm_qty": "7"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "kho%C3%A1+d%C3%B2ng" in r.headers["location"] or "kho" in r.headers["location"]

    # Gán đủ khoá dòng + xác nhận `note` vắng → ghi vào absent_fields.
    client.post(
        f"/companies/{slug}/documents/file/{fid}",
        data={
            "_field_major": "1",
            "col_product_code": "1", "col_material_code": "4", "col_norm_qty": "7",
            "absent_note": "1",
        },
        follow_redirects=False,
    )
    with app_db.SessionLocal() as db:
        c = db.query(Company).filter_by(code="DN_T112").one()
        saved = load_column_map(db, c.id, "m16", "sig-post")
    assert saved is not None
    assert "note" in saved.absent_fields_obj
    assert "note" not in saved.column_map_obj
