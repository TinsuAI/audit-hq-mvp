"""Suy map cột Mẫu 15 mở rộng từ dòng đánh số, chứng minh bằng đẳng thức (ADR #15)."""

from __future__ import annotations

from app.adapters.extended_layout import parse_formula, parse_numbering_row, resolve_m15


def test_parse_formula_leading_term_has_no_sign():
    # Số hạng đầu (5) không có dấu -> phải hiểu là cộng, nếu không đẳng thức thiếu tồn đầu.
    target, terms = parse_formula("(11)=(5)+(6)-(7)-(8) - (9) - (10)")
    assert target == "11"
    assert terms == [(1, "5"), (1, "6"), (-1, "7"), (-1, "8"), (-1, "9"), (-1, "10")]


def test_numbering_row_tolerates_broken_label_and_subparts():
    # `-6` (mất ngoặc) vẫn là số 6; (6a)(6b) gom vào nhóm gốc "6".
    cells = [
        ["(1)", "(2)", "(5)", "(6a)", "(6b)", "-6", "(7)", "(11)=(5)+(6)-(7)"],
    ]
    ri, direct, parts, formula = parse_numbering_row(cells)
    assert ri == 0
    assert direct["6"] == 5           # cột "-6" (Tổng)
    assert parts["6"] == [3, 4]       # (6a),(6b)
    assert formula.startswith("(11)")


def _extended_grid():
    """Bố cục mở rộng: chèn Mã kế toán ở c1, tách (6) thành (6a)(6b)+Tổng."""
    grid = [[None] * 12 for _ in range(5)]
    # dòng đánh số: (1)c0 (2)c2 (5)c4 (6a)c5 (6b)c6 (6)c7 (7)c8 (8)c9 (9)c10 (10)c11 ... (11)?
    grid.append(["(1)", "152", "(2)", None, "(5)", "(6a)", "(6b)", "(6)",
                 "(7)", "(8)", "(9)", "(10)"])
    # thiếu (11) trên dòng này; thêm cột (11) riêng
    grid[-1] = grid[-1] + ["(11)=(5)+(6)-(7)-(8)-(9)-(10)"]
    # dữ liệu: open=10, 6a=40,6b=60,tổng=100, tái xuất=0, MĐSD=0, SX=80, khác=0, cuối=30
    for i in range(3):
        grid.append([i + 1, "ACC", f"MAT{i}", None, 10, 40, 60, 100, 0, 0, 80, 0, 30])
    return grid


def test_resolve_m15_reads_total_column_and_verifies():
    m = resolve_m15(_extended_grid())
    assert m is not None
    assert m.cols["material_code"] == [2]      # không phải Mã kế toán ở c1
    assert m.cols["opening_qty"] == [4]
    assert m.cols["import_qty"] == [7]         # cột Tổng (6), không phải (6a)/(6b)
    assert m.cols["production_out_qty"] == [10]
    assert m.cols["closing_qty"] == [12]
    row = [1, "ACC", "MAT0", None, 10, 40, 60, 100, 0, 0, 80, 0, 30]
    assert m.value(row, "import_qty") == 100.0


def test_resolve_m15_rejects_when_identity_fails():
    grid = _extended_grid()
    grid[-1][12] = 999          # tồn cuối sai -> đẳng thức không khớp
    grid[-2][12] = 999
    grid[-3][12] = 999
    assert resolve_m15(grid) is None
