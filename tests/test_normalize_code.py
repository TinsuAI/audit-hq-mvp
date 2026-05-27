"""Unit test cho normalize_code — reject placeholder phổ biến."""

from __future__ import annotations

import pytest

from app.adapters._common import normalize_code


@pytest.mark.parametrize("raw", [
    None, "", "  ",
    ".", "..", "...", "-", "--",
    "n/a", "N/A", "NaN", "nan",
    "None", "null", "_",
])
def test_junk_returns_none(raw):
    assert normalize_code(raw) is None


@pytest.mark.parametrize("raw,want", [
    ("HA-001", "HA-001"),
    ("  PE12  ", "PE12"),
    ("1", "1"),       # single digit vẫn giữ — có thể là mã hợp lệ ngắn
    ("A", "A"),       # single char chữ vẫn giữ — chỉ junk strings bị loại
    ("24-DE3315", "24-DE3315"),
    ("Mã 8 (tự định nghĩa)", "Mã 8 (tự định nghĩa)"),
])
def test_valid_codes_preserved(raw, want):
    assert normalize_code(raw) == want
