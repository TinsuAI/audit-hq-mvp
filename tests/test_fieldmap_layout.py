"""Bố cục màn gán cột theo TRƯỜNG — mỗi trường một DÒNG (#121, thi hành mục 6 ADR #28).

Bảng cũ CHUYỂN VỊ: mỗi trường là một CỘT, mọi `<select>` nằm chung một hàng và mọi ô
"không có trong file" nằm ở hàng sau. Ba hệ quả đo được: bộ chọn cách ô khai vắng CỦA
CHÍNH NÓ 8–12 chặng tab, bảng nới ngang theo số trường nên phải cuộn mới thấy hết, và
một ô trong bảng chuyển vị cần cả hai trục mới có tên mà 9 `<th>` không có `scope`.

Khẳng định ở CẤU TRÚC (`name=`, `scope=`, thứ tự tài liệu của phần tử nhận focus), không
dò câu chữ tiếng Việt — câu chữ thuộc `test_evidence_prose.py`. Suy từ thứ tự tài liệu ra
thứ tự focus chỉ hợp lệ khi KHÔNG có `tabindex` dương nào, nên bất biến đó cũng khẳng
định ở đây chứ không coi là hiển nhiên.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.adapters.declared_fields import declared as declared_fields
from app.main import app
from app.models import Company, DataFile
from app.pipeline.file_page import UNASSIGNED_MEANS, file_page_url
from app.pipeline.saved_map import load_column_map, save_column_map
from app.settings import settings
from tests.excel_fixtures import write_xlsx
from tests.test_static_assets import _declaration, _rule_body, _rules

REL_DIR = "DN_FM/2025/BCQT"

_M16_FIELDS = tuple(f.name for f in declared_fields("m16"))
_M16_ROW_KEYS = tuple(f.name for f in declared_fields("m16") if f.row_key)

# Bố cục DINHMUC có thật trong kho: không có cột `note`, nên trường đó tới màn ở trạng
# thái *chưa gán* — vế thứ hai của cặp AC 8 (máy chưa đặt được ≠ cán bộ khai vắng).
_M16 = {
    "sheet": "BCTT39",
    "form_signature": "sig-m16",
    "column_map": {
        "product_code": 1, "product_name": 2, "product_unit": 3, "material_code": 4,
        "material_name": 5, "material_unit": 6, "norm_qty": 7,
    },
    "columns": [
        {"field": name, "evidence": "header-matched", "review": "verified"}
        for name in _M16_FIELDS if name != "note"
    ],
    "column_choices": [
        {"index": i, "header": f"cot{i}", "samples": ["x"]} for i in range(9)
    ],
}

_BCCT_FIELDS = tuple(f.name for f in declared_fields("bcct"))
_BCCT = {
    "sheet": "Chi tiet",
    "form_signature": "sig-bcct",
    "column_map": {name: i for i, name in enumerate(_BCCT_FIELDS)},
    "columns": [
        {"field": name, "evidence": "header-matched", "review": "verified"}
        for name in _BCCT_FIELDS
    ],
    "column_choices": [
        {"index": i, "header": f"cot{i}", "samples": ["x"]} for i in range(20)
    ],
}


@pytest.fixture
def env(app_db, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "preview_cache_path", tmp_path / "kho-dem", raising=False)
    (Path(app_db.raw_root) / REL_DIR).mkdir(parents=True, exist_ok=True)
    with app_db.SessionLocal() as db:
        db.add(Company(code="DN_FM", name="Bố cục theo trường", tax_id="1"))
        db.commit()
    client = TestClient(app)
    client.post("/login", data={"user": "admin", "password": "admin"}, follow_redirects=False)
    return client, Path(app_db.raw_root)


def _register(root: Path, detail: dict, *, slot: str = "m16", name: str = "dm.xlsx",
              parse_layout: str | None = None) -> int:
    import app.database as dbmod

    rel = f"{REL_DIR}/{name}"
    write_xlsx(root / rel, [["Mã SP", "Mã NVL", "ĐM"], ["SP1", "MAT1", 1.5]])
    with dbmod.SessionLocal() as db:
        c = db.query(Company).filter_by(code="DN_FM").one()
        row = DataFile(
            company_id=c.id, period_year=2025, slot=slot,
            original_filename=name, stored_path=rel,
            size_bytes=(root / rel).stat().st_size,
            parse_status="parsed", row_count=3, parse_layout=parse_layout,
            parse_detail=json.dumps(detail, ensure_ascii=False),
        )
        db.add(row)
        db.commit()
        return row.id


def _declare_absent(fields: list[str], *, slot: str = "m16", sig: str = "sig-m16",
                    column_map: dict | None = None) -> None:
    """Lời khai vắng của cán bộ, ghi đúng chỗ màn đọc ra: map đã lưu của `(DN, slot, vân tay)`."""
    import app.database as dbmod

    with dbmod.SessionLocal() as db:
        c = db.query(Company).filter_by(code="DN_FM").one()
        save_column_map(
            db, c.id, slot, sig,
            column_map if column_map is not None else {
                k: v for k, v in _M16["column_map"].items() if k not in fields
            },
            absent_fields=fields,
        )
        db.commit()


def _table(text: str) -> str:
    """Chỉ phần bảng gán cột — phần còn lại của trang có bảng khác, nút khác."""
    start = text.index('<table class="fieldmap-table"')
    return text[start : text.index("</table>", start)]


_TAG = re.compile(r"<(a|button|select|textarea|input)\b([^>]*)>", re.I)


def _focus_stops(text: str) -> list[str]:
    """Phần tử nhận focus theo THỨ TỰ TÀI LIỆU. Hợp lệ vì không có `tabindex` dương."""
    stops = []
    for m in _TAG.finditer(text):
        tag, attrs = m.group(1).lower(), m.group(2)
        if tag == "a" and "href=" not in attrs:
            continue
        if tag == "input" and re.search(r'type="hidden"', attrs):
            continue
        if "disabled" in attrs:
            continue
        stops.append(m.group(0))
    return stops


def _assignment_badges(row: str) -> list[str]:
    return [t.strip() for t in re.findall(
        r'<span class="badge[^>]*data-axis="assignment"[^>]*>([^<]*)</span>', row,
    )]


def _checkbox(row: str, field: str) -> str:
    m = re.search(rf'<input[^>]*name="absent_{field}"[^>]*>', row)
    assert m, f"dòng {field} không có ô khai vắng"
    return m.group(0)


def _named(stops: list[str], name: str) -> int:
    for i, tag in enumerate(stops):
        if f'name="{name}"' in tag:
            return i
    raise AssertionError(f"không có phần tử nào mang name={name!r}")


# ─────────────────────── mỗi trường một dòng ───────────────────────

def test_every_declared_field_takes_exactly_one_row(env):
    """Trường là DÒNG, không còn là cột. Đếm theo `name=` chứ không theo nhãn tiếng Việt."""
    client, root = env
    fid = _register(root, _M16)

    table = _table(client.get(file_page_url("DN_FM", fid)).text)
    rows = re.findall(r"<tr\b[^>]*>.*?</tr>", table, re.S)

    body = [r for r in rows if 'scope="row"' in r]
    assert len(body) == len(_M16_FIELDS)
    for row, field in zip(body, _M16_FIELDS, strict=True):
        assert f'name="col_{field}"' in row, f"dòng {field} không mang bộ chọn của chính nó"


def test_a_group_field_still_takes_one_multi_index_input(env):
    """Nhóm cột con (ADR #25) đọc bằng TỔNG nhiều cột — `<select>` một giá trị không nói được."""
    client, root = env
    detail = dict(_M16, column_map=dict(_M16["column_map"], norm_qty=[7, 8]))
    fid = _register(root, detail, parse_layout="extended")

    table = _table(client.get(file_page_url("DN_FM", fid)).text)

    assert table.count('name="col_norm_qty"') == 1
    group_row = next(r for r in re.findall(r"<tr\b[^>]*>.*?</tr>", table, re.S)
                     if 'name="col_norm_qty"' in r)
    assert 'type="text"' in group_row and 'value="7,8"' in group_row
    assert "<select" not in group_row


# ─────────────────────── thứ tự focus ───────────────────────

def test_the_absent_box_is_the_next_focus_stop_after_its_own_picker(env):
    """Số đo của vé: 8–12 chặng ở bảng chuyển vị, phải còn đúng 1."""
    client, root = env
    fid = _register(root, _M16)

    stops = _focus_stops(_table(client.get(file_page_url("DN_FM", fid)).text))

    for field in _M16_FIELDS:
        if field in _M16_ROW_KEYS:
            continue
        assert _named(stops, f"absent_{field}") == _named(stops, f"col_{field}") + 1, field


def test_a_row_key_field_offers_no_absent_box(env):
    """Khoá dòng vắng thì không dựng nổi một dòng Tầng 1 nào — ô đó là lời hứa không giữ được."""
    client, root = env
    fid = _register(root, _M16)

    table = _table(client.get(file_page_url("DN_FM", fid)).text)

    for field in _M16_ROW_KEYS:
        assert f'name="absent_{field}"' not in table


def test_no_positive_tabindex_anywhere_on_the_page(env):
    """Thiếu bất biến này thì thứ tự DOM không suy ra được thứ tự focus, và test trên là vô căn cứ."""
    client, root = env
    fid = _register(root, _M16)

    text = client.get(file_page_url("DN_FM", fid)).text

    assert re.search(r'tabindex\s*=\s*"?\+?[1-9]', text) is None


# ─────────────────────── không cuộn ngang ───────────────────────

def test_the_table_width_does_not_grow_with_the_number_of_fields(env):
    """Bất biến làm cuộn ngang KHÔNG THỂ xảy ra: số cột của bảng không theo số trường.

    Biểu tờ khai khai 19 trường, Mẫu 16 khai 8. Ở bảng chuyển vị đó là 19 cột so 8 cột —
    chính chỗ sinh ra cuộn ngang ở khung nhìn 1280px.
    """
    client, root = env
    m16 = _register(root, _M16)
    bcct = _register(root, _BCCT, slot="bcct", name="tk.xlsx")

    heads = []
    for fid in (m16, bcct):
        table = _table(client.get(file_page_url("DN_FM", fid)).text)
        heads.append(len(re.findall(r'<th[^>]*scope="col"', table)))

    assert heads[0] >= 3, "bảng không có tiêu đề cột nào — phép so bên dưới thành vô nghĩa"
    assert heads[0] == heads[1], f"số cột đổi theo số trường: {heads}"


def test_every_body_row_has_one_cell_per_column_header(env):
    client, root = env
    fid = _register(root, _M16)

    table = _table(client.get(file_page_url("DN_FM", fid)).text)
    width = len(re.findall(r'<th[^>]*scope="col"', table))

    for row in re.findall(r"<tr\b[^>]*>.*?</tr>", table, re.S):
        if 'scope="row"' not in row:
            continue
        cells = len(re.findall(r"<t[dh]\b", row))
        assert cells == width, f"dòng có {cells} ô, tiêu đề có {width} cột"


def test_the_field_map_card_no_longer_bleeds_past_the_viewport() -> None:
    """Bảng cũ tràn `100vw` và tự cuộn ngang vì nó nới theo số trường. Bố cục mới không cần."""
    body = _rule_body(".fieldmap-card")

    for prop in ("width", "overflow-x", "margin-inline", "scrollbar-width"):
        assert _declaration(body, prop) is None, f".fieldmap-card còn khai `{prop}`"


def test_the_field_map_table_is_bounded_by_its_container() -> None:
    body = next(b for sel, b in _rules() if sel.strip() == ".fieldmap-table")

    assert (_declaration(body, "width") or "").strip() == "100%"
    assert (_declaration(body, "table-layout") or "").strip() == "fixed"


def test_read_basis_no_longer_carries_the_sample_rows() -> None:
    """Khẳng định bằng HÌNH DẠNG DỮ LIỆU (theo mẫu #120): còn trường thì dựng lại được.

    Dòng mẫu lấy theo hàng chỉ có nghĩa trong bảng chuyển vị. Ở bố cục theo trường, dòng
    dữ liệu thật thuộc về lưới — nó hiện dòng NGUYÊN VẸN của trang tính (ADR #29).
    """
    import dataclasses

    from app.pipeline.file_page import ReadBasis

    assert "sample_rows" not in {f.name for f in dataclasses.fields(ReadBasis)}


def test_the_transposed_row_rules_are_gone() -> None:
    """Bốn lớp chỉ có nghĩa trong bảng chuyển vị, kể cả chặn 18rem #120 thêm vào cho ô căn cứ."""
    dead = ("fm-pickrow", "fm-absentrow", "fm-metarow", "fm-datarow")

    for sel, _body in _rules():
        for name in dead:
            assert name not in sel, f"`{name}` còn rule trong style.css: {sel.strip()}"


# ─────────────────────── ô của bảng có tên theo cả hai trục ───────────────────────

def test_every_header_cell_of_the_table_declares_its_axis(env):
    """9 `<th>` không có `scope` ở bản cũ: ô dữ liệu không suy ra được nó thuộc trường nào."""
    client, root = env
    fid = _register(root, _M16)

    table = _table(client.get(file_page_url("DN_FM", fid)).text)

    for th in re.findall(r"<th\b[^>]*>", table):
        assert re.search(r'scope="(col|row)"', th), th


# ─────────────────────── hai lời khai của cán bộ ───────────────────────

def test_an_assigned_field_renders_back_the_column_it_was_saved_with(env):
    client, root = env
    fid = _register(root, _M16)

    table = _table(client.get(file_page_url("DN_FM", fid)).text)
    row = next(r for r in re.findall(r"<tr\b[^>]*>.*?</tr>", table, re.S)
               if 'name="col_material_code"' in r)

    assert re.search(r'<option value="4"[^>]*selected', row)
    assert "chưa gán" not in row, "trường đã gán không được mời bỏ gán: ô trống nghĩa là giữ nguyên"


def test_an_unassigned_field_keeps_the_empty_option_that_means_keep_as_is(env):
    client, root = env
    fid = _register(root, _M16)

    table = _table(client.get(file_page_url("DN_FM", fid)).text)
    row = next(r for r in re.findall(r"<tr\b[^>]*>.*?</tr>", table, re.S)
               if 'name="col_note"' in r)

    assert re.search(r'<option value=""[^>]*selected', row)


def test_an_absent_field_renders_the_officers_statement_back(env):
    client, root = env
    fid = _register(root, _M16)
    _declare_absent(["note"])

    table = _table(client.get(file_page_url("DN_FM", fid)).text)
    row = next(r for r in re.findall(r"<tr\b[^>]*>.*?</tr>", table, re.S)
               if 'name="absent_note"' in r)

    assert "checked" in row


def test_the_officers_absent_statement_reads_differently_from_a_field_never_placed(env):
    """AC 8. Hai trạng thái khác nhau về NGUỒN: một là kết luận của cán bộ, một là máy chưa đặt được."""
    client, root = env
    # `product_name` không có trong map của lượt nạp: MÁY chưa đặt được nó.
    # `note` có trong lời khai đã lưu: CÁN BỘ kết luận file không có trường đó.
    detail = dict(_M16, column_map={
        k: v for k, v in _M16["column_map"].items() if k != "product_name"
    })
    fid = _register(root, detail)
    _declare_absent(["note"], column_map=detail["column_map"])

    table = _table(client.get(file_page_url("DN_FM", fid)).text)
    rows = re.findall(r"<tr\b[^>]*>.*?</tr>", table, re.S)
    absent = next(r for r in rows if 'name="col_note"' in r)
    unassigned = next(r for r in rows if 'name="col_product_name"' in r)

    # Nhãn trục *gán cột* nói nguồn của trạng thái, và chỉ một trong hai dòng đổi nền.
    assert _assignment_badges(absent) == ["Không có trong file"]
    assert _assignment_badges(unassigned) == ["Chưa gán"]
    assert "fm-row-absent" in absent and "fm-row-absent" not in unassigned
    assert "checked" in _checkbox(absent, "note")
    assert "checked" not in _checkbox(unassigned, "product_name")


def test_the_absent_row_is_marked_by_a_class_that_has_a_rule(env):
    client, root = env
    fid = _register(root, _M16)
    _declare_absent(["note"])

    table = _table(client.get(file_page_url("DN_FM", fid)).text)
    row = next(r for r in re.findall(r"<tr\b[^>]*>.*?</tr>", table, re.S)
               if 'name="absent_note"' in r)
    marker = re.search(r'<tr class="([^"]*)"', row).group(1).split()

    assert any(any(f".{cls}" in sel for sel, _ in _rules()) for cls in marker), marker


def test_the_unassigned_sentence_names_controls_that_exist_on_the_screen(env):
    """Câu "chưa gán" chỉ đường bằng TÊN control — bản cũ nói "hàng «Cột trên file»",
    tức là hàng của bảng chuyển vị. Đổi bố cục mà giữ câu là chỉ cán bộ tới chỗ không
    còn tồn tại, nên câu và tiêu đề cột phải khớp nhau ở mức chuỗi."""
    client, root = env
    fid = _register(root, _M16)

    table = _table(client.get(file_page_url("DN_FM", fid)).text)
    headers = [h.strip() for h in
               re.findall(r'<th[^>]*scope="col"[^>]*>([^<]*)</th>', table)]
    quoted = re.findall(r"“([^”]+)”", UNASSIGNED_MEANS)

    assert quoted, "câu không gọi tên control nào"
    for name in quoted:
        assert name in headers, f"câu chỉ tới “{name}”, bảng không có cột nào tên đó"


def test_the_absent_row_is_not_rendered_by_dimming() -> None:
    """`opacity: .55` đo được 2,55 — vừa không đọc được, vừa nói sai: đó là lời khai của
    cán bộ, không phải chỗ hệ thống bớt tin. Phép đo tương phản ở `test_static_assets`
    KHÔNG tính `opacity`, nên phải chốt riêng."""
    for sel, body in _rules():
        if "fm-row-absent" in sel or "fm-col-absent" in sel:
            assert _declaration(body, "opacity") is None, sel.strip()


# ─────────────────────── bộ chọn giữ tiêu đề cột thật ───────────────────────

def test_the_picker_labels_each_column_with_its_real_header(env):
    client, root = env
    fid = _register(root, _M16)

    table = _table(client.get(file_page_url("DN_FM", fid)).text)

    assert "«cot4»" in table


# ─────────────────────── ô khai vắng dựng có điều kiện ───────────────────────

def test_a_form_with_no_column_snapshot_declares_no_absent_box(env):
    """`_field_major` nói "biểu mẫu lần này CÓ dựng ô khai vắng". Phát nó ở biểu mẫu KHÔNG
    dựng ô đó thì lượt gửi tính ra `absent_fields=[]` và xoá sạch lời khai đã lưu."""
    client, root = env
    detail = {k: v for k, v in _M16.items() if k != "column_choices"}
    fid = _register(root, detail)

    text = client.get(file_page_url("DN_FM", fid)).text

    assert 'name="absent_note"' not in text
    assert "_field_major" not in text


def test_a_saved_absent_statement_survives_a_form_that_has_no_absent_box(env, app_db):
    client, root = env
    detail = {k: v for k, v in _M16.items() if k != "column_choices"}
    fid = _register(root, detail)
    _declare_absent(["note"])

    client.post(
        file_page_url("DN_FM", fid),
        data={"col_product_code": "1", "col_material_code": "4", "col_norm_qty": "7"},
        follow_redirects=False,
    )

    with app_db.SessionLocal() as db:
        c = db.query(Company).filter_by(code="DN_FM").one()
        saved = load_column_map(db, c.id, "m16", "sig-m16")
    assert saved.absent_fields_obj == ["note"]


def test_the_field_major_marker_is_declared_once(env):
    """Nó nói về CẢ biểu mẫu, không về từng trường — phát lại theo mỗi dòng là 8–19 bản sao."""
    client, root = env
    fid = _register(root, _M16)

    text = client.get(file_page_url("DN_FM", fid)).text

    assert text.count("_field_major") == 1
