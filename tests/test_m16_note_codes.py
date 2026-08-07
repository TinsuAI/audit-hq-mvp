"""Bộ mã cột (9) Mẫu 16 phụ thuộc KỲ (#114).

Nguyên văn hai bản văn bản ở `.ai/notes/2026-08-08-huong-dan-lap-mau-16-tt39.md`:

- TT 39/2018 Phụ lục II tr. 8 — cột (9) có BA trạng thái: `X` mua trong nước · để
  trống = nhập khẩu · `KXDĐM` không xây dựng được định mức.
- TT 121/2025 tr. 238, hiệu lực **01/02/2026** — thêm `TH` (thu hồi từ SP tái nhập)
  và `SPTN` (sửa chữa/tái chế từ SP tái nhập).

Kho bắc qua CẢ HAI thế hệ, nên bộ mã không được hằng số hoá.
"""

from __future__ import annotations

import io
from datetime import date

import pytest
from openpyxl import Workbook

from app.adapters.m16 import parse_m16
from app.adapters.m16_note import (
    DOMESTIC,
    NO_NORM,
    RECOVERED_REIMPORT,
    REWORK_REIMPORT,
    TT121_EFFECTIVE,
    is_domestic_origin,
    is_unknown_note,
    note_codes_for,
)

# Kỳ dương lịch 2025 kết thúc 31/12/2025 (trước mốc); kỳ 2026 kết thúc 31/12/2026 (sau).
TT39_PERIOD_END = date(2025, 12, 31)
TT121_PERIOD_END = date(2026, 12, 31)


def test_effective_date_is_the_one_in_the_gazette():
    assert TT121_EFFECTIVE == date(2026, 2, 1)


def test_tt39_period_accepts_three_states():
    assert note_codes_for(TT39_PERIOD_END) == {DOMESTIC, NO_NORM}


def test_tt121_period_adds_the_two_reimport_codes():
    assert note_codes_for(TT121_PERIOD_END) == {
        DOMESTIC, NO_NORM, RECOVERED_REIMPORT, REWORK_REIMPORT
    }


@pytest.mark.parametrize(
    ("period_end", "expected_extra"),
    [
        (date(2026, 1, 31), False),   # ngay TRƯỚC mốc
        (TT121_EFFECTIVE, True),      # ĐÚNG ngày hiệu lực
        (date(2026, 2, 2), True),     # ngay SAU mốc
    ],
)
def test_boundary_on_both_sides_of_2026_02_01(period_end, expected_extra):
    codes = note_codes_for(period_end)
    assert (RECOVERED_REIMPORT in codes) is expected_extra
    assert (REWORK_REIMPORT in codes) is expected_extra
    # Hai mã của TT 39 có ở CẢ hai thế hệ.
    assert DOMESTIC in codes and NO_NORM in codes


def test_th_and_sptn_are_strange_values_in_a_2025_period():
    """Không im lặng: kỳ ≤ 2025 chưa có hai mã này."""
    assert is_unknown_note("TH", TT39_PERIOD_END)
    assert is_unknown_note("SPTN", TT39_PERIOD_END)
    assert not is_unknown_note("TH", TT121_PERIOD_END)
    assert not is_unknown_note("SPTN", TT121_PERIOD_END)


def test_blank_is_never_strange():
    """Để trống = nhập khẩu, là một trạng thái HỢP LỆ của biểu, không phải giá trị lạ."""
    for blank in (None, "", "   "):
        assert not is_unknown_note(blank, TT39_PERIOD_END)
        assert not is_unknown_note(blank, TT121_PERIOD_END)


def test_junk_value_is_strange_in_both_generations():
    for period_end in (TT39_PERIOD_END, TT121_PERIOD_END):
        assert is_unknown_note("abc", period_end)
        assert is_unknown_note("1.5", period_end)


def test_codes_are_read_case_and_space_insensitively():
    assert not is_unknown_note("  x  ", TT39_PERIOD_END)
    assert not is_unknown_note("kxdđm", TT39_PERIOD_END)
    assert not is_unknown_note("KXDĐM", TT39_PERIOD_END)
    assert not is_unknown_note("sptn", TT121_PERIOD_END)


def test_kxddm_is_not_domestic():
    """DN tự khai KHÔNG xây dựng được định mức — khác hẳn "mua trong nước".

    Trước #114 mọi mã ≠ "x" bị xử lý y hệt ô để trống. `is_domestic_origin` vốn đã trả
    False cho `KXDĐM`; test này khoá lại để không ai "sửa" thành True khi thêm mã mới.
    """
    assert not is_domestic_origin("KXDĐM")
    assert not is_domestic_origin("kxdđm")


def test_reimport_codes_are_not_domestic():
    assert not is_domestic_origin("TH")
    assert not is_domestic_origin("SPTN")


def test_domestic_behaviour_of_x_is_unchanged():
    """Cổng chống sửa quá tay: C4.1 phải trừ ĐÚNG tập mã như trước (delta = 0)."""
    assert is_domestic_origin("x")
    assert is_domestic_origin("X")
    assert is_domestic_origin("  x  ")
    assert not is_domestic_origin(None)
    assert not is_domestic_origin("")
    assert not is_domestic_origin("xx")
    assert not is_domestic_origin("x1")


# --- Seam hàm parse: giá trị lạ phải đếm được, không nuốt im lặng ---------------


def _write_m16(path, note_values: list) -> str:
    """Bố cục TT39: cột (9) = `note` ở chỉ số 8."""
    grid: list[list] = [[None] * 9 for _ in range(8)]
    grid.append([None, "Mã sản phẩm", "Tên sản phẩm", "ĐVT SP", "Mã nguyên liệu",
                 "Tên nguyên liệu", "ĐVT NVL", "Lượng NL, VT thực tế sử dụng", "Ghi chú"])
    for i, note in enumerate(note_values):
        grid.append([i + 1, "SP1" if i == 0 else None, "TP" if i == 0 else None,
                     "PCE" if i == 0 else None, f"MAT{i}", "NPL", "KG", 1.5, note])
    wb = Workbook()
    ws = wb.active
    ws.title = "BCTT39"
    for row in grid:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    path.write_bytes(buf.getvalue())
    return str(path)


def test_parse_counts_out_of_set_notes_for_a_2025_period(tmp_path):
    path = _write_m16(tmp_path / "m16.xlsx", ["X", "TH", "SPTN", "rác"])
    parsed = parse_m16(path, sheet="BCTT39", year=2025)
    # Kỳ 2025 thuộc TT 39 → TH/SPTN chưa tồn tại, cùng "rác" là ba giá trị lạ.
    assert parsed.issues.unknown_note_codes == {"TH": 1, "SPTN": 1, "RÁC": 1}
    assert parsed.issues.unknown_note_total == 3


def test_parse_accepts_the_reimport_codes_for_a_2026_period(tmp_path):
    path = _write_m16(tmp_path / "m16.xlsx", ["X", "TH", "SPTN", "rác"])
    parsed = parse_m16(path, sheet="BCTT39", year=2026)
    # Kỳ 2026 thuộc TT 121 → chỉ "rác" là lạ.
    assert parsed.issues.unknown_note_codes == {"RÁC": 1}


def test_parse_never_flags_blank_or_known_codes(tmp_path):
    path = _write_m16(tmp_path / "m16.xlsx", ["X", None, "KXDĐM", ""])
    parsed = parse_m16(path, sheet="BCTT39", year=2025)
    assert parsed.issues.unknown_note_codes == {}


def test_unknown_notes_do_not_change_the_values_loaded(tmp_path):
    """Cảnh báo, KHÔNG đổi số liệu đã nạp — cùng quy ước với ô lỗi Excel."""
    path = _write_m16(tmp_path / "m16.xlsx", ["TH"])
    parsed = parse_m16(path, sheet="BCTT39", year=2025)
    assert parsed.rows[0].note == "TH"
    assert parsed.rows[0].norm_qty == 1.5


def test_no_period_means_no_verdict(tmp_path):
    """Không biết kỳ thì không kết luận giá trị nào là lạ — thà im còn hơn báo sai."""
    path = _write_m16(tmp_path / "m16.xlsx", ["TH", "rác"])
    parsed = parse_m16(path, sheet="BCTT39")
    assert parsed.issues.unknown_note_codes == {}


def test_explicit_period_to_wins_over_the_year(tmp_path):
    """DN niên độ lệch: kỳ nhãn 2025 kết thúc 31/03/2026 → đã thuộc TT 121."""
    path = _write_m16(tmp_path / "m16.xlsx", ["TH"])
    parsed = parse_m16(path, sheet="BCTT39", year=2025, period_to=date(2026, 3, 31))
    assert parsed.issues.unknown_note_codes == {}
