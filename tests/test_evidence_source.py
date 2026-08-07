"""Nguồn bằng chứng + trạng thái review mỗi cột (WS1, ADR #18).

Gồm ca hoán vị cùng dấu: đổi `production_out`↔`other_out` giữ đẳng thức cân đối
(⇔ C2 xanh) nhưng cột dùng RIÊNG LẺ báo `needs_review` — đẳng thức không phân biệt
hai cột cùng dấu.
"""

from __future__ import annotations

from app.adapters.evidence import (
    BALANCE_CHECKED,
    HEADER_MATCHED,
    NEEDS_REVIEW,
    POSITION_ONLY,
    VERIFIED,
    evidence_m15_extended,
    evidence_m15_standard,
    evidence_m15a_extended,
    evidence_m15a_standard,
    evidence_m16,
    strongest,
)
from app.checks.registry import (
    CHECK_COLUMNS,
    is_consumed,
    is_individually_consumed,
    review_state,
)


# --- Mẫu 15 header hai dòng (cha + con) như dữ liệu thật ---------------------
# col0=STT 1=mã 2=tên 3=đvt 4=tồn đầu 5=nhập 6=tái xuất 7=chuyển MĐSD
# 8=xuất SX 9=xuất khác 10=tồn cuối
def _m15_grid(prod_hdr="Xuất kho để sản xuất", other_hdr="Xuất kho khác",
              prod_col=8, other_col=9):
    grid = [[None] * 11 for _ in range(7)]
    parent = ["STT", "Mã nguyên liệu, vật tư", "Tên nguyên liệu, vật tư", "ĐVT",
              "Lượng NL, VT tồn kho đầu kỳ", "Lượng NL, VT nhập trong kỳ",
              None, None, None, None, "Lượng NL, VT tồn kho cuối kỳ"]
    child = [None, None, None, None, None, None,
             "Tái xuất", "Chuyển mục đích sử dụng", None, None, None]
    child[prod_col] = prod_hdr
    child[other_col] = other_hdr
    grid.append(parent)   # row 7
    grid.append(child)    # row 8
    return grid  # data_start = 9


def _rows_balanced(grid, prod_col=8, other_col=9):
    """3 dòng: tồn cuối = tồn đầu + nhập − tái xuất − chuyển − xuất SX − xuất khác."""
    for i in range(3):
        row = [i + 1, f"MAT{i}", "Vật tư", "KG", 10, 100, 0, 0, 0, 0, 30]
        row[prod_col] = 80   # số bị TRỪ (cùng dấu với xuất khác)
        row[other_col] = 0
        grid.append(row)
    return grid


def test_registry_individually_consumed_set():
    # Đúng 4 cột giá trị dùng riêng lẻ (+ các cột mã khoá).
    assert is_individually_consumed("m15", "production_out_qty")
    assert is_individually_consumed("m15", "repurpose_qty")
    assert is_individually_consumed("m15a", "export_qty")
    assert is_individually_consumed("m16", "norm_qty")
    # Các số hạng cân đối chỉ dùng dạng TỔNG → không riêng lẻ.
    for f in ("opening_qty", "import_qty", "reexport_qty", "other_out_qty", "closing_qty"):
        assert not is_individually_consumed("m15", f), f
    assert is_consumed("m15", "other_out_qty")       # C2.1 đọc (dạng tổng)
    assert not is_consumed("m15", "material_name")   # không check nào đọc


def test_review_state_rules():
    # Cột riêng lẻ: header-matched → verified; balance-checked / position → needs_review.
    assert review_state("m15", "production_out_qty", HEADER_MATCHED) == VERIFIED
    assert review_state("m15", "production_out_qty", BALANCE_CHECKED) == NEEDS_REVIEW
    assert review_state("m15", "production_out_qty", POSITION_ONLY) == NEEDS_REVIEW
    # Cột dạng tổng: balance-checked đủ (verified); position vẫn needs_review.
    assert review_state("m15", "other_out_qty", BALANCE_CHECKED) == VERIFIED
    assert review_state("m15", "other_out_qty", POSITION_ONLY) == NEEDS_REVIEW
    # Cột không check nào đọc → luôn verified.
    assert review_state("m15", "material_name", POSITION_ONLY) == VERIFIED


def test_strongest_prefers_header_over_balance():
    assert strongest(POSITION_ONLY, BALANCE_CHECKED, HEADER_MATCHED) == HEADER_MATCHED
    assert strongest(POSITION_ONLY, BALANCE_CHECKED) == BALANCE_CHECKED


def test_m15_standard_all_header_matched_when_headers_present():
    grid = _rows_balanced(_m15_grid())
    ev = evidence_m15_standard(grid, data_start=9)
    for field, src in ev.items():
        assert src == HEADER_MATCHED, (field, src)
        assert review_state("m15", field, src) == VERIFIED


def test_same_sign_permutation_keeps_c2_green_but_flags_individual_column():
    """Đổi production_out↔other_out (nhãn + số): đẳng thức vẫn khớp (C2 xanh) nhưng
    cột dùng riêng lẻ (production_out) báo needs_review; cột dạng tổng thì verified."""
    # Hoán vị: header col8='Xuất khác', col9='Xuất kho để sản xuất'; số cũng đổi chỗ.
    grid = _m15_grid(prod_hdr="Xuất kho khác", other_hdr="Xuất kho để sản xuất")
    for i in range(3):
        # production 80 nằm ở col9, other 0 ở col8 — cả hai đều TRỪ nên tổng bất biến.
        grid.append([i + 1, f"MAT{i}", "Vật tư", "KG", 10, 100, 0, 0, 0, 80, 30])

    # C2 xanh: đẳng thức khớp mọi dòng (đọc theo vị trí cố định).
    for r in grid[9:]:
        assert abs((r[4] + r[5] - r[6] - r[7] - r[8] - r[9]) - r[10]) < 1e-9

    ev = evidence_m15_standard(grid, data_start=9)
    # production_out (đọc col8, header 'Xuất khác') → không khớp tiêu đề nhưng đẳng thức
    # khớp → balance-checked; dùng riêng lẻ → needs_review.
    assert ev["production_out_qty"] == BALANCE_CHECKED
    assert review_state("m15", "production_out_qty", ev["production_out_qty"]) == NEEDS_REVIEW
    # other_out (đọc col9, header 'Xuất kho để sản xuất') → balance-checked, dạng tổng →
    # verified (đẳng thức đủ cho cột dùng dạng tổng).
    assert ev["other_out_qty"] == BALANCE_CHECKED
    assert review_state("m15", "other_out_qty", ev["other_out_qty"]) == VERIFIED


def test_m15_standard_position_only_when_no_header_and_no_balance():
    # Header thiếu cột SX + đẳng thức KHÔNG khớp → position-only → needs_review.
    grid = _m15_grid(prod_hdr="???", other_hdr="???")
    for i in range(3):
        grid.append([i + 1, f"MAT{i}", "Vật tư", "KG", 10, 100, 0, 0, 5, 0, 999])
    ev = evidence_m15_standard(grid, data_start=9)
    assert ev["production_out_qty"] == POSITION_ONLY
    assert review_state("m15", "production_out_qty", ev["production_out_qty"]) == NEEDS_REVIEW


def test_m15a_standard_export_header_matched():
    # col7 = xuất khẩu. Header đủ → export header-matched → verified.
    grid = [[None] * 10 for _ in range(8)]
    grid.append(["STT", "Mã SP", "Tên", "ĐVT", "Tồn đầu kỳ", "Nhập kho",
                 "Chuyển mục đích", "Lượng SP xuất khẩu", "Xuất khác", "Tồn cuối kỳ"])
    for i in range(3):
        grid.append([i + 1, f"SP{i}", "TP", "PCE", 0, 100, 0, 70, 0, 30])
    ev = evidence_m15a_standard(grid, data_start=9)
    assert ev["export_qty"] == HEADER_MATCHED
    assert review_state("m15a", "export_qty", ev["export_qty"]) == VERIFIED


# Bố cục Mẫu 16 TT39 — khớp `_M16_TT39_COLS`. Bằng chứng nay suy TỪ map cột (#111) nên
# hàm nhận cả map, không chỉ hai cột có check đọc.
_M16_COLS = {
    "product_code": 1, "product_name": 2, "product_unit": 3, "material_code": 4,
    "material_name": 5, "material_unit": 6, "norm_qty": 7, "note": 8,
}


def test_m16_norm_header_matched_and_missing():
    # Có nhãn "thực tế" ở cột định mức → header-matched → verified.
    grid = [[None] * 9 for _ in range(8)]
    grid[7] = [None, None, None, None, "Nguyên liệu, vật tư", None, None,
               "Lượng NL, VT thực tế sử dụng", "Ghi chú"]
    grid.append([1, "SP1", "TP", "PCE", "MAT1", "NPL", "KG", 1.5, None])
    ev = evidence_m16(grid, data_start=8, cols=_M16_COLS)
    assert ev["norm_qty"] == HEADER_MATCHED
    assert review_state("m16", "norm_qty", ev["norm_qty"]) == VERIFIED
    # norm_labeled=True (chọn theo nhãn 004) luôn header-matched dù không quét được.
    ev2 = evidence_m16([[None] * 9], data_start=0, cols=_M16_COLS, norm_labeled=True)
    assert ev2["norm_qty"] == HEADER_MATCHED


def test_m16_evidence_covers_every_mapped_field():
    """#109: sáu trường Mẫu 16 từng đi vào cơ sở dữ liệu KHÔNG có mục bằng chứng nào,
    nên không có badge và không có ô sửa. Bằng chứng nay phủ đúng map cột."""
    grid = [[None] * 9 for _ in range(8)]
    grid[7] = [None, "Mã SP", "Tên SP", "ĐVT SP", "Mã NVL", "Tên NVL", "ĐVT NVL",
               "Lượng NL, VT thực tế sử dụng", "Ghi chú"]
    grid.append([1, "SP1", "TP", "PCE", "MAT1", "NPL", "KG", 1.5, "x"])
    ev = evidence_m16(grid, data_start=8, cols=_M16_COLS)
    assert set(ev) == set(_M16_COLS)
    assert ev["product_code"] == HEADER_MATCHED
    assert ev["note"] == HEADER_MATCHED


def test_extended_evidence_balance_checked_except_export_label():
    m15_ev = evidence_m15_extended(["material_code", "production_out_qty", "closing_qty"])
    assert all(v == BALANCE_CHECKED for v in m15_ev.values())
    # production_out mở rộng chỉ balance-checked → needs_review (đúng ý ADR: bố cục mở rộng
    # không pin được cột cùng dấu, cần cán bộ xác nhận).
    assert review_state("m15", "production_out_qty", m15_ev["production_out_qty"]) == NEEDS_REVIEW

    m15a_ev = evidence_m15a_extended(["opening_qty", "export_qty", "closing_qty"])
    assert m15a_ev["export_qty"] == HEADER_MATCHED   # chọn theo nhãn 'xuất khẩu'
    assert m15a_ev["opening_qty"] == BALANCE_CHECKED
    assert review_state("m15a", "export_qty", m15a_ev["export_qty"]) == VERIFIED


def test_every_registered_column_has_known_field():
    # Vệ sinh registry: consumed_as chỉ nhận individual|sum.
    for uses in CHECK_COLUMNS.values():
        for slot, _field, how in uses:
            assert slot in ("m15", "m15a", "m16")
            assert how in ("individual", "sum")


def test_every_evidence_source_and_field_has_a_vietnamese_label():
    """Badge truy nguồn không được rơi về định danh thô (`position-only`, `norm_qty`).

    `_evidence_columns` tra nhãn bằng `.get(key, key)`; test này chốt nhánh fallback
    không bao giờ chạy với dữ liệu thật.
    """
    from app.adapters.declared_fields import FIELD_LABEL_VI
    from app.adapters.evidence import (
        _RANK,
        REVIEW_LABEL_VI,
        SOURCE_LABEL_VI,
    )
    from app.pipeline.data_files import _EVIDENCE_ORDER

    assert set(_RANK) == set(SOURCE_LABEL_VI)
    assert {VERIFIED, NEEDS_REVIEW} == set(REVIEW_LABEL_VI)
    for slot, fields in _EVIDENCE_ORDER.items():
        missing = set(fields) - set(FIELD_LABEL_VI)
        assert not missing, f"slot {slot} thiếu nhãn cho: {missing}"


def test_evidence_columns_label_every_field_under_every_source():
    """Mọi (cột, nguồn) parser sinh ra đều có nhãn tiếng Việt ở cả hai phía."""
    from app.adapters.evidence import _RANK
    from app.pipeline.data_files import _EVIDENCE_ORDER, _evidence_columns

    for slot, fields in _EVIDENCE_ORDER.items():
        for source in _RANK:
            cols = _evidence_columns(slot, dict.fromkeys(fields, source))
            assert len(cols) == len(fields)
            for c in cols:
                assert c["label"] != c["field"], f"{slot}.{c['field']} còn tên trường thô"
                assert c["evidence_label"] != c["evidence"], (
                    f"{slot}.{c['field']} còn nguồn thô {c['evidence']}"
                )
