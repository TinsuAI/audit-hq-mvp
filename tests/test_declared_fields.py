"""Tập trường khai theo biểu — ràng buộc chống trôi (#111, spec #116 story 27).

Adapter thêm một cột mà quên khai thì bộ test phải ĐỎ. Đây là test đáng lẽ đã chặn
được lỗ hổng Mẫu 16 (#109) ngay ngày nó sinh ra: adapter đọc 8 trường, khai 2, và sáu
trường còn lại đi vào cơ sở dữ liệu mà không có dòng nào ở màn gán cột.
"""

import pytest

from app.adapters import bcct, m15, m15a, m16
from app.adapters.declared_fields import (
    DECLARED_FIELDS,
    declared_names,
    label_of,
    row_key_fields,
)

# Mọi hằng vị trí cột của adapter. Hằng ở lại adapter (chúng trả lời "cột nào trong
# bố cục này"), nhưng KHOÁ của chúng phải có mặt trong khai của biểu.
COLUMN_CONSTANTS = [
    ("m15", "_COL", m15._COL),
    ("m15a", "_COL", m15a._COL),
    ("m16", "_M16_TT39_COLS", m16._M16_TT39_COLS),
    ("m16", "_M16_DINHMUC_COLS", m16._M16_DINHMUC_COLS),
    ("bcct", "_COL", bcct._COL),
    ("bcct", "_LABEL_ALIASES", bcct._LABEL_ALIASES),
]


@pytest.mark.parametrize(("slot", "const_name", "const"), COLUMN_CONSTANTS)
def test_every_adapter_column_key_is_declared(slot, const_name, const):
    """Chiều chặt: hằng cột ⊆ khai."""
    undeclared = sorted(set(const) - declared_names(slot))
    assert not undeclared, (
        f"{slot}.{const_name} đọc {undeclared} nhưng biểu {slot} chưa khai. "
        "Trường không khai thì không có dòng ở màn gán cột và cán bộ không sửa được."
    )


def test_declared_field_set_covers_all_four_slots():
    assert set(DECLARED_FIELDS) == {"m15", "m15a", "m16", "bcct"}


@pytest.mark.parametrize("slot", ["m15", "m15a", "m16", "bcct"])
def test_every_declared_field_has_a_vietnamese_label(slot):
    """Màn gán dùng tên tiếng Việt của biểu mẫu chính thức (story 26)."""
    for name in declared_names(slot):
        label = label_of(slot, name)
        assert label and label != name, f"{slot}.{name} chưa có nhãn tiếng Việt"


def test_row_keys_match_the_glossary():
    """Khoá dòng quyết định HẬU QUẢ của trường bắt buộc bị thiếu — từ chối file."""
    assert row_key_fields("m15") == {"material_code"}
    assert row_key_fields("m15a") == {"product_code"}
    assert row_key_fields("m16") == {"product_code", "material_code", "norm_qty"}
    assert row_key_fields("bcct") == {"declaration_no", "item_code", "quantity"}


def test_m16_units_are_required_by_the_form_but_not_row_keys():
    """Cột (4) và (7) của Mẫu 16 bắt buộc theo biểu mẫu chính thức, nhưng thiếu chúng
    vẫn dựng được dòng → nhận file, cảnh báo, đánh dấu thiếu (không từ chối)."""
    required = {f.name for f in DECLARED_FIELDS["m16"] if f.required}
    assert {"product_unit", "material_unit"} <= required
    assert not ({"product_unit", "material_unit"} & row_key_fields("m16"))


def test_row_keys_are_always_required():
    for slot in DECLARED_FIELDS:
        required = {f.name for f in DECLARED_FIELDS[slot] if f.required}
        assert row_key_fields(slot) <= required, slot


def test_bcct_row_keys_agree_with_the_adapter_constant():
    """Hai chỗ nói cùng một điều — nếu lệch thì file bị từ chối theo luật khác nhau."""
    assert row_key_fields("bcct") == set(bcct._REQUIRED_FIELDS)
