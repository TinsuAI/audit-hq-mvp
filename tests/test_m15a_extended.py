"""Mẫu 15a bố cục mở rộng: đẳng thức cân đối làm cổng + export_qty theo NHÃN (ADR #15).

Kiểu hỏng nguy hiểm: map trông hợp lý nhưng export_qty sai cột → C4.3/C1.4 ra số sai
âm thầm. Các test ở đây khoá: (1) chọn đúng cột xuất khẩu giữa nhiều cột xuất-khác,
(2) khai triển nhãn gộp `(8ab)`, (3) từ chối khi mơ hồ / đẳng thức sai.
"""

from __future__ import annotations

from app.adapters.extended_layout import (
    parse_formula_terms,
    resolve_m15a,
)

_N = 16


def _plain_grid(*, second_export_label: bool = False, break_balance: bool = False):
    """EPE-like: số biểu phẳng (8)(9)(10) + cột con decoy (8a)(8c)(9c). export = biểu (9)."""
    grid = [[None] * _N for _ in range(5)]
    labels = [None] * _N
    labels[9] = "Lượng SP đăng ký tờ khai năm trước, năm nay xuất kho\nLast year export"
    labels[10] = "Lượng SP đăng ký tờ khai và xuất kho năm nay\nExport this year"
    labels[11] = "Lượng SP xuất bán cho DNCX khác không TTHQ\nOutput without customs"
    labels[13] = "Lượng SP xuất cho nghiên cứu sản phẩm, hư hỏng\nresearch, damage"
    if second_export_label:
        labels[8] = "Lượng sản phẩm xuất khẩu"  # cột trừ khác cũng mang nhãn export → mơ hồ
    grid.append(labels)  # row 5
    numbering = [None] * _N
    for col, tok in {
        0: "(1)", 2: "(2)", 3: "(3)", 4: "(4)", 5: "(5)", 6: "(6)", 7: "(7)",
        8: "(8)", 9: "(8a)", 10: "(9)", 11: "(8c)", 13: "(10)", 14: "(9c)",
        15: "(11) = (5) +(6) +(7) -(8) - (9)-(10)",
    }.items():
        numbering[col] = tok
    grid.append(numbering)  # row 6
    for i in range(3):
        row = [None] * _N
        row[0], row[2], row[3], row[4] = i + 1, f"SP{i}", f"Name{i}", "PCE"
        # open100 +(6)10 +(7)5 -(8)3 -(9=export)80 -(10)2 -> close 30
        row[5], row[6], row[7], row[8], row[10], row[13] = 100, 10, 5, 3, 80, 2
        row[9], row[11], row[14] = 999, 888, 777  # cột con NGOÀI đẳng thức
        row[15] = 999 if break_balance else 30
        grid.append(row)
    return grid


def test_export_chosen_by_label_among_many_out_columns():
    res = resolve_m15a(_plain_grid())
    assert res is not None
    assert res.cols["export_qty"] == [10]           # "Export this year", KHÔNG phải năm trước/nghiên cứu
    assert res.cols["product_code"] == [2]
    assert res.cols["opening_qty"] == [5]
    assert res.cols["closing_qty"] == [15]
    assert (res.matched, res.checked) == (3, 3)
    assert "export this year" in (res.export_label or "")


def test_rejects_when_two_columns_match_export_label():
    # Hai cột trừ cùng mang nhãn export → không dám chọn → không nạp (thà thiếu hơn sai).
    assert resolve_m15a(_plain_grid(second_export_label=True)) is None


def test_rejects_when_balance_identity_fails():
    assert resolve_m15a(_plain_grid(break_balance=True)) is None


def _grouped_grid():
    """GC-like: nhãn gộp `(6ab) (8ab) (9abc)`. export = (8b); (8c) NGOÀI đẳng thức."""
    grid = [[None] * _N for _ in range(5)]
    labels = [None] * _N
    labels[6] = "Lượng SP sản xuất nhập kho\nInput from Production"
    labels[7] = "Lượng SP đã xuất khẩu bị khách hàng trả lại\nReturn from Customer"
    labels[9] = "Lượng SP đăng ký tờ khai năm trước\nLast year"
    labels[10] = "Lượng SP đăng ký tờ khai và xuất kho năm nay\nExport this year"
    labels[11] = "Lượng SP xuất bán cho DNCX khác\nOutput without customs"
    grid.append(labels)  # row 5
    numbering = [None] * _N
    for col, tok in {
        0: "(1)", 2: "(2)", 3: "(3)", 4: "(4)", 5: "(5)", 6: "(6a)", 7: "(6b)",
        8: "(7)", 9: "(8a)", 10: "(8b)", 11: "(8c)", 12: "(9a)", 13: "(9b)", 14: "(9c)",
        15: "(10) = (5) +(6ab) -(7) -(8ab) - (9abc)",
    }.items():
        numbering[col] = tok
    grid.append(numbering)  # row 6
    for i in range(2):
        row = [None] * _N
        row[0], row[2], row[3], row[4] = i + 1, f"SP{i}", f"Name{i}", "PCE"
        # open100 +(6a)4+(6b)6 -(7)3 -(8a)5-(8b=export)90 -(9a)1-(9b)1-(9c)0  -> close 10
        row[5] = 100
        row[6], row[7] = 4, 6
        row[8] = 3
        row[9], row[10], row[11] = 5, 90, 500  # (8c)=500 NGOÀI đẳng thức (nếu gộp nhầm sẽ vỡ)
        row[12], row[13], row[14] = 1, 1, 0
        row[15] = 10
        grid.append(row)
    return grid


def test_grouped_labels_expand_to_exact_subcolumns():
    res = resolve_m15a(_grouped_grid())
    assert res is not None, "khai triển (8ab) phải bỏ (8c) — nếu gộp cả (8c) đẳng thức sẽ vỡ"
    assert res.cols["export_qty"] == [10]           # (8b) = Export this year
    assert (res.matched, res.checked) == (2, 2)


def test_parse_formula_terms_keeps_letter_groups():
    target, terms = parse_formula_terms("(10) = (5) +(6ab) -(7) -(8ab) - (9abc)")
    assert target == "10"
    assert terms == [
        (1, "5", ""), (1, "6", "ab"), (-1, "7", ""), (-1, "8", "ab"), (-1, "9", "abc"),
    ]
