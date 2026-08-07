"""Bằng chứng phủ ĐỦ tập trường khai, đo ở seam hàm parse (#111, spec #116 story 1-3).

Trước lát này: Mẫu 16 đọc và ghi 8 trường nhưng chỉ 2 có nguồn bằng chứng, Mẫu 15 là
11/8, Mẫu 15a là 10/7. Trường không có bằng chứng không vào `column_map`, nên không có
badge và không có ô sửa ở biểu mẫu xác nhận cột — đó là #109.

Khẳng định ở seam hàm parse (không phải trên hình dạng dict bằng chứng) để test sống
sót qua tái cấu trúc: thứ được khẳng định là thứ cán bộ nhìn thấy.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from openpyxl import Workbook

from app.adapters.declared_fields import declared_names
from app.adapters.m15 import parse_m15
from app.adapters.m15a import parse_m15a
from app.adapters.m16 import parse_m16


def _write_grid(path: Path, sheet: str, grid: list[list]) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = sheet
    for row in grid:
        ws.append(row)
    path.parent.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    wb.save(buf)
    path.write_bytes(buf.getvalue())
    return path


def _m15_grid() -> list[list]:
    grid: list[list] = [[None] * 11 for _ in range(8)]
    grid.append(["STT", "Mã nguyên liệu, vật tư", "Tên nguyên liệu, vật tư", "ĐVT",
                 "Lượng NL, VT tồn kho đầu kỳ", "Lượng NL, VT nhập trong kỳ",
                 "Tái xuất", "Chuyển mục đích sử dụng", "Xuất kho để sản xuất",
                 "Xuất kho khác", "Lượng NL, VT tồn kho cuối kỳ"])
    for i in range(3):
        grid.append([i + 1, f"MAT{i}", "Vật tư", "KG", 10, 100, 0, 0, 80, 0, 30])
    return grid


def _m15a_grid() -> list[list]:
    grid: list[list] = [[None] * 10 for _ in range(8)]
    grid.append(["STT", "Mã sản phẩm", "Tên sản phẩm", "ĐVT", "Tồn đầu kỳ", "Nhập kho",
                 "Chuyển mục đích", "Lượng SP xuất khẩu", "Xuất khác", "Tồn cuối kỳ"])
    for i in range(3):
        grid.append([i + 1, f"SP{i}", "TP", "PCE", 0, 100, 0, 70, 0, 30])
    return grid


def _m16_grid(note_values: list | None = None) -> list[list]:
    """Bố cục TT39 chuẩn: 9 cột, `note` ở cột 8."""
    grid: list[list] = [[None] * 9 for _ in range(8)]
    grid.append([None, "Mã sản phẩm", "Tên sản phẩm", "ĐVT SP", "Mã nguyên liệu",
                 "Tên nguyên liệu", "ĐVT NVL", "Lượng NL, VT thực tế sử dụng", "Ghi chú"])
    notes = note_values if note_values is not None else [None, None, None]
    for i, note in enumerate(notes):
        grid.append([i + 1, "SP1" if i == 0 else None, "TP" if i == 0 else None,
                     "PCE" if i == 0 else None, f"MAT{i}", "NPL", "KG", 1.5, note])
    return grid


def _column_map(parsed) -> dict:
    return parsed.provenance.detail["column_map"]


def _evidence(parsed) -> dict:
    return parsed.provenance.evidence


@pytest.mark.parametrize(
    ("slot", "builder", "parser", "sheet", "expected_fields"),
    [
        ("m15", _m15_grid, parse_m15, "BCQT_NPL", 11),
        ("m15a", _m15a_grid, parse_m15a, "BCQT_SP", 10),
        ("m16", _m16_grid, parse_m16, "BCTT39", 8),
    ],
)
def test_every_read_field_carries_evidence(
    tmp_path, slot, builder, parser, sheet, expected_fields
):
    """Đo đúng con số ở tiêu chí nghiệm thu: m15 11/11 · m15a 10/10 · m16 8/8."""
    path = _write_grid(tmp_path / f"{slot}.xlsx", sheet, builder())
    parsed = parser(path, sheet=sheet)

    evidence, column_map = _evidence(parsed), _column_map(parsed)
    assert len(column_map) == expected_fields, (
        f"{slot} đọc {sorted(column_map)} — chờ {expected_fields} trường"
    )
    assert set(evidence) == set(column_map), (
        f"{slot}: trường có map nhưng KHÔNG có bằng chứng = "
        f"{sorted(set(column_map) - set(evidence))}; có bằng chứng mà không map = "
        f"{sorted(set(evidence) - set(column_map))}"
    )
    assert set(column_map) <= declared_names(slot)


def test_m16_product_code_reaches_the_column_map(tmp_path):
    """#109 nguyên văn: mã thành phẩm được đọc, được ghi, nhưng không hiện ở khối căn
    cứ đọc và cán bộ không sửa được."""
    path = _write_grid(tmp_path / "m16.xlsx", "BCTT39", _m16_grid())
    parsed = parse_m16(path, sheet="BCTT39")
    assert "product_code" in _column_map(parsed)
    assert "product_code" in _evidence(parsed)


def test_m16_note_reaches_the_column_map(tmp_path):
    """Ca thứ hai của #109: `note` đọc ở cột 8, ghi vào `norms.note`, C4.1 tiêu thụ qua
    `is_domestic_origin` để trừ NVL trong nước khỏi phạm vi — không badge, không ô sửa."""
    path = _write_grid(tmp_path / "m16.xlsx", "BCTT39", _m16_grid(note_values=["x", None, None]))
    parsed = parse_m16(path, sheet="BCTT39")
    assert "note" in _column_map(parsed)
    assert "note" in _evidence(parsed)
    assert parsed.rows[0].note == "x"


def test_m16_note_and_norm_never_share_one_column(tmp_path):
    """Bố cục 004: hai cột định mức → `_detect_actual_norm_col` dời `norm_qty` sang cột
    ĐM thực tế, và chỉ số đó chính là cột `note`. Adapter từng đọc MỘT cột vào HAI
    trường (`norms.note` == `norm_qty` ở 880/880 dòng PILOT_004 2025)."""
    grid: list[list] = [[None] * 9 for _ in range(8)]
    grid.append([None, "Mã sản phẩm", "Tên sản phẩm", "ĐVT SP", "Mã nguyên liệu",
                 "Tên nguyên liệu", "ĐVT NVL", "Định mức kỹ thuật",
                 "Lượng NL, VT thực tế sử dụng"])
    grid.append([1, "SP1", "TP", "PCE", "MAT0", "NPL", "KG", 2.0, 1.5])
    path = _write_grid(tmp_path / "m16_004.xlsx", "BCTT39", grid)
    parsed = parse_m16(path, sheet="BCTT39")

    column_map = _column_map(parsed)
    assert column_map["norm_qty"] == 8, "cột ĐM thực tế phải thắng cột ĐM kỹ thuật"
    assert column_map.get("note") != column_map["norm_qty"]
    # Trường mất chỗ về *chưa gán* — không bịa vị trí khác ở lát này.
    assert "note" not in column_map
    assert parsed.rows[0].norm_qty == 1.5
    assert parsed.rows[0].note is None


def test_m16_parent_child_forward_fill_follows_the_product_code_column(tmp_path):
    """Đổi vị trí cột mã SP đổi CẢ NHÓM dòng NVL forward-fill, không chỉ dòng cha.
    Kho thật: 4.613 mã sản phẩm → 270.385 dòng, 58,6 dòng NVL mỗi mã."""
    path = _write_grid(tmp_path / "m16.xlsx", "BCTT39", _m16_grid())
    parsed = parse_m16(path, sheet="BCTT39")
    assert len(parsed.rows) == 3
    assert {r.product_code for r in parsed.rows} == {"SP1"}
    assert [r.material_code for r in parsed.rows] == ["MAT0", "MAT1", "MAT2"]
