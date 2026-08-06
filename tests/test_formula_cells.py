"""Ô công thức bị ghi thành chuỗi JSON thay vì số — đọc đúng giá trị, và đếm lại.

Ca thật: file 006 do cán bộ gộp tay có 2.076 ô dạng `{"formula":"","result":<số>}`
ở ba cột tiền (Đơn giá 377 · Trị giá NT 1.015 · Tổng trị giá 684). `to_float` trả
0.0 cho chuỗi đó → mất 28.563.550.970,35 đ mà số dòng và tập khoá vẫn đúng, không
kiểm tra nào bắt được. Đo ở `.ai/notes/2026-08-06-006-f1-f2-f3-vs-file-gop.md`.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.adapters._common import to_float
from app.adapters.bcct import parse_bcct
from app.pipeline.validate import diagnose_upload
from tests.test_bcct_columns import STANDARD_54, _rows, _write


def _as_formula_cell(value: float) -> str:
    """Ô công thức đúng như bản gộp tay của 006 ghi ra."""
    return json.dumps({"formula": "", "result": value})


def test_to_float_reads_result_from_serialized_formula_cell():
    assert to_float('{"formula":"","result":123.45}') == 123.45


def test_to_float_reads_serialized_formula_with_a_formula_present():
    assert to_float('{"formula":"=SUM(A1:A9)","result":1000}') == 1000.0


def test_to_float_reads_negative_and_zero_results():
    assert to_float('{"formula":"","result":-8.5}') == -8.5
    assert to_float('{"formula":"","result":0}') == 0.0


def test_to_float_keeps_returning_zero_for_a_result_that_is_not_a_number():
    assert to_float('{"formula":"","result":"#REF!"}') == 0.0
    assert to_float('{"formula":"","result":null}') == 0.0


def _bcct_with_formula_money(tmp_path: Path) -> Path:
    """File BCCT chuẩn, riêng ba cột tiền ghi thành chuỗi công thức (2 dòng × 3 cột)."""
    header = list(STANDARD_54)
    rows = _rows(header)
    for row in rows:
        for label in ("Đơn giá", "Trị giá NT", "Tổng trị giá"):
            row[header.index(label)] = _as_formula_cell(row[header.index(label)])
    p = tmp_path / "bcct_formula.xlsx"
    _write(p, header, rows)
    return p


def test_parse_bcct_reads_money_from_serialized_formula_cells(tmp_path):
    parsed = parse_bcct(_bcct_with_formula_money(tmp_path))

    assert len(parsed.rows) == 2
    for row in parsed.rows:
        assert row.unit_price == 1.25
        assert row.value_foreign == 100880.0
        assert row.value_total == 2522000000.0
    # Cột số không phải ô công thức vẫn nguyên.
    assert parsed.rows[0].quantity == 104000.0


def test_parse_bcct_counts_serialized_formula_cells_per_field(tmp_path):
    parsed = parse_bcct(_bcct_with_formula_money(tmp_path))

    assert parsed.issues.formula_cells == {
        "unit_price": 2, "value_foreign": 2, "value_total": 2,
    }
    assert parsed.issues.formula_total == 6
    assert bool(parsed.issues) is True


def test_parse_bcct_reports_no_formula_cells_for_an_ordinary_file(tmp_path):
    header = list(STANDARD_54)
    p = tmp_path / "bcct_clean.xlsx"
    _write(p, header, _rows(header))
    parsed = parse_bcct(p)

    assert parsed.issues.formula_cells == {}
    assert parsed.issues.formula_total == 0


def test_diagnose_upload_warns_about_serialized_formula_cells(tmp_path):
    """Cán bộ phải thấy file đã qua công cụ gộp/xuất — không nạp im lặng."""
    src = _bcct_with_formula_money(tmp_path)
    dest = tmp_path / "DN_F" / "2024" / "HANG_CHI_TIET" / "BaoCaoHangChiTiet.xlsx"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(src.read_bytes())

    diag = diagnose_upload("DN_F", 2024, tmp_path)

    warnings = [d for d in diag.diagnostics if d.level == "warning"]
    text = " ".join(f"{w.title} {w.detail}" for w in warnings)
    assert "6 ô công thức" in text
    assert "Đơn giá ×2" in text and "Tổng trị giá ×2" in text
    # Cảnh báo, KHÔNG chặn nạp: giá trị đã đọc đúng từ `result`.
    assert not diag.has_errors


def test_diagnose_upload_stays_quiet_for_an_ordinary_bcct_file(tmp_path):
    header = list(STANDARD_54)
    dest = tmp_path / "DN_G" / "2024" / "HANG_CHI_TIET" / "BaoCaoHangChiTiet.xlsx"
    _write(dest, header, _rows(header))

    diag = diagnose_upload("DN_G", 2024, tmp_path)

    text = " ".join(f"{d.title} {d.detail}" for d in diag.diagnostics)
    assert "ô công thức" not in text


def test_to_float_leaves_ordinary_values_alone():
    assert to_float(1234.5) == 1234.5
    assert to_float("1,234.5") == 1234.5
    assert to_float("") == 0.0
    assert to_float(None) == 0.0
    assert to_float("không phải số") == 0.0
    # Chuỗi JSON khác — không phải ô công thức thì không nhận.
    assert to_float('{"a":1}') == 0.0
