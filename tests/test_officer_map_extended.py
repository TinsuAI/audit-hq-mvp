"""#95 — cán bộ đẩy được vị trí cột qua bố cục MỞ RỘNG, đẳng thức vẫn là cổng.

#84 cố ý không áp map cán bộ cho bố cục mở rộng: ở đó một trường có thể đọc bằng
TỔNG nhiều cột con `(6a)+(6b)`, mà map lưu chỉ giữ được MỘT chỉ số cột. Hệ quả: cán
bộ sửa cột trên file của 004/006 thì không gì được áp, cột cũng không được gắn nhãn
"cán bộ xác nhận", nên file kẹt ở "cần xác nhận" vĩnh viễn.

Bản sửa: map lưu diễn đạt `field → [cột…]`, và sau khi áp vị trí của cán bộ thì
**kiểm lại đẳng thức cân đối của biểu** (ADR #15). Không đạt ngưỡng → ném
``OfficerMapBalanceError``, KHÔNG lặng lẽ quay về map suy được — đọc nhầm cột im
lặng đúng là lớp lỗi đã làm mất 28,5 tỷ.

Bố cục dùng ở đây là hình dạng THẬT của hai DN pilot (đã dựng lại trong
`tests/test_officer_map_precedence.py` và `tests/test_m15a_extended.py`): Mẫu 15 có
cột `Mã kế toán` chèn thêm + `(6)` tách thành `(6a)(6b)` + cột Tổng; Mẫu 15a sổ GC
dùng nhãn gộp `(6ab) (8ab) (9abc)`.
"""

from __future__ import annotations

import pytest

from app.adapters.evidence import BALANCE_CHECKED, OFFICER_CONFIRMED
from app.adapters.extended_layout import OfficerMapBalanceError
from app.adapters.m15 import parse_m15
from app.adapters.m15a import parse_m15a
from app.adapters.templates import MATCH_EXTENDED, MATCH_OFFICER
from tests.test_m15a_extended import _grouped_grid
from tests.test_officer_map_precedence import _m15_extended_grid, _write_grid

# Cột trên `_m15_extended_grid`: (6a)=c5 · (6b)=c6 · Tổng (6)=c7.
_SUB_A, _SUB_B, _TOTAL = 5, 6, 7
# Cột trên `_grouped_grid` (Mẫu 15a sổ GC): (8a)=c9 · (8b)=c10 (xuất khẩu) · (8c)=c11
# nằm NGOÀI đẳng thức; (6a)=c6 · (6b)=c7 là nhóm nhập kho.
_M15A_EXPORT, _M15A_SIBLING, _M15A_OUTSIDE = 10, 9, 11
_M15A_INTAKE = [6, 7]


def _m15_file(tmp_path):
    return _write_grid(tmp_path / "m15x.xlsx", "BCQT_NPL", _m15_extended_grid())


def _m15a_file(tmp_path):
    return _write_grid(tmp_path / "m15ax.xlsx", "BCQT_SP", _grouped_grid())


def _signature(parsed) -> str:
    return parsed.provenance.detail["form_signature"]


# --- (1) Map lưu diễn đạt được một trường ánh xạ tới NHIỀU cột ------------------


def test_extended_map_records_every_column_of_a_group(tmp_path):
    """Map ghi lại phải là CẢ nhóm cột, không phải cột đầu nhóm.

    Màn xác nhận dựng ô nhập từ chính map này; ghi mỗi cột đầu là đưa cho cán bộ một
    bố cục sai để xác nhận.
    """
    parsed = parse_m15(_m15_file(tmp_path))
    column_map = parsed.provenance.detail["column_map"]
    assert column_map["import_qty"] == [_TOTAL]
    assert column_map["closing_qty"] == [12]
    assert parsed.provenance.detail["match_source"] == MATCH_EXTENDED


def test_officer_group_of_subcolumns_is_applied_and_balances(tmp_path):
    """Cán bộ đổi `Nhập trong kỳ` từ cột Tổng sang nhóm `(6a)+(6b)`.

    Cách cài chỉ lấy cột đầu nhóm sẽ đọc 40 thay vì 100 → đẳng thức vỡ → ném lỗi.
    Test này xanh chỉ khi nhóm cột được CỘNG.
    """
    path = _m15_file(tmp_path)
    sig = _signature(parse_m15(path))
    parsed = parse_m15(path, officer_maps={sig: {"import_qty": [_SUB_A, _SUB_B]}})

    assert parsed.rows[0].import_qty == 100.0
    assert parsed.provenance.detail["column_map"]["import_qty"] == [_SUB_A, _SUB_B]
    assert parsed.provenance.evidence["import_qty"] == OFFICER_CONFIRMED
    # Trường cán bộ không đụng vẫn giữ nguồn cũ.
    assert parsed.provenance.evidence["closing_qty"] == BALANCE_CHECKED
    assert parsed.provenance.detail["match_source"] == MATCH_OFFICER
    # Đẳng thức được kiểm LẠI sau khi áp, số đo ghi vào provenance.
    assert parsed.provenance.detail["matched"] == parsed.provenance.detail["checked"] == 3


def test_officer_map_stored_as_single_int_still_applies(tmp_path):
    """Map cũ trong DB lưu `field: int` — vẫn phải hiểu là nhóm một cột."""
    path = _m15_file(tmp_path)
    sig = _signature(parse_m15(path))
    parsed = parse_m15(path, officer_maps={sig: {"closing_qty": 12}})
    assert parsed.rows[0].closing_qty == 30.0
    assert parsed.provenance.evidence["closing_qty"] == OFFICER_CONFIRMED
    assert parsed.provenance.detail["match_source"] == MATCH_OFFICER


def test_officer_map_equal_to_derived_map_changes_nothing(tmp_path):
    """Xác nhận nguyên map đề xuất: cùng số liệu, cùng số đo đẳng thức, không ném.

    Đây là ca thường gặp nhất (cán bộ bấm xác nhận mà không sửa gì) và cũng là mốc
    chứng minh phép kiểm lại đẳng thức dựng đúng: nó phải cho ra cùng kết quả với
    phép chứng minh gốc.
    """
    path = _m15_file(tmp_path)
    base = parse_m15(path)
    sig = _signature(base)
    derived = dict(base.provenance.detail["column_map"])

    parsed = parse_m15(path, officer_maps={sig: derived})
    assert [r.import_qty for r in parsed.rows] == [r.import_qty for r in base.rows]
    assert [r.material_code for r in parsed.rows] == [r.material_code for r in base.rows]
    assert parsed.provenance.detail["matched"] == base.provenance.detail["matched"]
    assert parsed.provenance.detail["checked"] == base.provenance.detail["checked"]
    # Mọi cột trong map lưu đều lên "cán bộ xác nhận" → cổng review clear.
    assert set(parsed.provenance.evidence.values()) == {OFFICER_CONFIRMED}


def test_officer_map_of_another_signature_is_ignored(tmp_path):
    """Khoá map vẫn là (DN, slot, vân tay) — vân tay khác thì không áp."""
    path = _m15_file(tmp_path)
    parsed = parse_m15(path, officer_maps={"vantay-khac": {"import_qty": [_SUB_A]}})
    assert parsed.rows[0].import_qty == 100.0
    assert parsed.provenance.detail["match_source"] == MATCH_EXTENDED


# --- (2) Đẳng thức vỡ sau khi áp map cán bộ → BÁO, không nuốt ------------------


def test_dropping_a_subcolumn_breaks_the_balance_and_is_reported(tmp_path):
    """Cán bộ chỉ `(6a)` mà bỏ `(6b)`: 10+40-80 ≠ 30 → từ chối nạp, nói rõ lý do."""
    path = _m15_file(tmp_path)
    sig = _signature(parse_m15(path))
    with pytest.raises(OfficerMapBalanceError) as err:
        parse_m15(path, officer_maps={sig: {"import_qty": [_SUB_A]}})

    message = str(err.value)
    assert "m15" in message
    assert "import_qty" in message          # trường nào cán bộ chỉ định
    assert "0/3" in message                 # số dòng khớp / số dòng đã kiểm


def test_broken_balance_does_not_fall_back_to_the_derived_map(tmp_path):
    """Không có đường nào lặng lẽ đọc lại map suy được rồi báo "đã nạp xong"."""
    path = _m15_file(tmp_path)
    sig = _signature(parse_m15(path))
    with pytest.raises(OfficerMapBalanceError):
        parse_m15(path, officer_maps={sig: {"import_qty": [_SUB_A]}})


def test_officer_moving_the_code_column_off_data_is_reported(tmp_path):
    """Dời cột mã sang cột rỗng → không dòng nào kiểm được → cũng không nạp."""
    path = _m15_file(tmp_path)
    sig = _signature(parse_m15(path))
    with pytest.raises(OfficerMapBalanceError):
        parse_m15(path, officer_maps={sig: {"material_code": [3]}})


# --- (3) Mẫu 15a sổ GC — nhãn gộp `(6ab) (8ab) (9abc)` -------------------------


def test_m15a_grouped_layout_records_groups(tmp_path):
    parsed = parse_m15a(_m15a_file(tmp_path))
    column_map = parsed.provenance.detail["column_map"]
    assert column_map["intake_qty"] == _M15A_INTAKE
    assert column_map["export_qty"] == [_M15A_EXPORT]


def test_m15a_officer_confirming_the_whole_map_labels_every_column(tmp_path):
    """Xác nhận nguyên map trên file nhãn gộp → mọi cột "cán bộ xác nhận", vẫn cân."""
    path = _m15a_file(tmp_path)
    base = parse_m15a(path)
    sig = _signature(base)
    parsed = parse_m15a(
        path, officer_maps={sig: dict(base.provenance.detail["column_map"])}
    )
    assert parsed.rows[0].export_qty == 90.0
    assert parsed.rows[0].intake_qty == 10.0
    assert set(parsed.provenance.evidence.values()) == {OFFICER_CONFIRMED}
    assert parsed.provenance.detail["match_source"] == MATCH_OFFICER


def test_m15a_officer_column_outside_the_identity_is_reported(tmp_path):
    """Chỉ `export_qty` sang `(8c)` — cột NGOÀI đẳng thức → tổng trừ vọt → từ chối."""
    path = _m15a_file(tmp_path)
    sig = _signature(parse_m15a(path))
    with pytest.raises(OfficerMapBalanceError) as err:
        parse_m15a(path, officer_maps={sig: {"export_qty": [_M15A_OUTSIDE]}})
    assert "export_qty" in str(err.value)


def test_m15a_double_counting_a_column_breaks_the_balance(tmp_path):
    """Chỉ `export_qty` sang `(8a)` mà quên bỏ `(8a)` khỏi `other_out_qty`: cột đó bị
    cộng hai lần ở vế trừ còn `(8b)` rơi ra → đẳng thức vỡ → từ chối."""
    path = _m15a_file(tmp_path)
    sig = _signature(parse_m15a(path))
    with pytest.raises(OfficerMapBalanceError):
        parse_m15a(path, officer_maps={sig: {"export_qty": [_M15A_SIBLING]}})


def test_m15a_swapping_two_columns_of_the_same_sign_still_passes(tmp_path):
    """Ghi lại GIỚI HẠN của cổng đẳng thức, đừng để ai đọc test khác mà tưởng nhầm.

    Đổi `export_qty` từ `(8b)` sang `(8a)` VÀ đổi `other_out_qty` ngược lại giữ nguyên
    TỔNG vế trừ, nên đẳng thức vẫn đúng dù số xuất khẩu đọc ra khác hẳn (5 thay vì 90).
    Đẳng thức là lưới chặn, không phải trọng tài phân biệt hai cột cùng dấu (ADR #18) —
    chính vì thế nhãn cuối cùng là "cán bộ xác nhận" chứ không phải "đã chứng minh".
    """
    path = _m15a_file(tmp_path)
    base = parse_m15a(path)
    sig = _signature(base)
    other_out = base.provenance.detail["column_map"]["other_out_qty"]
    swapped = [_M15A_EXPORT if c == _M15A_SIBLING else c for c in other_out]
    parsed = parse_m15a(
        path,
        officer_maps={sig: {"export_qty": [_M15A_SIBLING], "other_out_qty": swapped}},
    )
    assert parsed.rows[0].export_qty == 5.0
    assert parsed.provenance.evidence["export_qty"] == OFFICER_CONFIRMED
