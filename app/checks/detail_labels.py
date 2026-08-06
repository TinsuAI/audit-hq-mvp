"""Nhãn tiếng Việt + bộ cột cho `finding.details`.

Khoá trong `details` là ĐỊNH DANH nội bộ (`m15_import`, `diff_pct`) — giữ tiếng
Anh cho khớp phần còn lại của mã nguồn, chuyển sang tiếng Việt lúc render, giống
`app/jobs/result_labels.py`. `tests/test_detail_labels.py` đọc mã nguồn các check
bằng AST và khẳng định mọi khoá đều có nhãn ở đây.

Hai đầu ra khác nhau, đừng lẫn:
- `describe_details()` — TOÀN BỘ khoá, dạng nhãn/giá trị, dùng ở trang chi tiết
  một phát hiện.
- `column_headers()` / `row_cells()` — bộ khoá CHỌN LỌC thành cột số trên bảng
  phát hiện. Bảng gom theo `check_code` nên mỗi nhóm có bộ cột riêng; nhờ vậy bỏ
  được cột "Mô tả" vốn lặp lại y hệt ở mọi dòng.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.formatting import EMPTY, fmt_bool, fmt_int, fmt_pct, fmt_qty

# kind quyết định cách format + căn lề:
#   qty   — số lượng hàng, căn phải
#   pct   — tỷ lệ, luôn có dấu và `%`, căn phải
#   int   — số đếm, căn phải
#   text  — chuỗi
#   list  — danh sách mã, nối bằng dấu phẩy
#   bool  — Có/Không
#   enum  — tra tiếp ở DETAIL_VALUE_LABELS
DETAIL_FIELDS: dict[str, tuple[str, str]] = {
    # --- ngữ cảnh chung ---
    "company_type": ("Loại hình doanh nghiệp", "enum"),
    "unit": ("ĐVT", "text"),
    "reason": ("Lý do", "enum"),
    "detail": ("Chi tiết", "text"),
    # --- C1 số lượng ---
    "m15_import": ("M15 nhập", "qty"),
    "m15a_export": ("M15a xuất", "qty"),
    # Cột M15/M15a đem đối chiếu KHÔNG cố định: DN thuê gia công ở nước ngoài
    # đối chiếu `xuất kho để sản xuất` chứ không phải `nhập trong kỳ`
    # (`app/checks/company_type.py:PAIRING`). Nêu tên cột ra để tiêu đề bảng
    # không nói sai về con số nằm dưới nó.
    "m15_column": ("Cột M15 đối chiếu", "enum"),
    "m15a_column": ("Cột M15a đối chiếu", "enum"),
    "bcct_sum": ("Σ tờ khai", "qty"),
    "diff_pct": ("Chênh lệch", "pct"),
    "import_codes": ("Loại hình nhập", "list"),
    "export_codes": ("Loại hình xuất", "list"),
    "m15_repurpose": ("M15 chuyển MĐSD", "qty"),
    "repurpose": ("Chuyển MĐSD", "qty"),
    "ratio_pct": ("Tỷ lệ chuyển MĐSD", "pct"),
    # --- C2 cân đối kho ---
    "opening": ("Tồn đầu", "qty"),
    "import": ("Nhập trong kỳ", "qty"),
    "intake": ("Nhập kho SX", "qty"),
    "reexport": ("Tái xuất", "qty"),
    "production_out": ("Xuất SX", "qty"),
    "export": ("Xuất khẩu", "qty"),
    "other_out": ("Xuất khác", "qty"),
    "closing_reported": ("Tồn cuối DN khai", "qty"),
    "closing_expected": ("Tồn cuối tính lại", "qty"),
    "closing_qty": ("Tồn cuối", "qty"),
    "diff": ("Chênh lệch", "qty"),
    "ghost_stock": ("Tồn ảo", "bool"),
    # --- C3 phân loại ---
    "nvl_codes": ("Loại hình NVL", "list"),
    "mmtb_codes": ("Loại hình MMTB", "list"),
    "hs_codes": ("Các mã HS", "list"),
    "divergence": ("Khác nhau ở cấp", "enum"),
    "m15_unit": ("ĐVT trên M15", "text"),
    "m15_units": ("Các ĐVT trên M15", "list"),
    "bcct_units": ("ĐVT trên tờ khai", "list"),
    "uom_match": ("Mức khớp đơn vị", "enum"),
    # --- C4 định mức ---
    "m15_opening": ("M15 tồn đầu", "qty"),
    "theoretical_consumption": ("Tiêu hao lý thuyết (M16)", "qty"),
    "actual_m15_production_out": ("Xuất SX thực tế (M15)", "qty"),
    "divergent_norm_products": ("Mã SP có định mức lệch", "list"),
    "norm_source_years": ("Kỳ khai định mức đã dùng", "list"),
    "norm_in_other_book": ("Định mức khai ở sổ khác", "list"),
    "boundary_period": ("Kỳ biên — có thể đã khai trước cửa sổ dữ liệu", "bool"),
    # --- C6 liên kỳ ---
    "current_opening": ("Tồn đầu kỳ này", "qty"),
    "previous_closing": ("Tồn cuối kỳ trước", "qty"),
    # --- tổ hợp ---
    "triggers": ("Kiểm tra kích hoạt", "list"),
    "description": ("Diễn giải", "text"),
    "trigger_finding_ids": ("Mã phát hiện nguồn", "list"),
}

DETAIL_VALUE_LABELS: dict[str, dict[str, str]] = {
    "company_type": {
        "DNCX": "DNCX (doanh nghiệp chế xuất)",
        "GIA_CONG": "Gia công",
        "GIA_CONG_NN": "Thuê gia công ở nước ngoài",
        "SXXK": "SXXK (sản xuất xuất khẩu)",
        "UNKNOWN": "Chưa xác định",
    },
    "uom_match": {
        "equivalent": "Quy đổi được",
        "same_family": "Cùng họ đơn vị",
        "different": "Khác họ đơn vị",
    },
    "divergence": {
        "subheading": "Phân nhóm 6 số",
        "heading": "Nhóm 4 số",
        "chapter": "Chương 2 số",
    },
    "reason": {
        "no_m15": "Không có dòng M15",
        "no_source": "M15 nhập = 0 và tồn đầu = 0",
    },
    # Giá trị là TÊN CỘT trong DB — phải dịch sang tên cột trên biểu mẫu.
    "m15_column": {
        "import_qty": "Nhập trong kỳ",
        "production_out_qty": "Xuất kho để sản xuất",
    },
    "m15a_column": {
        "export_qty": "Xuất khẩu",
        "intake_qty": "Nhập kho từ sản xuất",
    },
}

# Nhãn cột riêng cho từng check, đè lên nhãn mặc định ở DETAIL_FIELDS. Dùng khi
# cùng một khoá mang nghĩa hẹp hơn ở check này: `m15_import` ở C4.1 đúng là "M15
# nhập", nhưng ở C1.1/C1.3 nó là con số của cột đối chiếu — có thể không phải cột
# nhập. Tiêu đề phải nói được cả hai trường hợp.
COLUMN_LABEL_OVERRIDES: dict[str, dict[str, str]] = {
    "C1.1": {"m15_import": "Số M15 đối chiếu"},
    "C1.3": {"m15_import": "Số M15 đối chiếu"},
    "C1.4": {"m15a_export": "Số M15a đối chiếu"},
    # Nhãn đầy đủ ("Kỳ biên — có thể đã khai trước cửa sổ dữ liệu") đủ chỗ ở trang chi
    # tiết, nhưng làm cột bảng rộng gấp đôi các cột số. Bảng rút gọn, chi tiết giữ đủ.
    "C4.9": {"boundary_period": "Kỳ biên"},
}

# Khoá nào lên cột trên bảng phát hiện, theo thứ tự. Chọn lọc — cột nào cũng lên
# thì bảng rộng hơn màn hình mà vẫn không đọc nhanh hơn. Khoá ngữ cảnh
# (`company_type`, `import_codes`) chỉ hiện ở trang chi tiết.
FINDING_COLUMNS: dict[str, tuple[str, ...]] = {
    "C1.1": ("m15_import", "bcct_sum", "diff_pct", "unit", "m15_column"),
    "C1.2": ("bcct_sum", "import_codes"),
    "C1.3": ("m15_import", "import_codes", "m15_column"),
    "C1.4": ("m15a_export", "bcct_sum", "diff_pct", "unit", "m15a_column"),
    "C1.6": ("m15_repurpose",),
    "C1.7": ("repurpose", "opening", "import", "ratio_pct"),
    # C2.x: KHÔNG trải trọn phương trình cân đối ra cột. Mười cột số đẩy hai cột
    # thao tác ra ngoài màn hình, cán bộ phải cuộn ngang mới bấm được. Câu hỏi khi
    # rà soát là "DN khai bao nhiêu, tính lại bao nhiêu, lệch bao nhiêu" — ba số đó
    # lên cột; các thành phần đầu vào nằm ở trang chi tiết và bảng chứng cứ.
    "C2.1": ("closing_reported", "closing_expected", "diff", "ghost_stock"),
    "C2.2": ("closing_reported", "closing_expected", "diff"),
    "C2.3": ("closing_qty", "unit"),
    "C2.4": ("closing_qty", "unit"),
    "C3.1": ("nvl_codes", "mmtb_codes"),
    "C3.2": ("divergence", "hs_codes"),
    "C3.3": ("uom_match", "m15_units", "bcct_units"),
    "C4.1": ("reason", "m15_import", "m15_opening", "norm_source_years"),
    "C4.3": (
        "theoretical_consumption", "actual_m15_production_out", "diff_pct",
        "norm_source_years", "divergent_norm_products",
    ),
    "C4.9": ("intake", "norm_in_other_book", "boundary_period"),
    "C5.1": ("production_out", "import", "opening"),
    "C6.1": ("current_opening", "previous_closing", "diff"),
    "COMBO_FORGED_NORM": ("triggers",),
    "COMBO_UNDECLARED_SOURCE": ("triggers",),
    "COMBO_ACCOUNTING_INCONSISTENT": ("triggers",),
    "COMBO_HS_GAMING": ("triggers",),
}

_NUMERIC_KINDS = frozenset({"qty", "pct", "int"})


@dataclass(frozen=True)
class Column:
    key: str
    label: str
    css: str


@dataclass(frozen=True)
class Cell:
    text: str
    css: str


def _label_and_kind(key: str) -> tuple[str, str]:
    return DETAIL_FIELDS.get(key, (key, "text"))


def _format_value(key: str, kind: str, value: object, style: str | None) -> str:
    if value is None or value == "" or value == [] or value == {}:
        return EMPTY
    if kind == "qty":
        return fmt_qty(value, style=style)
    if kind == "pct":
        return fmt_pct(value, style=style)
    if kind == "int":
        return fmt_int(value, style=style)
    if kind == "bool":
        return fmt_bool(value)
    if kind == "list":
        if isinstance(value, list | tuple):
            return ", ".join(str(v) for v in value)
        return str(value)
    if kind == "enum":
        return DETAIL_VALUE_LABELS.get(key, {}).get(str(value), str(value))
    return str(value)


def column_headers(check_code: str) -> list[Column]:
    """Cột số của một check. Check động (admin tự viết SQL) trả rỗng."""
    overrides = COLUMN_LABEL_OVERRIDES.get(check_code, {})
    columns = []
    for key in FINDING_COLUMNS.get(check_code, ()):
        label, kind = _label_and_kind(key)
        columns.append(Column(key, overrides.get(key, label), _css(kind)))
    return columns


def _css(kind: str) -> str:
    return "num" if kind in _NUMERIC_KINDS else ""


def row_cells(
    check_code: str, details: dict | None, *, style: str | None = None
) -> list[Cell]:
    """Giá trị theo đúng thứ tự cột. Thiếu khoá thì vẫn trả ô rỗng — bảng không lệch."""
    data = details or {}
    cells = []
    for key in FINDING_COLUMNS.get(check_code, ()):
        _label, kind = _label_and_kind(key)
        cells.append(Cell(_format_value(key, kind, data.get(key), style), _css(kind)))
    return cells


def describe_details(
    details: dict | None, *, style: str | None = None
) -> list[dict[str, str]]:
    """Toàn bộ `details` → danh sách `{label, value}` cho trang chi tiết phát hiện.

    Khoá lạ (check động) vẫn hiện, lấy chính khoá làm nhãn — thà thô còn hơn nuốt
    mất dữ liệu cán bộ cần đọc.
    """
    if not details:
        return []
    rows = []
    for key, value in details.items():
        label, kind = _label_and_kind(key)
        rows.append({"label": label, "value": _format_value(key, kind, value, style)})
    return rows
