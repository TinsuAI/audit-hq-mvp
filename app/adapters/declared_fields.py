"""Tập trường khai theo biểu (ADR #28).

Nguồn sự thật cho màn gán cột: màn hiện MỘT DÒNG mỗi trường khai, kể cả trường máy
không đặt được ở file này. Đối lập với mô hình cũ, nơi `evidence` viết tay quyết định
trường nào có ô nhập — trường không có bằng chứng thì không vào `column_map`, không có
badge, không có ô sửa (#109).

**Tập trường khai = tập trường adapter GHI vào dòng Tầng 1.** Ràng buộc chống trôi ở
`tests/test_declared_fields.py` giữ chiều chặt: mọi khoá trong mọi hằng cột của adapter
phải có mặt ở đây. Chiều ngược để LỎNG có chủ ý — trường khai mà bố cục không có vị trí
mặc định thì tới màn gán ở trạng thái *chưa gán*, không bịa vị trí.

Hai sự thật KHÔNG gộp:
- **bắt buộc theo biểu** (`required`) — biểu mẫu chính thức có cột đó. Sự thật về BIỂU.
- **có check đọc** — suy từ `CHECK_COLUMNS` (`app/checks/registry.py`), ở nguyên chỗ cũ.
  Sự thật về CODE.
Gộp lại thì sửa khai của một check lặng lẽ đổi thứ cán bộ nhìn thấy, và biểu tờ khai —
vốn chưa có mục nào trong registry — bị khai là "không cần trường nào".
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "DECLARED_FIELDS",
    "DeclaredField",
    "FIELD_LABEL_VI",
    "declared",
    "declared_names",
    "label_of",
    "required_fields",
    "row_key_fields",
]


@dataclass(frozen=True)
class DeclaredField:
    """Một trường của một biểu.

    ``row_key`` — thiếu nó thì không dựng được dòng Tầng 1 nào ⇒ TỪ CHỐI file.
    ``required`` mà không ``row_key`` ⇒ nhận file, cảnh báo, đánh dấu thiếu.
    ``multi_column`` — đọc bằng TỔNG nhiều cột con được (bố cục mở rộng `(6a)+(6b)`,
    ADR #25). Chỉ cột lượng mới cộng được; cột mã/tên/đơn vị thì không.
    """

    name: str
    label_vi: str
    required: bool = False
    row_key: bool = False
    multi_column: bool = False


def _key(name: str, label: str) -> DeclaredField:
    return DeclaredField(name, label, required=True, row_key=True)


def _qty(name: str, label: str) -> DeclaredField:
    return DeclaredField(name, label, multi_column=True)


# Mẫu 15 — nhập/xuất/tồn nguyên liệu, vật tư.
_M15 = (
    DeclaredField("row_no", "STT"),
    _key("material_code", "Mã NVL"),
    DeclaredField("material_name", "Tên NVL"),
    DeclaredField("unit", "Đơn vị tính"),
    _qty("opening_qty", "Tồn đầu"),
    _qty("import_qty", "Nhập trong kỳ"),
    _qty("reexport_qty", "Tái xuất"),
    _qty("repurpose_qty", "Chuyển MĐSD"),
    _qty("production_out_qty", "Xuất sản xuất"),
    _qty("other_out_qty", "Xuất khác"),
    _qty("closing_qty", "Tồn cuối"),
)

# Mẫu 15a — nhập/xuất/tồn thành phẩm.
_M15A = (
    DeclaredField("row_no", "STT"),
    _key("product_code", "Mã SP"),
    DeclaredField("product_name", "Tên SP"),
    DeclaredField("unit", "Đơn vị tính"),
    _qty("opening_qty", "Tồn đầu"),
    _qty("intake_qty", "Nhập kho"),
    _qty("repurpose_qty", "Chuyển MĐSD"),
    _qty("export_qty", "Xuất khẩu"),
    _qty("other_out_qty", "Xuất khác"),
    _qty("closing_qty", "Tồn cuối"),
)

# Mẫu 16 — định mức thực tế. Một dòng là ánh xạ một thành phẩm → một nguyên liệu →
# lượng định mức, nên thiếu bất kỳ vế nào trong ba vế đó là dòng vô nghĩa ⇒ ba khoá dòng.
# `product_unit` và `material_unit` là cột (4) và (7) của biểu mẫu chính thức, buộc thống
# nhất với đơn vị tính khai trên tờ khai ở CẢ hai thế hệ văn bản (TT 39/2018 và TT
# 121/2025) → bắt buộc theo biểu, nhưng thiếu vẫn dựng được dòng nên không phải khoá dòng.
_M16 = (
    _key("product_code", "Mã SP"),
    DeclaredField("product_name", "Tên SP"),
    DeclaredField("product_unit", "ĐVT SP", required=True),
    _key("material_code", "Mã NVL"),
    DeclaredField("material_name", "Tên NVL"),
    DeclaredField("material_unit", "ĐVT NVL", required=True),
    _key("norm_qty", "Định mức thực tế"),
    DeclaredField("note", "Ghi chú"),
)

# Tờ khai hải quan (BCCT).
_BCCT = (
    _key("declaration_no", "Số tờ khai"),
    DeclaredField("declaration_date", "Ngày đăng ký"),
    DeclaredField("customs_code", "Mã loại hình"),
    DeclaredField("line_no", "STT hàng"),
    _key("item_code", "Mã NPL/SP"),
    DeclaredField("item_name", "Tên hàng"),
    DeclaredField("hs_code", "Mã HS"),
    DeclaredField("origin", "Xuất xứ"),
    _key("quantity", "Lượng tờ khai"),
    DeclaredField("unit", "Đơn vị tính"),
    DeclaredField("unit_price", "Đơn giá"),
    DeclaredField("currency", "Đơn vị tiền tệ"),
    DeclaredField("value_foreign", "Trị giá nguyên tệ"),
    DeclaredField("value_total", "Tổng trị giá"),
    DeclaredField("tax_total", "Tổng tiền thuế"),
    DeclaredField("partner", "Tên đối tác"),
    DeclaredField("invoice_no", "Số hoá đơn"),
    DeclaredField("company_tax_id", "Mã doanh nghiệp"),
    DeclaredField("company_name", "Tên doanh nghiệp"),
)

DECLARED_FIELDS: dict[str, tuple[DeclaredField, ...]] = {
    "m15": _M15,
    "m15a": _M15A,
    "m16": _M16,
    "bcct": _BCCT,
}


def declared(slot: str) -> tuple[DeclaredField, ...]:
    return DECLARED_FIELDS.get(slot, ())


def declared_names(slot: str) -> set[str]:
    return {f.name for f in declared(slot)}


def row_key_fields(slot: str) -> set[str]:
    return {f.name for f in declared(slot) if f.row_key}


def required_fields(slot: str) -> set[str]:
    return {f.name for f in declared(slot) if f.required}


def label_of(slot: str, name: str) -> str:
    for f in declared(slot):
        if f.name == name:
            return f.label_vi
    return FIELD_LABEL_VI.get(name, name)


def _merged_labels() -> dict[str, str]:
    """Nhãn phẳng field → tiếng Việt, gộp cả bốn biểu.

    Giữ cho những chỗ gọi chỉ có tên trường mà không có slot. Trường trùng tên giữa các
    biểu mang cùng nhãn, trừ `unit`/`row_no` vốn cùng nghĩa — nên gộp không mất thông tin.
    Chỗ nào BIẾT slot thì dùng `label_of(slot, name)`, chính xác hơn.
    """
    out: dict[str, str] = {}
    for fields in DECLARED_FIELDS.values():
        for f in fields:
            out.setdefault(f.name, f.label_vi)
    return out


FIELD_LABEL_VI: dict[str, str] = _merged_labels()
