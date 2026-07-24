"""Mẫu 16: chọn cột ĐM THỰC TẾ khi file tách 'kỹ thuật' vs 'thực tế' (004).

Kiểm tra hải quan dùng định mức thực tế. DN một cột ĐM (6 DN whitelist) phải GIỮ cột
mặc định → kết quả bất biến.
"""

from __future__ import annotations

from app.adapters.m16 import _detect_actual_norm_col


def _grid_with(captions: dict[int, str], data_start: int = 6):
    grid = [[None] * 12 for _ in range(data_start + 2)]
    for col, text in captions.items():
        grid[data_start - 2][col] = text
    return grid


def test_picks_actual_over_technical_when_both_present():
    cells = _grid_with({
        6: "Đơn vị tính\nUnit",
        7: "Định mức kỹ thuật\nTechnical BOM",
        8: "Lượng NL, VT thực tế sử dụng để sản xuất một sp\nActual BOM/ Product",
    })
    col, label, tech = _detect_actual_norm_col(cells, data_start=6, default_col=7)
    assert col == 8
    assert tech == 7
    assert "thực tế" in label


def test_keeps_default_when_single_norm_column():
    # 6 DN whitelist: một cột "Lượng định mức", không có cặp kỹ thuật/thực tế.
    cells = _grid_with({6: "Đơn vị tính", 7: "Lượng định mức"})
    col, label, tech = _detect_actual_norm_col(cells, data_start=6, default_col=7)
    assert (col, label, tech) == (7, None, None)


def test_keeps_default_when_only_technical_labelled():
    cells = _grid_with({7: "Định mức kỹ thuật\nTechnical BOM"})
    col, label, tech = _detect_actual_norm_col(cells, data_start=6, default_col=7)
    assert (col, label, tech) == (7, None, None)
