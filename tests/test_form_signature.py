"""Vân tay form — bất biến hash (WS1-3, ADR #18).

Chứng minh: cùng bố cục khác NĂM → cùng vân tay; đổi số cột / hoán vị / thêm nhãn →
vân tay khác; mã DN (dòng metadata đầu file) KHÔNG ảnh hưởng.
"""

from __future__ import annotations

from app.adapters.form_signature import (
    compute_form_signature,
    fold_label,
    form_signature,
)

# --- hàm hash thuần (labels, col_count, numbering) --------------------------

def test_year_stripped_same_signature():
    a = form_signature(["Tồn đầu kỳ 2024", "Nhập trong kỳ 2024"], 2)
    b = form_signature(["Tồn đầu kỳ 2025", "Nhập trong kỳ 2025"], 2)
    assert a == b


def test_fold_label_strips_accents_case_year_whitespace():
    assert fold_label("  Lượng NL, VT  tồn kho ĐẦU kỳ 2024 ") == "luong nl, vt ton kho dau ky"


def test_different_col_count_differs():
    labels = ["Mã", "Tồn đầu", "Tồn cuối"]
    assert form_signature(labels, 3) != form_signature(labels, 4)


def test_reordered_labels_differ():
    assert form_signature(["a", "b", "c"], 3) != form_signature(["b", "a", "c"], 3)


def test_added_label_differs():
    assert form_signature(["a", "b"], 2) != form_signature(["a", "b", "c"], 3)


def test_numbering_row_changes_signature():
    labels = ["Mã", "Tồn đầu"]
    assert form_signature(labels, 2) != form_signature(labels, 2, ["(1)", "(2)"])


def test_numbering_marker_folds_missing_paren():
    # "-6" (thiếu ngoặc) và "(6)" gập về cùng marker → cùng vân tay.
    labels = ["a", "b"]
    assert form_signature(labels, 2, ["(6)"]) == form_signature(labels, 2, ["-6)"])


# --- tính từ cells (vùng tiêu đề m15 như dữ liệu thật) ----------------------

def _m15_grid(year: int, company: str, ncols: int = 11, numbering: bool = True,
              prod_hdr: str = "Xuất kho để sản xuất"):
    grid = [[None] * ncols for _ in range(3)]
    grid.append([f"Tên tổ chức: {company}"] + [None] * (ncols - 1))     # metadata DN
    grid.append([f"Kỳ báo cáo: 01/01/{year} - 31/12/{year}"] + [None] * (ncols - 1))
    parent = ["STT", "Mã nguyên liệu, vật tư", "Tên", "ĐVT",
              f"Lượng NL, VT tồn kho đầu kỳ {year}", "Lượng NL, VT nhập trong kỳ",
              "Tái xuất", "Chuyển mục đích sử dụng", prod_hdr, "Xuất khác",
              "Lượng NL, VT tồn kho cuối kỳ"]
    if ncols == 12:  # thêm một cột (Mã kế toán) sau cột mã
        parent = parent[:2] + ["Mã kế toán"] + parent[2:]
    grid.append(parent)                                                 # hrow
    if numbering:
        nums = [f"({i})" for i in range(1, ncols + 1)]
        grid.append(nums)
    for i in range(3):
        row = [i + 1, f"MAT{i}", "Vật tư", "KG", 10, 100, 0, 0, 80, 0, 30]
        if ncols == 12:
            row = row[:2] + ["KT"] + row[2:]
        grid.append(row)
    return grid


def _data_start(grid):
    from app.adapters.layout import find_data_start
    return find_data_start(grid, "m15")


def test_cells_same_layout_two_years_same_signature():
    g24 = _m15_grid(2024, "CÔNG TY A")
    g25 = _m15_grid(2025, "CÔNG TY A")
    assert compute_form_signature(g24, "m15", _data_start(g24)) == \
        compute_form_signature(g25, "m15", _data_start(g25))


def test_cells_dn_code_does_not_affect_signature():
    g_a = _m15_grid(2024, "CÔNG TY A — MST 0101010101")
    g_b = _m15_grid(2024, "DOANH NGHIỆP B KHÁC HẲN — MST 0202020202")
    assert compute_form_signature(g_a, "m15", _data_start(g_a)) == \
        compute_form_signature(g_b, "m15", _data_start(g_b))


def test_cells_extra_column_changes_signature():
    g11 = _m15_grid(2024, "CÔNG TY A", ncols=11)
    g12 = _m15_grid(2024, "CÔNG TY A", ncols=12)
    assert compute_form_signature(g11, "m15", _data_start(g11)) != \
        compute_form_signature(g12, "m15", _data_start(g12))


def test_cells_reordered_header_changes_signature():
    g = _m15_grid(2024, "CÔNG TY A")
    g_swap = _m15_grid(2024, "CÔNG TY A", prod_hdr="Xuất khác khác")
    assert compute_form_signature(g, "m15", _data_start(g)) != \
        compute_form_signature(g_swap, "m15", _data_start(g_swap))


def test_cells_numbering_presence_changes_signature():
    g_num = _m15_grid(2024, "CÔNG TY A", numbering=True)
    g_none = _m15_grid(2024, "CÔNG TY A", numbering=False)
    assert compute_form_signature(g_num, "m15", _data_start(g_num)) != \
        compute_form_signature(g_none, "m15", _data_start(g_none))
