"""Nhãn tiếng Việt + cột số cho `finding.details`.

Hai việc test này khoá:
1. Không khoá thô nào (`m15_import`, `diff_pct`) lọt ra màn hình. Bộ khoá đọc
   THẲNG từ mã nguồn các check bằng AST — thêm khoá mới mà quên khai nhãn thì
   test đỏ ngay, không đợi cán bộ nhìn thấy.
2. Mỗi check dựng sẵn có bộ cột riêng, để bảng phát hiện tách số ra cột thay vì
   nhét số vào chuỗi mô tả.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.checks.combos import COMBO_SPECS
from app.checks.detail_labels import (
    DETAIL_FIELDS,
    DETAIL_VALUE_LABELS,
    FINDING_COLUMNS,
    column_headers,
    describe_details,
    row_cells,
)
from app.checks.registry import SPECS

_CHECKS_DIR = Path(__file__).resolve().parent.parent / "app" / "checks"


def _detail_keys_in_source() -> dict[str, set[str]]:
    """Khoá `details` mỗi module check sinh ra, đọc từ AST.

    Bắt cả ba dạng đang dùng trong repo: `details={...}` ở lời gọi `Finding(...)`,
    `details = {...}` gán biến rồi truyền vào, và `details["x"] = ...` gán thêm sau.
    """
    def dict_keys(node: ast.AST) -> set[str]:
        if not isinstance(node, ast.Dict):
            return set()
        return {
            k.value for k in node.keys
            if isinstance(k, ast.Constant) and isinstance(k.value, str)
        }

    found: dict[str, set[str]] = {}
    for path in sorted(_CHECKS_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        keys: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword) and node.arg == "details":
                keys |= dict_keys(node.value)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "details":
                        keys |= dict_keys(node.value)
                    elif (
                        isinstance(target, ast.Subscript)
                        and isinstance(target.value, ast.Name)
                        and target.value.id == "details"
                        and isinstance(target.slice, ast.Constant)
                        and isinstance(target.slice.value, str)
                    ):
                        keys.add(target.slice.value)
        if keys:
            found[path.name] = keys
    return found


def test_ast_scan_actually_finds_keys() -> None:
    """Nếu cách quét hỏng, mọi test dưới thành xanh giả — kiểm nó tìm được đã."""
    found = _detail_keys_in_source()
    assert "c1_quantity.py" in found
    assert "m15_import" in found["c1_quantity.py"]
    assert "ghost_stock" in found["c2_balance.py"], "bỏ sót dạng details['x'] = ..."


def test_every_detail_key_in_the_checks_has_a_label() -> None:
    missing = {
        module: sorted(keys - set(DETAIL_FIELDS))
        for module, keys in _detail_keys_in_source().items()
        if keys - set(DETAIL_FIELDS)
    }
    assert not missing, f"khoá chưa có nhãn tiếng Việt: {missing}"


def test_every_registered_check_has_a_column_spec() -> None:
    """Check dựng sẵn nào cũng phải tách số ra cột; check động (SQL) thì không."""
    missing = sorted(set(SPECS) - set(FINDING_COLUMNS))
    assert not missing, f"check chưa khai bộ cột: {missing}"


def test_every_combo_has_a_column_spec() -> None:
    assert not sorted(set(COMBO_SPECS) - set(FINDING_COLUMNS))


def test_column_keys_all_have_labels() -> None:
    for code, keys in FINDING_COLUMNS.items():
        unknown = sorted(set(keys) - set(DETAIL_FIELDS))
        assert not unknown, f"{code}: cột chưa có nhãn {unknown}"


def test_column_headers_are_vietnamese_with_alignment() -> None:
    headers = column_headers("C1.1")
    assert [h.label for h in headers] == [
        "Giá trị chênh lệch", "Số M15 đối chiếu", "Σ tờ khai", "Chênh lệch", "ĐVT",
        "Cột M15 đối chiếu",
    ]
    assert [h.css for h in headers] == ["num", "num", "num", "num", "", ""]


def test_row_cells_format_numbers_by_kind() -> None:
    cells = row_cells("C1.1", {
        "value_vnd": 500000.0,
        "m15_import": 1234.5, "bcct_sum": 1008.0, "diff_pct": 22.47, "unit": "kg",
        "m15_column": "import_qty",
    }, style="vi")
    assert [c.text for c in cells] == [
        "500.000 VND", "1.234,50", "1.008", "+22,5 %", "kg", "Nhập trong kỳ",
    ]


def test_unpriced_finding_shows_an_empty_money_cell() -> None:
    """`value_vnd` NULL = chưa quy ra tiền được, KHÔNG phải 0 đồng."""
    cells = row_cells("C1.1", {"value_vnd": None, "m15_import": 10.0}, style="vi")
    assert cells[0].text == "—"


def test_header_does_not_claim_import_when_the_column_may_differ() -> None:
    """DN thuê gia công NN đối chiếu `xuất kho để sản xuất`, không phải `nhập`.

    Tiêu đề C1.1 vì thế không được ghi "M15 nhập"; tên cột thật nằm ở cột riêng.
    """
    cells = row_cells("C1.1", {"m15_column": "production_out_qty"}, style="vi")
    assert cells[-1].text == "Xuất kho để sản xuất"
    assert "nhập" not in column_headers("C1.1")[0].label.lower()


def test_every_pairing_column_has_a_label() -> None:
    """Thêm loại hình DN mới vào PAIRING mà quên nhãn cột → test đỏ."""
    from app.checks.company_type import PAIRING

    nvl = {p.nvl_column for p in PAIRING.values()}
    sp = {p.sp_column for p in PAIRING.values()}
    assert nvl <= set(DETAIL_VALUE_LABELS["m15_column"]), (
        f"thiếu nhãn cột M15: {nvl - set(DETAIL_VALUE_LABELS['m15_column'])}"
    )
    assert sp <= set(DETAIL_VALUE_LABELS["m15a_column"]), (
        f"thiếu nhãn cột M15a: {sp - set(DETAIL_VALUE_LABELS['m15a_column'])}"
    )


def test_row_cells_keep_column_count_when_a_key_is_missing() -> None:
    """Finding cũ thiếu khoá mới thêm — bảng phải giữ đúng số cột, không lệch hàng."""
    cells = row_cells("C1.1", {"m15_import": 1.0}, style="vi")
    assert len(cells) == len(column_headers("C1.1"))
    assert cells[-1].text == "—"


def test_row_cells_of_an_unknown_check_are_empty() -> None:
    assert row_cells("C9.9", {"a": 1}) == []
    assert column_headers("C9.9") == []


def test_describe_details_translates_key_and_value() -> None:
    rows = describe_details({"company_type": "GIA_CONG", "diff_pct": -8.2}, style="vi")
    assert rows == [
        {"label": "Loại hình doanh nghiệp", "value": "Gia công"},
        {"label": "Chênh lệch", "value": "-8,2 %"},
    ]


def test_describe_details_renders_lists_readably() -> None:
    rows = describe_details({"import_codes": ["E31", "A12"]})
    assert rows[0]["value"] == "E31, A12"


def test_describe_details_falls_back_to_the_raw_key() -> None:
    """Check động do admin viết sinh khoá tự do — in thô còn hơn nuốt mất."""
    rows = describe_details({"khoa_la": 5})
    assert rows == [{"label": "khoa_la", "value": "5"}]


def test_describe_details_handles_empty() -> None:
    assert describe_details(None) == []
    assert describe_details({}) == []


@pytest.mark.parametrize("key", sorted(DETAIL_VALUE_LABELS))
def test_enum_value_maps_cover_the_real_enums(key: str) -> None:
    """Giá trị enum ra thẳng màn hình (`SAME_FAMILY`) nếu bảng tra thiếu nhánh."""
    real: set[str] = set()
    if key == "company_type":
        from app.checks.company_type import CompanyType
        real = {t.value for t in CompanyType}
    elif key == "uom_match":
        from app.checks.uom import UomMatch
        real = {m.value for m in UomMatch}
    if real:
        assert real <= set(DETAIL_VALUE_LABELS[key]), (
            f"{key}: thiếu nhãn cho {real - set(DETAIL_VALUE_LABELS[key])}"
        )


def test_ghost_stock_reads_as_a_word_not_true() -> None:
    rows = describe_details({"ghost_stock": True})
    assert rows == [{"label": "Tồn ảo", "value": "Có"}]
