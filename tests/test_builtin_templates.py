"""TPL-1/TPL-2 (#51, #52, ADR #23 T3) — template builtin trong code.

Thứ tự resolve: map officer-confirmed của DN → template builtin khớp vân tay →
dò từ khoá → cổng review. Khớp template = nguồn `builtin-template` (rank giữa
`header-matched` và `officer-confirmed`) → cột `verified` → cổng review TỰ QUA.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from openpyxl import Workbook

from app.adapters import parse_m15, parse_m15a
from app.adapters.evidence import (
    BUILTIN_TEMPLATE,
    HEADER_MATCHED,
    OFFICER_CONFIRMED,
    POSITION_ONLY,
    VERIFIED,
    strongest,
)
from app.adapters.form_signature import compute_form_signature
from app.adapters.layout import find_data_start
from app.adapters.templates import (
    BUILTIN_TEMPLATES,
    MATCH_BUILTIN,
    MATCH_DEFAULT,
    MATCH_KEYWORD,
    match_template,
    template_by_id,
)
from app.checks.registry import review_state

# Vùng tiêu đề hai tầng của biểu TT39 chuẩn, chép nguyên văn NHÃN CỘT từ họ biểu
# thật (text của mẫu ban hành — không phải dữ liệu DN nào). Vân tay hash đúng vùng
# này nên fixture phải giống hệt thì mới tái hiện được họ đã seed.
_M15_HEADER_PARENT = [
    "STT", "Mã nguyên liệu, vật tư", "Tên nguyên liệu, vật tư", "Đơn vị tính",
    "Lượng NL, VT tồn kho đầu kỳ", "Lượng NL, VT nhập trong kỳ",
    "Lượng nguyên liệu, vật tư nhập khẩu xuất kho trong kỳ", None, None, None,
    "Lượng NL, VT nhập khẩu tồn kho cuối kỳ", "Ghi chú",
]
_M15_HEADER_CHILD = [
    None, None, None, None, None, None,
    "Tái xuất", "Chuyển mục đích sử dụng, tiêu thụ nội địa, tiêu hủy",
    "Xuất kho để sản xuất", "Xuất kho khác",
]
_M15A_HEADER_PARENT = [
    "STT", "Mã sản phẩm xuất khẩu", "Tên sản phẩm xuất khẩu", "Đơn vị tính",
    "Lượng sản phẩm tồn kho đầu kỳ", "Lượng sản phẩm nhập trong kỳ",
    "Lượng sản phẩm xuất kho trong kỳ", None, None,
    "Lượng sản phẩm tồn kho cuối kỳ theo sổ sách theo dõi", "Ghi chú",
]
_M15A_HEADER_CHILD = [
    None, None, None, None, None, None,
    "Lượng sản phẩm thay đổi mục đích sử dụng, chuyển tiêu thụ nội địa",
    "Lượng sản phẩm xuất khẩu", "Xuất kho khác",
]


def _write(path: Path, sheet: str, band: list[list], pad: int, rows: list[list]) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = sheet
    width = max(len(r) for r in band)
    for _ in range(pad):
        ws.append([None] * width)
    for header_row in band:
        ws.append(header_row)
    for r in rows:
        ws.append(r)
    path.parent.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    wb.save(buf)
    path.write_bytes(buf.getvalue())
    return path


def m15_fixture(tmp_path: Path, pad: int = 7, band: list[list] | None = None) -> Path:
    return _write(
        tmp_path / "m15.xlsx", "BCQT_NPL",
        band or [_M15_HEADER_PARENT, _M15_HEADER_CHILD], pad,
        [[1, "NVL001", "Vải chính", "MTR", 10, 100, 0, 0, 80, 0, 30]],
    )


def m15a_fixture(tmp_path: Path, pad: int = 7, band: list[list] | None = None) -> Path:
    return _write(
        tmp_path / "m15a.xlsx", "BCQT_SP",
        band or [_M15A_HEADER_PARENT, _M15A_HEADER_CHILD], pad,
        [[1, "SP001", "Áo sơ mi", "PCE", 5, 50, 0, 40, 0, 15]],
    )


def signature_of(path: Path, slot: str) -> tuple[str, int]:
    import pandas as pd

    cells = pd.read_excel(pd.ExcelFile(path), sheet_name=0, header=None).values.tolist()
    data_start = find_data_start(cells, slot)
    return compute_form_signature(cells, slot, data_start), data_start


# --- Registry -----------------------------------------------------------------


def test_registry_seeds_four_families_from_the_census():
    assert len(BUILTIN_TEMPLATES) == 4
    assert {t.slot for t in BUILTIN_TEMPLATES} == {"m15", "m15a"}
    assert len({t.id for t in BUILTIN_TEMPLATES}) == 4
    for t in BUILTIN_TEMPLATES:
        assert t.signatures, f"{t.id} không có vân tay"
        assert t.name and t.note


def test_template_lookup_by_id():
    assert template_by_id("m15a-tt39-chuan").slot == "m15a"
    assert template_by_id("khong-co") is None
    assert template_by_id(None) is None


def test_match_needs_the_right_slot():
    tpl = BUILTIN_TEMPLATES[0]
    sig = next(iter(tpl.signatures))
    assert match_template(tpl.slot, sig, tpl.data_start) is tpl
    assert match_template("m16", sig, tpl.data_start) is None


def test_match_refuses_when_data_start_differs():
    """Cùng vân tay nhưng dữ liệu bắt đầu lệch dòng → KHÔNG khớp (nuốt dòng im lặng)."""
    tpl = BUILTIN_TEMPLATES[0]
    sig = next(iter(tpl.signatures))
    assert match_template(tpl.slot, sig, tpl.data_start - 1) is None


def test_no_signature_never_matches():
    assert match_template("m15", None, 9) is None
    assert match_template("m15", "", 9) is None


# --- Rank nguồn bằng chứng ----------------------------------------------------


def test_builtin_template_outranks_header_match_and_loses_to_officer():
    assert strongest(HEADER_MATCHED, BUILTIN_TEMPLATE) == BUILTIN_TEMPLATE
    assert strongest(BUILTIN_TEMPLATE, OFFICER_CONFIRMED) == OFFICER_CONFIRMED
    assert strongest(POSITION_ONLY, BUILTIN_TEMPLATE) == BUILTIN_TEMPLATE


def test_template_columns_pass_the_review_gate():
    """Cột đọc riêng lẻ: `position-only` phải review, `builtin-template` thì không."""
    assert review_state("m15", "repurpose_qty", POSITION_ONLY) != VERIFIED
    assert review_state("m15", "repurpose_qty", BUILTIN_TEMPLATE) == VERIFIED
    assert review_state("m15a", "export_qty", BUILTIN_TEMPLATE) == VERIFIED


# --- Parse thật qua fixture ---------------------------------------------------


@pytest.mark.parametrize("slot,builder", [("m15", m15_fixture), ("m15a", m15a_fixture)])
def test_fixture_reproduces_a_seeded_family(tmp_path, slot, builder):
    """Fixture phải khớp ĐÚNG một họ đã seed — nếu không, template chỉ là số chết."""
    sig, data_start = signature_of(builder(tmp_path), slot)
    tpl = match_template(slot, sig, data_start)
    assert tpl is not None, f"fixture {slot} không khớp họ nào (sig={sig}, ds={data_start})"
    assert tpl.slot == slot


def test_matched_file_parses_by_the_template_and_is_verified(tmp_path):
    parsed = parse_m15(m15_fixture(tmp_path))
    prov = parsed.provenance
    assert prov.detail["match_source"] == MATCH_BUILTIN
    assert prov.detail["template_id"] == "m15-tt39-chuan"
    assert set(prov.evidence.values()) == {BUILTIN_TEMPLATE}
    # Cột vẫn đọc đúng số liệu.
    assert parsed.rows[0].material_code == "NVL001"
    assert parsed.rows[0].import_qty == 100
    assert parsed.rows[0].closing_qty == 30


def test_m15a_matched_file_parses_by_the_template(tmp_path):
    parsed = parse_m15a(m15a_fixture(tmp_path))
    assert parsed.provenance.detail["template_id"] == "m15a-tt39-chuan"
    assert parsed.rows[0].product_code == "SP001"
    assert parsed.rows[0].export_qty == 40


def _m15_band_with_changed_label() -> list[list]:
    """Đổi nhãn cột cuối — sheet vẫn nhận là m15 (từ khoá chấm điểm không đụng),
    chỉ vân tay đổi. Đổi nhãn CÓ trong từ khoá thì `select_sheet` từ chối luôn file,
    không kiểm được nhánh "không khớp template nhưng vẫn parse"."""
    changed = list(_M15_HEADER_PARENT)
    changed[11] = "Diễn giải"
    return [changed, _M15_HEADER_CHILD]


def test_one_changed_header_label_breaks_the_match(tmp_path):
    """Mutation: đổi MỘT nhãn cột → vân tay khác → không nhận nhầm là họ đã curate."""
    sig, data_start = signature_of(
        m15_fixture(tmp_path, band=_m15_band_with_changed_label()), "m15"
    )
    assert match_template("m15", sig, data_start) is None


def test_unmatched_file_keeps_the_old_path_and_names_its_source(tmp_path):
    parsed = parse_m15(m15_fixture(tmp_path, band=_m15_band_with_changed_label()))
    detail = parsed.provenance.detail
    assert detail["template_id"] is None
    assert detail["match_source"] in (MATCH_KEYWORD, MATCH_DEFAULT)
    assert BUILTIN_TEMPLATE not in set(parsed.provenance.evidence.values())
    # Không đường nào parse im lặng: vẫn đọc được số, nhưng nguồn nói rõ là gì.
    assert parsed.rows[0].material_code == "NVL001"


# --- Căn cứ đọc: tầng nào đã quyết định vị trí cột -----------------------------

# Khẳng định ở mức DỮ LIỆU trên cấu trúc trang file dựng ra (#92), không dò câu chữ
# trong HTML: chỗ hiện đã dời một lần (dòng file → trang file, ADR #24) và sẽ còn dời.


def _basis(match_source: str | None, template_id: str | None = None):
    import json

    from app.models import DataFile
    from app.pipeline.file_page import file_read_basis

    return file_read_basis(DataFile(
        company_id=1, period_year=2025, slot="m15",
        original_filename="NVL.xlsx", stored_path="DN_077/2025/BCQT/NVL.xlsx",
        parse_layout="standard", template_id=template_id, match_source=match_source,
        parse_detail=json.dumps({"template_name": "Mẫu 15 TT39 — bố cục chuẩn"}),
    ))


def test_read_basis_says_which_template_matched():
    basis = _basis(MATCH_BUILTIN, template_id="m15-tt39-chuan")

    assert basis.match_source == MATCH_BUILTIN
    assert basis.template_id == "m15-tt39-chuan"
    assert basis.template_name == "Mẫu 15 TT39 — bố cục chuẩn"
    assert "mẫu biểu" in basis.match_source_label.lower()


def test_read_basis_says_officer_map_when_the_company_map_won():
    from app.adapters.templates import MATCH_OFFICER

    basis = _basis(MATCH_OFFICER)

    assert basis.match_source == MATCH_OFFICER
    assert "cán bộ" in basis.match_source_label.lower()


def test_read_basis_names_the_default_positions_when_nothing_matched():
    basis = _basis(MATCH_DEFAULT)

    assert basis.match_source == MATCH_DEFAULT
    assert "vị trí mặc định" in basis.match_source_label.lower()
