"""Định dạng số trên giao diện — dấu phân cách, ký hiệu %, đơn vị tiền.

Cán bộ đọc `12.4` không biết đó là 12,4% hay 12,4 đơn vị; đọc `1250000000` phải
đếm chữ số. Test khoá cả ba: phân cách theo quy ước đang chọn, `%` luôn có dấu,
tiền luôn có mã tiền tệ.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.formatting import (
    EMPTY,
    fmt_date,
    fmt_int,
    fmt_money,
    fmt_pct,
    fmt_price,
    fmt_qty,
    group_number,
)


@pytest.mark.parametrize(("value", "decimals", "style", "expected"), [
    (1234.56, 2, "vi", "1.234,56"),
    (1234.56, 2, "en", "1,234.56"),
    (1250000000, 0, "vi", "1.250.000.000"),
    (1250000000, 0, "en", "1,250,000,000"),
    (0, 2, "vi", "0,00"),
    (-42.5, 1, "vi", "-42,5"),
    (999, 0, "vi", "999"),
])
def test_group_number_follows_the_selected_convention(
    value: float, decimals: int, style: str, expected: str
) -> None:
    assert group_number(value, decimals, style=style) == expected


def test_group_number_signs_when_asked() -> None:
    assert group_number(12.4, 1, style="vi", signed=True) == "+12,4"
    assert group_number(-12.4, 1, style="vi", signed=True) == "-12,4"


@pytest.mark.parametrize(("value", "expected"), [
    (1234.0, "1.234"),          # tròn → bỏ phần thập phân
    (1234.5, "1.234,50"),
    (0.0018, "0,0018"),         # rất nhỏ → giữ chữ số có nghĩa, không thành 0,00
    (0.000001234, "0,000001234"),
    (0, "0"),
])
def test_fmt_qty_drops_noise_but_keeps_small_values(value: float, expected: str) -> None:
    assert fmt_qty(value, style="vi") == expected


def test_fmt_qty_appends_the_unit() -> None:
    assert fmt_qty(1234.5, "kg", style="vi") == "1.234,50 kg"
    assert fmt_qty(1234.5, None, style="vi") == "1.234,50"


def test_fmt_pct_always_carries_sign_and_symbol() -> None:
    assert fmt_pct(12.4, style="vi") == "+12,4 %"
    assert fmt_pct(-3.06, style="vi") == "-3,1 %"
    assert fmt_pct(0, style="vi") == "+0,0 %"


def test_fmt_money_always_carries_the_currency() -> None:
    assert fmt_money(1250000000, style="vi") == "1.250.000.000 VND"
    assert fmt_money(1250.4, "USD", style="en") == "1,250 USD"
    assert fmt_money(1250, None, style="vi") == "1.250"


def test_fmt_price_keeps_four_decimals() -> None:
    """Đơn giá NPL hay nhỏ hơn 1 — cắt còn 2 chữ số là mất giá trị thật."""
    assert fmt_price(0.0125, style="vi") == "0,0125"
    assert fmt_price(1.5, "USD", style="vi") == "1,5000 USD"


def test_fmt_int_has_no_decimals() -> None:
    assert fmt_int(1234, style="vi") == "1.234"
    assert fmt_int(1234.7, style="vi") == "1.235"


@pytest.mark.parametrize("fn", [fmt_qty, fmt_int, fmt_money, fmt_pct, fmt_price])
def test_empty_values_render_as_a_dash(fn) -> None:
    assert fn(None) == EMPTY
    assert fn("") == EMPTY


@pytest.mark.parametrize("fn", [fmt_qty, fmt_int, fmt_money, fmt_pct, fmt_price])
def test_non_numeric_passes_through_instead_of_crashing(fn) -> None:
    """Dữ liệu bẩn không được làm vỡ trang — in thô còn hơn 500."""
    assert fn("n/a") == "n/a"


def test_fmt_date_is_day_first() -> None:
    assert fmt_date(date(2025, 3, 12)) == "12/03/2025"
    assert fmt_date(None) == EMPTY


def test_style_defaults_to_the_saved_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    """Không truyền `style` → đọc setting, không phải hằng số cứng trong module."""
    import app.app_settings as st

    monkeypatch.setattr(st, "get_number_format", lambda db=None: "en")
    assert fmt_qty(1234.5) == "1,234.50"
    monkeypatch.setattr(st, "get_number_format", lambda db=None: "vi")
    assert fmt_qty(1234.5) == "1.234,50"
