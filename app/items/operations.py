"""Mã loại hình XNK → phân loại nhập/xuất + nhãn tiếng Việt.

Bảng mã loại hình theo Thông tư 38/2015, sửa đổi TT 39/2018.
Tập trung mọi mapping ở đây để các trang detail/aggregation đồng nhất.
"""

from __future__ import annotations

from typing import Literal

OperationKind = Literal["import", "export", "other", "unknown"]


# Mã nhập (tờ khai luồng vào).
IMPORT_CODES: dict[str, str] = {
    "A11": "Nhập kinh doanh tiêu dùng",
    "A12": "Nhập kinh doanh sản xuất",
    "A41": "Nhập kinh doanh của DNCX",
    "E11": "Nhập nguyên liệu của DNCX",
    "E13": "Nhập tạo TSCĐ của DNCX",
    "E15": "Nhập nguyên liệu của DNCX từ nội địa",
    "E21": "Nhập NPL để gia công cho thương nhân nước ngoài",
    "E23": "Nhập NPL gia công từ HĐ khác chuyển sang",
    "E31": "Nhập NPL để sản xuất xuất khẩu",
    "E33": "Nhập NPL vào kho bảo thuế",
    "G11": "Tạm nhập hàng kinh doanh tạm nhập tái xuất",
    "G12": "Tạm nhập máy móc thiết bị thuê mượn",
    "G13": "Tạm nhập miễn thuế khác",
}

# Mã xuất (tờ khai luồng ra). B13 (tái xuất) cũng tính outbound.
EXPORT_CODES: dict[str, str] = {
    "B11": "Xuất kinh doanh",
    "B12": "Xuất sau khi đã tạm nhập",
    "B13": "Xuất trả/Tái xuất",
    "E42": "Xuất sản phẩm của DNCX",
    "E52": "Xuất sản phẩm gia công cho thương nhân nước ngoài",
    "E54": "Xuất nguyên liệu gia công sang HĐ khác",
    "E62": "Xuất sản phẩm sản xuất xuất khẩu",
    "E82": "Xuất nguyên liệu, vật tư thuê gia công ở nước ngoài",
}

# Mã chuyển đổi mục đích / không phải import/export thuần.
OTHER_CODES: dict[str, str] = {
    "A42": "Chuyển tiêu thụ nội địa khác",
    "A43": "Nhập theo chương trình ưu đãi thuế",
}


def classify_operation(code: str | None) -> OperationKind:
    if not code:
        return "unknown"
    if code in IMPORT_CODES:
        return "import"
    if code in EXPORT_CODES:
        return "export"
    if code in OTHER_CODES:
        return "other"
    return "unknown"


def operation_label(code: str | None) -> str:
    if not code:
        return "Không xác định"
    if code in IMPORT_CODES:
        return f"Nhập — {IMPORT_CODES[code]}"
    if code in EXPORT_CODES:
        return f"Xuất — {EXPORT_CODES[code]}"
    if code in OTHER_CODES:
        return OTHER_CODES[code]
    return f"Loại hình {code}"
