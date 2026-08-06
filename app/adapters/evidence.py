"""Nguồn bằng chứng (evidence source) cho mỗi cột parser đọc — nền WS1 (ADR #18).

Mỗi cột đã đọc mang MỘT nguồn, mạnh→yếu:
- ``officer-confirmed`` — cán bộ duyệt / map đã lưu (WS1-3, chưa có nguồn ở ticket này).
- ``builtin-template`` — khớp vân tay một họ biểu đã curate trong code (ADR #23 T3):
  cấu trúc đã được người xem lúc viết template, mạnh hơn khớp tiêu đề tại chỗ nhưng
  yếu hơn map cán bộ tự xác nhận cho chính DN đó.
- ``header-matched`` — tiêu đề tại ĐÚNG vị trí cột khớp nhãn mong đợi (pin đúng cột).
- ``balance-checked`` — đẳng thức cân đối của biểu khớp nếu lấy cột này (số vouch). ĐỦ cho
  cột dùng dạng TỔNG; KHÔNG phân biệt hai cột cùng dấu.
- ``position-only`` — chỉ số cột cố định, không tín hiệu nào khác.

Tính header-matched bằng cách quét vùng tiêu đề TẠI CỘT kỳ vọng, gộp cả dòng tiêu đề cha
lẫn dòng con (tiêu đề Mẫu 15 thật tách hai dòng: cha "Lượng NL, VT…", con "Tái xuất/Xuất kho
để sản xuất/…"). Không đụng `BALANCE_EXPECT` / `find_header_columns` (một dòng) để không dời
điểm chọn sheet — thêm nhãn cột con vào đó làm `find_header_columns` bỏ dòng cha chứa cột mã.
"""

from __future__ import annotations

from typing import Any

from app.adapters._common import to_float, to_str
from app.adapters.layout import norm

# Nguồn bằng chứng — định danh tiếng Anh (KHÔNG dịch), mạnh→yếu.
OFFICER_CONFIRMED = "officer-confirmed"
BUILTIN_TEMPLATE = "builtin-template"
HEADER_MATCHED = "header-matched"
BALANCE_CHECKED = "balance-checked"
POSITION_ONLY = "position-only"

_RANK = {
    POSITION_ONLY: 0,
    BALANCE_CHECKED: 1,
    HEADER_MATCHED: 2,
    BUILTIN_TEMPLATE: 3,
    OFFICER_CONFIRMED: 4,
}

# Trạng thái review (badge gộp hai trạng thái cán bộ hành động).
VERIFIED = "verified"
NEEDS_REVIEW = "needs_review"

SOURCE_LABEL_VI = {
    OFFICER_CONFIRMED: "Cán bộ xác nhận",
    BUILTIN_TEMPLATE: "Khớp mẫu có sẵn",
    HEADER_MATCHED: "Khớp tiêu đề",
    BALANCE_CHECKED: "Khớp đẳng thức",
    POSITION_ONLY: "Chỉ theo vị trí",
}

REVIEW_LABEL_VI = {
    VERIFIED: "Đã kiểm",
    NEEDS_REVIEW: "Cần xác nhận",
}

# Nhãn tiếng Việt cho từng field khi hiện ở badge.
FIELD_LABEL_VI = {
    "material_code": "Mã NVL",
    "product_code": "Mã SP",
    "opening_qty": "Tồn đầu",
    "import_qty": "Nhập trong kỳ",
    "intake_qty": "Nhập kho",
    "reexport_qty": "Tái xuất",
    "repurpose_qty": "Chuyển MĐSD",
    "production_out_qty": "Xuất sản xuất",
    "export_qty": "Xuất khẩu",
    "other_out_qty": "Xuất khác",
    "closing_qty": "Tồn cuối",
    "norm_qty": "Định mức thực tế",
    # BCCT (tờ khai) — tên field không trùng các slot cân đối ở trên.
    "declaration_no": "Số tờ khai",
    "declaration_date": "Ngày đăng ký",
    "customs_code": "Mã loại hình",
    "line_no": "STT hàng",
    "item_code": "Mã NPL/SP",
    "item_name": "Tên hàng",
    "hs_code": "Mã HS",
    "origin": "Xuất xứ",
    "quantity": "Lượng tờ khai",
    "unit": "Đơn vị tính",
    "unit_price": "Đơn giá",
    "currency": "Đơn vị tiền tệ",
    "value_foreign": "Trị giá nguyên tệ",
    "value_total": "Tổng trị giá",
    "tax_total": "Tổng tiền thuế",
    "partner": "Tên đối tác",
    "invoice_no": "Số hoá đơn",
    "company_tax_id": "Mã doanh nghiệp",
    "company_name": "Tên doanh nghiệp",
}


def strongest(*sources: str) -> str:
    """Nguồn mạnh nhất trong các nguồn đưa vào (mặc định position-only)."""
    best = POSITION_ONLY
    for s in sources:
        if s and _RANK.get(s, -1) > _RANK[best]:
            best = s
    return best


# --- header keyword mỗi cột (đã bỏ dấu/hạ chữ như `norm`) ---------------------
# Quét TẠI cột kỳ vọng nên từ khoá rộng vẫn an toàn (không lẫn sang cột khác).
_M15_HDR_KW: dict[str, tuple[str, ...]] = {
    "material_code": ("ma nguyen lieu", "ma nvl", "ma npl", "ma vat tu", "ma nguyen"),
    "opening_qty": ("ton dau", "ton kho dau", "dau ky"),
    "import_qty": ("nhap trong ky", "nhap kho", "nhap"),
    "reexport_qty": ("tai xuat",),
    "repurpose_qty": ("chuyen muc dich",),
    "production_out_qty": ("xuat san xuat", "xuat kho de san xuat", "de san xuat", "dua vao"),
    "other_out_qty": ("xuat khac", "xuat kho khac", "kho khac"),
    "closing_qty": ("ton cuoi", "ton kho cuoi", "cuoi ky"),
}

_M15A_HDR_KW: dict[str, tuple[str, ...]] = {
    "product_code": ("ma sp", "ma thanh pham", "ma san pham"),
    "opening_qty": ("ton dau", "ton kho dau", "dau ky"),
    "intake_qty": ("nhap kho", "nhap trong ky", "nhap"),
    "repurpose_qty": ("chuyen muc dich", "thay doi muc dich"),
    "export_qty": ("xuat khau", "export"),
    "other_out_qty": ("xuat khac", "xuat kho khac", "kho khac"),
    "closing_qty": ("ton cuoi", "ton kho cuoi", "cuoi ky"),
}

# Cột định mức thực tế (norm_qty) + cột mã NVL (material_code, C4.1/C4.3 khoá theo mã này).
_M16_NORM_KW: tuple[str, ...] = (
    "thuc te", "actual", "dinh muc", "luong nl", "luong nguyen", "luong dinh muc", "bom",
)
_M16_CODE_KW: tuple[str, ...] = ("ma npl", "ma nvl", "ma nguyen", "ma vat tu", "nguyen lieu")

_HEADER_DEPTH = 6


def _column_header_text(cells: list[list[Any]], data_start: int, col: int) -> str:
    """Gộp text vùng tiêu đề TẠI một cột (các dòng ngay trên dòng dữ liệu), đã `norm`."""
    parts: list[str] = []
    for r in range(max(0, data_start - _HEADER_DEPTH), data_start):
        if r >= len(cells):
            continue
        s = to_str(cells[r][col]) if col < len(cells[r]) else None
        if s:
            parts.append(norm(s))
    return " ".join(parts)


def _header_matched(cells, data_start: int, col: int, keywords: tuple[str, ...]) -> bool:
    text = _column_header_text(cells, data_start, col)
    return bool(text) and any(norm(k) in text for k in keywords)


def _balance_ok(
    cells: list[list[Any]], data_start: int, code_col: int,
    plus_cols: list[int], minus_cols: list[int], target_col: int, tol: float = 0.01,
) -> bool:
    """Đẳng thức cân đối khớp trên MỌI dòng dữ liệu (⇔ C2 xanh cho file này)."""
    checked = 0
    for row in cells[data_start:]:
        if code_col >= len(row) or not to_str(row[code_col]):
            continue
        checked += 1
        acc = sum(to_float(row[c]) for c in plus_cols if c < len(row))
        acc -= sum(to_float(row[c]) for c in minus_cols if c < len(row))
        tgt = to_float(row[target_col]) if target_col < len(row) else 0.0
        if abs(acc - tgt) > tol:
            return False
    return checked > 0


# Cột (0-indexed) đọc trên đường CHUẨN — khớp `_COL` trong m15.py / m15a.py.
_M15_COL = {
    "material_code": 1, "opening_qty": 4, "import_qty": 5, "reexport_qty": 6,
    "repurpose_qty": 7, "production_out_qty": 8, "other_out_qty": 9, "closing_qty": 10,
}
_M15_NUMERIC = ("opening_qty", "import_qty", "reexport_qty", "repurpose_qty",
                "production_out_qty", "other_out_qty", "closing_qty")

_M15A_COL = {
    "product_code": 1, "opening_qty": 4, "intake_qty": 5, "repurpose_qty": 6,
    "export_qty": 7, "other_out_qty": 8, "closing_qty": 9,
}
_M15A_NUMERIC = ("opening_qty", "intake_qty", "repurpose_qty", "export_qty",
                 "other_out_qty", "closing_qty")

# label BALANCE_EXPECT (colmap) → field, để tận dụng colmap select_sheet đã tính.
_M15_LABEL_FIELD = {
    "__code__": "material_code", "Tồn đầu": "opening_qty", "Nhập trong kỳ": "import_qty",
    "Xuất sản xuất": "production_out_qty", "Tồn cuối": "closing_qty",
}
_M15A_LABEL_FIELD = {
    "__code__": "product_code", "Tồn đầu": "opening_qty", "Nhập kho": "intake_qty",
    "Xuất khẩu": "export_qty", "Tồn cuối": "closing_qty",
}


def _colmap_hits(colmap: dict[str, int] | None, label_field: dict[str, str],
                 expected: dict[str, int]) -> set[str]:
    """Field mà colmap (select_sheet) đã pin ĐÚNG vị trí — cũng tính header-matched."""
    hits: set[str] = set()
    if not colmap:
        return hits
    for label, col in colmap.items():
        field = label_field.get(label)
        if field is not None and expected.get(field) == col:
            hits.add(field)
    return hits


def evidence_m15_standard(
    cells: list[list[Any]], data_start: int, colmap: dict[str, int] | None = None,
) -> dict[str, str]:
    """Nguồn bằng chứng mỗi field cho Mẫu 15 đường CHUẨN (cột cố định)."""
    colmap_hits = _colmap_hits(colmap, _M15_LABEL_FIELD, _M15_COL)
    balance_ok = _balance_ok(
        cells, data_start, _M15_COL["material_code"],
        [_M15_COL["opening_qty"], _M15_COL["import_qty"]],
        [_M15_COL["reexport_qty"], _M15_COL["repurpose_qty"],
         _M15_COL["production_out_qty"], _M15_COL["other_out_qty"]],
        _M15_COL["closing_qty"],
    )
    out: dict[str, str] = {}
    # Mã: header-matched (đường chuẩn buộc cột mã đúng vị trí để select_sheet chấm điểm).
    out["material_code"] = (
        HEADER_MATCHED
        if "material_code" in colmap_hits
        or _header_matched(cells, data_start, _M15_COL["material_code"], _M15_HDR_KW["material_code"])
        else POSITION_ONLY
    )
    for field in _M15_NUMERIC:
        if field in colmap_hits or _header_matched(
            cells, data_start, _M15_COL[field], _M15_HDR_KW[field]
        ):
            out[field] = HEADER_MATCHED
        elif balance_ok:
            out[field] = BALANCE_CHECKED
        else:
            out[field] = POSITION_ONLY
    return out


def evidence_m15a_standard(
    cells: list[list[Any]], data_start: int, colmap: dict[str, int] | None = None,
) -> dict[str, str]:
    """Nguồn bằng chứng mỗi field cho Mẫu 15a đường CHUẨN (cột cố định)."""
    colmap_hits = _colmap_hits(colmap, _M15A_LABEL_FIELD, _M15A_COL)
    balance_ok = _balance_ok(
        cells, data_start, _M15A_COL["product_code"],
        [_M15A_COL["opening_qty"], _M15A_COL["intake_qty"]],
        [_M15A_COL["repurpose_qty"], _M15A_COL["export_qty"], _M15A_COL["other_out_qty"]],
        _M15A_COL["closing_qty"],
    )
    out: dict[str, str] = {}
    out["product_code"] = (
        HEADER_MATCHED
        if "product_code" in colmap_hits
        or _header_matched(cells, data_start, _M15A_COL["product_code"], _M15A_HDR_KW["product_code"])
        else POSITION_ONLY
    )
    for field in _M15A_NUMERIC:
        if field in colmap_hits or _header_matched(
            cells, data_start, _M15A_COL[field], _M15A_HDR_KW[field]
        ):
            out[field] = HEADER_MATCHED
        elif balance_ok:
            out[field] = BALANCE_CHECKED
        else:
            out[field] = POSITION_ONLY
    return out


def evidence_m16(
    cells: list[list[Any]], data_start: int, code_col: int, norm_col: int,
    norm_labeled: bool = False,
) -> dict[str, str]:
    """Nguồn bằng chứng cho Mẫu 16 (không đẳng thức cân đối → chỉ header-matched / position).

    ``norm_labeled`` = cột ĐM thực tế đã chọn theo nhãn "thực tế/actual" (bố cục 004) →
    header-matched hiển nhiên.
    """
    out: dict[str, str] = {}
    out["material_code"] = (
        HEADER_MATCHED
        if _header_matched(cells, data_start, code_col, _M16_CODE_KW)
        else POSITION_ONLY
    )
    if norm_labeled or _header_matched(cells, data_start, norm_col, _M16_NORM_KW):
        out["norm_qty"] = HEADER_MATCHED
    else:
        out["norm_qty"] = POSITION_ONLY
    return out


def evidence_m15_extended(fields: list[str]) -> dict[str, str]:
    """Bố cục MỞ RỘNG Mẫu 15: map suy từ dòng đánh số, chứng minh bằng đẳng thức →
    mọi cột là ``balance-checked`` (đẳng thức không phân biệt hai cột cùng dấu)."""
    return {f: BALANCE_CHECKED for f in fields}


def evidence_m15a_extended(fields: list[str]) -> dict[str, str]:
    """Bố cục MỞ RỘNG Mẫu 15a: đẳng thức vouch mọi cột (balance-checked); RIÊNG
    ``export_qty`` chọn theo NHÃN cột "xuất khẩu/export" → header-matched."""
    out = {f: BALANCE_CHECKED for f in fields}
    if "export_qty" in out:
        out["export_qty"] = HEADER_MATCHED
    return out


__all__ = [
    "BALANCE_CHECKED",
    "FIELD_LABEL_VI",
    "HEADER_MATCHED",
    "NEEDS_REVIEW",
    "OFFICER_CONFIRMED",
    "POSITION_ONLY",
    "REVIEW_LABEL_VI",
    "SOURCE_LABEL_VI",
    "VERIFIED",
    "evidence_m15_extended",
    "evidence_m15_standard",
    "evidence_m15a_extended",
    "evidence_m15a_standard",
    "evidence_m16",
    "strongest",
]
