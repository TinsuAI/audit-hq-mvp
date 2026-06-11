"""_format_cell — số rất nhỏ (định mức tiêu hao) không bị làm tròn về 0.00."""

from __future__ import annotations

from app.routes.companies import _format_cell


def test_small_number_not_rounded_to_zero():
    # Định mức ~0.0018 kg/sp: phải hiện giá trị thật, không phải "0.00".
    assert _format_cell(0.0018676776, "num") == "0.00186768"
    assert _format_cell(0.00200976, "num") == "0.00200976"
    assert _format_cell(-0.0018, "num") == "-0.0018"


def test_normal_numbers_unchanged():
    assert _format_cell(0.0, "num") == "0"
    assert _format_cell(5.0, "num") == "5"
    assert _format_cell(92.0, "num") == "92"
    assert _format_cell(1234.5, "num") == "1,234.50"
    assert _format_cell(0.5, "num") == "0.50"
    assert _format_cell(0.05, "num") == "0.05"


def test_non_num_passthrough():
    assert _format_cell(None, "num") == ""
    assert _format_cell("ADD", "code-cell") == "ADD"
