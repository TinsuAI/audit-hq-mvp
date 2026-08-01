"""_format_cell — số rất nhỏ (định mức tiêu hao) không bị làm tròn về 0,00.

Dấu phân cách theo setting `number_format`, mặc định quy ước Việt Nam
(`1.234,56`) — xem `app/formatting.py` và `tests/test_formatting.py`.
"""

from __future__ import annotations

from app.routes.companies import _format_cell


def test_small_number_not_rounded_to_zero():
    # Định mức ~0,0018 kg/sp: phải hiện giá trị thật, không phải "0,00".
    assert _format_cell(0.0018676776, "num") == "0,00186768"
    assert _format_cell(0.00200976, "num") == "0,00200976"
    assert _format_cell(-0.0018, "num") == "-0,0018"


def test_very_small_number_avoids_scientific_notation():
    """`%g` nhả `1.234e-06` ở cỡ này — cán bộ không đọc được ký hiệu mũ."""
    assert _format_cell(0.000001234, "num") == "0,000001234"


def test_normal_numbers_unchanged():
    assert _format_cell(0.0, "num") == "0"
    assert _format_cell(5.0, "num") == "5"
    assert _format_cell(92.0, "num") == "92"
    assert _format_cell(1234.5, "num") == "1.234,50"
    assert _format_cell(0.5, "num") == "0,50"
    assert _format_cell(0.05, "num") == "0,05"


def test_price_column_keeps_four_decimals():
    assert _format_cell(1.5, "price") == "1,5000"


def test_source_file_shows_only_the_file_name():
    """Đường dẫn máy chủ không có lý do gì phải in ra màn hình."""
    assert _format_cell("/srv/data/PILOT/2024/BCQT/M15.xlsx", "file") == "M15.xlsx"


def test_non_num_passthrough():
    assert _format_cell(None, "num") == ""
    assert _format_cell("ADD", "code-cell") == "ADD"
