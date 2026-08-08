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

# Nhãn NGẮN — đi vào chip ở màn dữ liệu, VÀ đi vào `parse_detail` lúc nạp
# (`data_files.py`). Đổi chuỗi ở đây là đổi dữ liệu đã lưu của mọi file nạp trước, nên
# câu giải nghĩa nằm ở `SOURCE_SENTENCE_VI` bên dưới chứ không viết đè lên đây.
SOURCE_LABEL_VI = {
    OFFICER_CONFIRMED: "Cán bộ xác nhận",
    BUILTIN_TEMPLATE: "Khớp mẫu có sẵn",
    HEADER_MATCHED: "Khớp tiêu đề",
    BALANCE_CHECKED: "Khớp đẳng thức",
    POSITION_ONLY: "Chỉ theo vị trí",
}

# Câu ở DÒNG CỦA TRƯỜNG (#120). Mỗi câu nói hai phần: cơ chế đã dùng, và giới hạn của
# chính cơ chế đó — thuật ngữ trần ("Khớp đẳng thức") không cho cán bộ biết khi nào
# KHÔNG tin được, mà đó mới là lúc họ phải mở file ra đối chiếu. Nội dung lấy từ
# docstring của module này, không phải một cách nói thứ hai dựng riêng cho màn hình.
# Tra lúc render, KHÔNG ghi xuống `parse_detail`: sửa câu chữ là file cũ đọc câu mới.
SOURCE_SENTENCE_VI = {
    OFFICER_CONFIRMED: (
        "Cán bộ đã tự xác nhận cột này cho cấu trúc biểu của doanh nghiệp; "
        "vị trí đã lưu chỉ áp dụng cho file cùng vân tay biểu, bố cục khác thì phải "
        "xác nhận lại."
    ),
    BUILTIN_TEMPLATE: (
        "Khớp vân tay một họ biểu đã dựng sẵn trong hệ thống; cấu trúc đã có người soát "
        "lúc viết mẫu, nhưng mẫu dựng theo biểu chung nên không bắt được sửa đổi riêng "
        "của doanh nghiệp."
    ),
    HEADER_MATCHED: (
        "Tiêu đề ngay tại cột này khớp nhãn mong đợi của trường; chỉ chắc khi người lập "
        "file ghi tiêu đề đúng nghĩa, vì tiêu đề viết tắt hoặc gộp ô thì không dò ra."
    ),
    BALANCE_CHECKED: (
        "Đẳng thức cân đối của biểu khớp khi lấy cột này; đủ cho cột dùng dạng tổng, "
        "nhưng đẳng thức không phân biệt hai cột cùng dấu nên vẫn có thể đang lấy nhầm "
        "cột liền kề."
    ),
    POSITION_ONLY: (
        "Đọc theo chỉ số cột mặc định của biểu, không tín hiệu nào khác xác nhận; "
        "file lệch bố cục thì đọc sai cột mà không có dấu hiệu nào báo."
    ),
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
    "row_no": ("stt", "so tt"),
    "material_name": ("ten nguyen lieu", "ten nvl", "ten npl", "ten vat tu", "ten hang"),
    "unit": ("dvt", "don vi tinh", "don vi"),
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
    "row_no": ("stt", "so tt"),
    "product_name": ("ten sp", "ten thanh pham", "ten san pham", "ten hang"),
    "unit": ("dvt", "don vi tinh", "don vi"),
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

# Từ khoá tiêu đề cho MỌI trường Mẫu 16, không chỉ hai trường có check đọc. Trường
# không dò được từ khoá vẫn có mục bằng chứng (`position-only`) — có mục thì có badge,
# có ô sửa, và cổng review nhìn thấy. Đó là nội dung của #109.
_M16_HDR_KW: dict[str, tuple[str, ...]] = {
    "product_code": ("ma sp", "ma thanh pham", "ma san pham"),
    "product_name": ("ten sp", "ten thanh pham", "ten san pham"),
    "product_unit": ("dvt sp", "don vi tinh sp", "dvt thanh pham", "don vi tinh"),
    "material_code": _M16_CODE_KW,
    "material_name": ("ten npl", "ten nvl", "ten nguyen lieu", "ten vat tu"),
    "material_unit": ("dvt npl", "dvt nvl", "don vi tinh npl", "don vi tinh"),
    "norm_qty": _M16_NORM_KW,
    "note": ("ghi chu", "note"),
}

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


# Cột (0-indexed) đọc trên đường CHUẨN — TOÀN BỘ trường adapter đọc, kể cả cột mô tả.
# Cột mô tả không vào đẳng thức cân đối nhưng vẫn phải có mục bằng chứng: trường không
# có bằng chứng thì không vào `column_map` và cán bộ không có ô sửa (#109).
_M15_COL = {
    "row_no": 0, "material_code": 1, "material_name": 2, "unit": 3,
    "opening_qty": 4, "import_qty": 5, "reexport_qty": 6,
    "repurpose_qty": 7, "production_out_qty": 8, "other_out_qty": 9, "closing_qty": 10,
}
_M15_NUMERIC = ("opening_qty", "import_qty", "reexport_qty", "repurpose_qty",
                "production_out_qty", "other_out_qty", "closing_qty")

_M15A_COL = {
    "row_no": 0, "product_code": 1, "product_name": 2, "unit": 3,
    "opening_qty": 4, "intake_qty": 5, "repurpose_qty": 6,
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


def _balance_over(
    cells: list[list[Any]], data_start: int, cols: dict[str, int],
    code: str, plus: tuple[str, ...], minus: tuple[str, ...], target: str,
) -> bool:
    """Đẳng thức cân đối trên map cột ĐANG dùng. Map thiếu vế nào thì không kết luận."""
    needed = (code, *plus, *minus, target)
    if any(f not in cols for f in needed):
        return False
    return _balance_ok(
        cells, data_start, cols[code],
        [cols[f] for f in plus], [cols[f] for f in minus], cols[target],
    )


def _standard_evidence(
    cells: list[list[Any]], data_start: int, cols: dict[str, int],
    keywords: dict[str, tuple[str, ...]], colmap_hits: set[str],
    balance_fields: tuple[str, ...], balance_ok: bool,
) -> dict[str, str]:
    """Bằng chứng cho MỌI trường trong `cols` — suy TỪ map cột, không từ danh sách viết tay.

    Đổi chiều này là nội dung của #111. Chiều cũ (`evidence` viết tay → `column_map` suy
    từ nó) làm sáu trường Mẫu 16 đi vào cơ sở dữ liệu mà không có badge và không có ô sửa.
    Trường không dò được từ khoá vẫn có mục — `position-only` là một kết luận, không phải
    sự vắng mặt.
    """
    out: dict[str, str] = {}
    for field, col in cols.items():
        if field in colmap_hits or _header_matched(
            cells, data_start, col, keywords.get(field, ())
        ):
            out[field] = HEADER_MATCHED
        elif balance_ok and field in balance_fields:
            out[field] = BALANCE_CHECKED
        else:
            out[field] = POSITION_ONLY
    return out


def evidence_m15_standard(
    cells: list[list[Any]], data_start: int, colmap: dict[str, int] | None = None,
    cols: dict[str, int] | None = None,
) -> dict[str, str]:
    """Nguồn bằng chứng mỗi field cho Mẫu 15 đường CHUẨN (cột cố định)."""
    cols = _M15_COL if cols is None else cols
    return _standard_evidence(
        cells, data_start, cols, _M15_HDR_KW,
        _colmap_hits(colmap, _M15_LABEL_FIELD, cols),
        _M15_NUMERIC,
        _balance_over(
            cells, data_start, cols, "material_code",
            ("opening_qty", "import_qty"),
            ("reexport_qty", "repurpose_qty", "production_out_qty", "other_out_qty"),
            "closing_qty",
        ),
    )


def evidence_m15a_standard(
    cells: list[list[Any]], data_start: int, colmap: dict[str, int] | None = None,
    cols: dict[str, int] | None = None,
) -> dict[str, str]:
    """Nguồn bằng chứng mỗi field cho Mẫu 15a đường CHUẨN (cột cố định)."""
    cols = _M15A_COL if cols is None else cols
    return _standard_evidence(
        cells, data_start, cols, _M15A_HDR_KW,
        _colmap_hits(colmap, _M15A_LABEL_FIELD, cols),
        _M15A_NUMERIC,
        _balance_over(
            cells, data_start, cols, "product_code",
            ("opening_qty", "intake_qty"),
            ("repurpose_qty", "export_qty", "other_out_qty"),
            "closing_qty",
        ),
    )


def evidence_m16(
    cells: list[list[Any]], data_start: int, cols: dict[str, int],
    norm_labeled: bool = False,
) -> dict[str, str]:
    """Nguồn bằng chứng cho Mẫu 16 (không đẳng thức cân đối → chỉ header-matched / position).

    ``norm_labeled`` = cột ĐM thực tế đã chọn theo nhãn "thực tế/actual" (bố cục 004) →
    header-matched hiển nhiên cho riêng cột định mức.
    """
    out = _standard_evidence(
        cells, data_start, cols, _M16_HDR_KW, set(), (), balance_ok=False,
    )
    if norm_labeled and "norm_qty" in out:
        out["norm_qty"] = HEADER_MATCHED
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
    "HEADER_MATCHED",
    "NEEDS_REVIEW",
    "OFFICER_CONFIRMED",
    "POSITION_ONLY",
    "SOURCE_LABEL_VI",
    "SOURCE_SENTENCE_VI",
    "VERIFIED",
    "evidence_m15_extended",
    "evidence_m15_standard",
    "evidence_m15a_extended",
    "evidence_m15a_standard",
    "evidence_m16",
    "strongest",
]
