"""Một trang file duy nhất (#92) — địa chỉ chuẩn, căn cứ đọc, hai địa chỉ cũ chuyển hướng.

Trang xem file và trang xác nhận cột trước đây dựng cùng một thứ hai lần, và lưới
xác nhận bị cắt còn 15 dòng — hạn mức vô nghĩa sau khi lưới cuộn (#91) ra đời. Ở
đây khẳng định vào DỮ LIỆU: cấu trúc `file_read_basis` và các thuộc tính `data-*`
của điểm neo lưới, chứ không dò câu chữ tiếng Việt trong HTML.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.adapters.templates import MATCH_BUILTIN, MATCH_EXTENDED, MATCH_OFFICER
from app.main import app
from app.models import Company, DataFile
from app.pipeline.file_page import NEVER_PARSED, file_page_url, file_read_basis
from app.settings import settings
from tests.excel_fixtures import write_xlsx

REL_DIR = "DN_FP/2025/BCQT"


@pytest.fixture
def env(app_db, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "preview_cache_path", tmp_path / "kho-dem", raising=False)
    (Path(app_db.raw_root) / REL_DIR).mkdir(parents=True, exist_ok=True)
    with app_db.SessionLocal() as db:
        db.add(Company(code="DN_FP", name="Trang file", tax_id="1"))
        db.commit()
    client = TestClient(app)
    client.post("/login", data={"user": "admin", "password": "admin"}, follow_redirects=False)
    return client, Path(app_db.raw_root)


def _register(
    name: str = "m15.xlsx",
    *,
    slot: str = "m15",
    parse_detail: dict | None = None,
    sheet_override: str | None = None,
    match_source: str | None = None,
    template_id: str | None = None,
    parse_layout: str | None = None,
    row_count: int | None = 3,
) -> int:
    import app.database as dbmod

    rel = f"{REL_DIR}/{name}"
    with dbmod.SessionLocal() as db:
        c = db.query(Company).filter_by(code="DN_FP").one()
        row = DataFile(
            company_id=c.id, period_year=2025, slot=slot,
            original_filename=name, stored_path=rel,
            size_bytes=(Path(settings.raw_data_path) / rel).stat().st_size,
            parse_status="parsed", row_count=row_count,
            sheet_override=sheet_override,
            match_source=match_source, template_id=template_id,
            parse_layout=parse_layout,
            parse_detail=json.dumps(parse_detail, ensure_ascii=False) if parse_detail else None,
        )
        db.add(row)
        db.commit()
        return row.id


def _row(file_id: int) -> DataFile:
    import app.database as dbmod

    with dbmod.SessionLocal() as db:
        return db.get(DataFile, file_id)


_M15_DETAIL = {
    "sheet": "BCQT_NVL",
    "form_signature": "sig-m15",
    "template_id": "m15-tt39-chuan",
    "template_name": "Mẫu 15 TT39 — bố cục chuẩn",
    "column_map": {"material_code": 1, "production_out_qty": 8},
    "columns": [
        {"field": "material_code", "label": "Mã NVL",
         "evidence": "header-matched", "review": "verified"},
        {"field": "production_out_qty", "label": "Xuất sản xuất",
         "evidence": "balance-checked", "review": "needs_review"},
    ],
}


def _mount(text: str) -> dict[str, str]:
    tag = re.search(r"<div[^>]*id=\"cell-grid\"[^>]*>", text)
    assert tag, "trang không có điểm neo lưới"
    return {
        m.group(1): html.unescape(m.group(3))
        for m in re.finditer(r"data-([a-z-]+)=([\"'])(.*?)\2", tag.group(0))
    }


# ───────────────────────────── căn cứ đọc (dữ liệu) ─────────────────────────────

def test_read_basis_names_what_decided_each_column(env):
    _client, root = env
    write_xlsx(root / REL_DIR / "m15.xlsx", [["Mã", 1]], sheet_name="BCQT_NVL")
    fid = _register(parse_detail=_M15_DETAIL, match_source=MATCH_BUILTIN,
                    template_id="m15-tt39-chuan", parse_layout="standard")

    basis = file_read_basis(_row(fid))

    assert basis.parsed is True
    by_field = {c.field: c for c in basis.columns}
    assert by_field["material_code"].evidence_label == "Khớp tiêu đề"
    assert by_field["material_code"].columns == (1,)
    assert by_field["material_code"].needs_review is False
    assert by_field["production_out_qty"].evidence_label == "Khớp đẳng thức"
    assert by_field["production_out_qty"].needs_review is True
    # Cột nào ảnh hưởng kiểm tra nào — cùng nguồn với cổng review.
    assert "C4.3" in by_field["production_out_qty"].checks


def test_read_basis_lists_the_columns_still_waiting_for_confirmation(env):
    _client, root = env
    write_xlsx(root / REL_DIR / "m15.xlsx", [["Mã", 1]], sheet_name="BCQT_NVL")
    fid = _register(parse_detail=_M15_DETAIL, match_source=MATCH_BUILTIN)

    basis = file_read_basis(_row(fid))

    assert basis.needs_confirmation == ("Xuất sản xuất",)
    assert basis.needs_count == 1


def test_read_basis_passes_through_the_layer_that_decided_the_column_positions(env):
    """Giá trị thô của `match_source` đi thẳng từ dòng registry sang căn cứ đọc.

    Câu ở MỨC TRANG nói tầng nào quyết định vị trí cột đã bỏ ở #120: mỗi cột mang căn
    cứ của riêng nó, còn một câu mô tả cả file bằng tên một tầng thì đi stale. Nên
    không còn `match_source_label` để khẳng định — chỉ còn đường dữ liệu ở đây.
    """
    _client, root = env
    write_xlsx(root / REL_DIR / "m15.xlsx", [["Mã", 1]])
    fid = _register(parse_detail=_M15_DETAIL, match_source=MATCH_OFFICER)

    basis = file_read_basis(_row(fid))

    assert basis.match_source == MATCH_OFFICER


def test_read_basis_of_a_file_never_read_says_so_instead_of_breaking(env):
    """#84 mới nối đường ghi `match_source`; file cũ và file chưa nạp vẫn phải mở được.

    Câu nói ra ca này chuyển sang `status_note` ở #120 — bảng gán cột chỉ render khi có
    cột đọc được, nên đây là chỗ duy nhất còn nói được “chưa đọc lần nào”.
    """
    _client, root = env
    write_xlsx(root / REL_DIR / "m15.xlsx", [["Mã", 1]])
    fid = _register(row_count=None)                        # không parse_detail, không match_source

    basis = file_read_basis(_row(fid))

    assert basis.parsed is False
    assert basis.columns == ()
    assert basis.needs_confirmation == ()
    assert basis.match_source is None
    assert basis.status_note == NEVER_PARSED


def test_read_basis_keeps_a_column_that_has_evidence_but_no_stored_position(env):
    """Bằng chứng ghi cho một trường mà map không giữ vị trí — vẫn phải nêu ra.

    `resolve_template_evidence` lọc `column_map` theo các trường có trong map, nên
    một trường có bằng chứng mà không có vị trí là ca có thật. Bỏ nó khỏi khối căn
    cứ là giấu một cột hệ thống đang đọc.
    """
    _client, root = env
    write_xlsx(root / REL_DIR / "m15.xlsx", [["Mã", 1]])
    fid = _register(parse_detail={
        "sheet": "BCQT_NVL", "form_signature": "sig-m15",
        "column_map": {"material_code": 1},
        "columns": [
            {"field": "material_code", "label": "Mã NVL",
             "evidence": "header-matched", "review": "verified"},
            {"field": "closing_qty", "label": "Tồn cuối",
             "evidence": "balance-checked", "review": "needs_review"},
        ],
    })

    basis = file_read_basis(_row(fid))

    by_field = {c.field: c for c in basis.columns}
    # Mỗi TRƯỜNG KHAI của biểu có một dòng (#112), nên tập dòng rộng hơn map.
    assert {"material_code", "closing_qty"} <= set(by_field)
    assert by_field["closing_qty"].columns == ()
    assert by_field["closing_qty"].column_ref == ""
    assert by_field["closing_qty"].evidence_label == "Khớp đẳng thức"
    assert "Tồn cuối" in basis.needs_confirmation
    # Vẫn xác nhận được: trường KHÁC có vị trí lưu, biểu mẫu còn việc để làm.
    assert basis.can_confirm is True


def test_a_file_with_evidence_but_no_stored_position_offers_no_input_for_it(env):
    client, root = env
    write_xlsx(root / REL_DIR / "m15.xlsx", [["Mã", 1]])
    fid = _register(parse_detail={
        "sheet": "BCQT_NVL", "form_signature": "sig-m15",
        "column_map": {"material_code": 1},
        "columns": [
            {"field": "material_code", "label": "Mã NVL",
             "evidence": "header-matched", "review": "verified"},
            {"field": "closing_qty", "label": "Tồn cuối",
             "evidence": "balance-checked", "review": "needs_review"},
        ],
    })

    text = client.get(file_page_url("DN_FP", fid)).text

    assert "Tồn cuối" in text                              # có mặt ở khối căn cứ
    assert 'name="col_closing_qty"' not in text            # không hứa một việc không làm


def test_read_basis_keeps_a_group_of_sub_columns_together(env):
    """Bố cục mở rộng đọc một trường bằng TỔNG nhiều cột con (ADR #25)."""
    _client, root = env
    write_xlsx(root / REL_DIR / "m15.xlsx", [["Mã", 1]])
    fid = _register(
        parse_layout="extended", match_source=MATCH_EXTENDED,
        parse_detail={
            "sheet": "BCQT_NVL", "form_signature": "sig-ext",
            "column_map": {"import_qty": [5, 6]},
            "columns": [{"field": "import_qty", "label": "Nhập trong kỳ",
                         "evidence": "balance-checked", "review": "needs_review"}],
        },
    )

    basis = file_read_basis(_row(fid))

    by_field = {c.field: c for c in basis.columns}
    assert by_field["import_qty"].columns == (5, 6)
    assert by_field["import_qty"].column_ref == "F, G"           # chữ cái cột, đếm từ 0
    assert basis.layout == "extended"                            # bố cục thô, không nhãn (#120)


# ───────────────────────────── một địa chỉ cho mỗi file ─────────────────────────

def test_the_file_page_answers_on_its_own_address(env):
    client, root = env
    write_xlsx(root / REL_DIR / "m15.xlsx", [["Mã", 1]], sheet_name="BCQT_NVL")
    fid = _register(parse_detail=_M15_DETAIL)

    r = client.get(file_page_url("DN_FP", fid))

    assert r.status_code == 200
    assert _mount(r.text)["cells-url"] == f"/companies/DN_FP/documents/file/{fid}/cells"


def test_both_old_addresses_redirect_to_the_one_address(env):
    client, root = env
    write_xlsx(root / REL_DIR / "m15.xlsx", [["Mã", 1]])
    fid = _register(parse_detail=_M15_DETAIL)
    target = file_page_url("DN_FP", fid)

    preview = client.get(f"{target}/preview", follow_redirects=False)
    review = client.get(f"{target}/review", follow_redirects=False)

    assert preview.status_code in (301, 302, 307, 308)
    assert preview.headers["location"] == target
    assert review.status_code in (301, 302, 307, 308)
    assert review.headers["location"] == target


def test_the_old_preview_address_keeps_the_sheet_the_officer_was_looking_at(env):
    client, root = env
    write_xlsx(root / REL_DIR / "m15.xlsx", [["Mã", 1]])
    fid = _register(parse_detail=_M15_DETAIL)

    r = client.get(f"{file_page_url('DN_FP', fid)}/preview?sheet=2", follow_redirects=False)

    assert r.headers["location"].endswith("?sheet=2")


def test_a_file_of_another_company_is_not_reachable_by_address(env):
    client, root = env
    write_xlsx(root / REL_DIR / "m15.xlsx", [["Mã", 1]])
    _register(parse_detail=_M15_DETAIL)

    assert client.get(file_page_url("DN_FP", 999999)).status_code == 404


def test_a_file_gone_from_disk_is_a_404_on_the_one_address_too(env):
    client, root = env
    write_xlsx(root / REL_DIR / "m15.xlsx", [["Mã", 1]])
    fid = _register(parse_detail=_M15_DETAIL)
    (root / REL_DIR / "m15.xlsx").unlink()

    assert client.get(file_page_url("DN_FP", fid)).status_code == 404
    assert client.get(f"{file_page_url('DN_FP', fid)}/preview").status_code == 404


# ─────────────────────── xác nhận cột ngay trên lưới đầy đủ ─────────────────────

def test_the_confirm_form_sits_on_the_same_page_as_the_scrolling_grid(env):
    client, root = env
    write_xlsx(root / REL_DIR / "m15.xlsx", [["Mã", 1]], sheet_name="BCQT_NVL")
    fid = _register(parse_detail=_M15_DETAIL)

    text = client.get(file_page_url("DN_FP", fid)).text

    assert _mount(text)["cells-url"]                       # lưới cuộn đầy đủ
    assert 'name="col_production_out_qty"' in text         # ô sửa chỉ số cột
    assert 'id="review-grid"' not in text                  # lưới rút gọn 15 dòng đã bỏ


def test_the_grid_opens_on_the_sheet_the_parser_read_not_the_first_one(env):
    """Xác nhận cột trên trang tính khác là xác nhận nhầm bố cục (workbook ECUS)."""
    client, root = env
    write_xlsx(
        root / REL_DIR / "m15.xlsx", [["Tổng hợp"]], sheet_name="Tổng hợp",
        extra_sheets={"BCQT_NVL": [["Mã", 1]]},
    )
    fid = _register(parse_detail=_M15_DETAIL)

    attrs = _mount(client.get(file_page_url("DN_FP", fid)).text)

    assert attrs["sheet"] == "1"                           # chỉ số của "BCQT_NVL"
    assert attrs["parsed-sheet"] == "BCQT_NVL"


def test_an_explicit_sheet_in_the_address_wins(env):
    client, root = env
    write_xlsx(
        root / REL_DIR / "m15.xlsx", [["Tổng hợp"]], sheet_name="Tổng hợp",
        extra_sheets={"BCQT_NVL": [["Mã", 1]]},
    )
    fid = _register(parse_detail=_M15_DETAIL)

    attrs = _mount(client.get(f"{file_page_url('DN_FP', fid)}?sheet=0").text)

    assert attrs["sheet"] == "0"


def test_the_sheet_picker_and_the_book_field_stay_on_the_page(env):
    """Bộ chọn trang tính nay là hàng liên kết trên lưới, không phải `<select>` (#124)."""
    client, root = env
    write_xlsx(
        root / REL_DIR / "m15.xlsx", [["Mã", 1]], sheet_name="BCQT_NVL",
        extra_sheets={"Phụ lục": [["x"]]},
    )
    fid = _register(parse_detail=_M15_DETAIL)

    text = client.get(file_page_url("DN_FP", fid)).text

    assert 'data-sheet-name="Phụ lục"' in text             # mọi trang xem lại được
    assert 'id="sheet-pin"' in text                        # ghim là hành động riêng
    assert 'name="book"' in text                           # file quyết toán → có ô sổ


def test_a_declaration_file_has_no_book_field(env):
    client, root = env
    (root / "DN_FP/2025/HANG_CHI_TIET").mkdir(parents=True, exist_ok=True)
    write_xlsx(root / "DN_FP/2025/HANG_CHI_TIET/bcct.xlsx", [["Số TK", 1]])
    import app.database as dbmod

    with dbmod.SessionLocal() as db:
        c = db.query(Company).filter_by(code="DN_FP").one()
        row = DataFile(
            company_id=c.id, period_year=2025, slot="bcct",
            original_filename="bcct.xlsx",
            stored_path="DN_FP/2025/HANG_CHI_TIET/bcct.xlsx",
            size_bytes=10, parse_status="parsed",
            parse_detail=json.dumps({
                "form_signature": "sig-bcct", "column_map": {"declaration_no": 1},
                "columns": [{"field": "declaration_no", "label": "Số TK",
                             "evidence": "header-matched", "review": "verified"}],
            }, ensure_ascii=False),
        )
        db.add(row)
        db.commit()
        fid = row.id

    assert 'name="book"' not in client.get(file_page_url("DN_FP", fid)).text


def test_confirming_columns_posts_to_the_one_address(env):
    client, root = env
    write_xlsx(root / REL_DIR / "m15.xlsx", [["Mã", 1]], sheet_name="BCQT_NVL")
    fid = _register(parse_detail=_M15_DETAIL)

    r = client.post(
        file_page_url("DN_FP", fid),
        data={"col_material_code": "1", "col_production_out_qty": "9"},
        follow_redirects=False,
    )

    assert r.status_code == 303
    import app.database as dbmod
    from app.pipeline.saved_map import load_column_map

    with dbmod.SessionLocal() as db:
        c = db.query(Company).filter_by(code="DN_FP").one()
        saved = load_column_map(db, c.id, "m15", "sig-m15")
        assert saved is not None
        assert saved.column_map_obj["production_out_qty"] == 9


def test_the_old_confirm_address_still_accepts_the_form(env):
    client, root = env
    write_xlsx(root / REL_DIR / "m15.xlsx", [["Mã", 1]], sheet_name="BCQT_NVL")
    fid = _register(parse_detail=_M15_DETAIL)

    r = client.post(
        f"{file_page_url('DN_FP', fid)}/review",
        data={"col_material_code": "1", "col_production_out_qty": "7"},
        follow_redirects=False,
    )

    assert r.status_code == 303


def test_a_file_with_no_column_layout_still_offers_the_sheet_pin(env):
    """File đọc hỏng: không có bố cục cột để xác nhận, nhưng phải ghim được trang tính."""
    client, root = env
    write_xlsx(
        root / REL_DIR / "m15.xlsx", [["x"]], sheet_name="Phụ lục",
        extra_sheets={"BCQT_NVL": [["Mã", 1]]},
    )
    fid = _register()

    text = client.get(file_page_url("DN_FP", fid)).text

    assert 'name="sheet"' in text                          # nút ghim, gửi qua `…/sheet`
    assert 'data-sheet-name="BCQT_NVL"' in text            # trang chứa biểu xem được
    assert 'name="col_material_code"' not in text
