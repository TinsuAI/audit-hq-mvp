"""Chuẩn hoá tên cột + dò dòng tiêu đề cho file BCQT.

Module nằm trong `app/adapters` chứ không phải `app/pipeline/validate` vì validate đã
import ngược lại adapters (`validate.py:16`) — đặt ở đây mới không tạo vòng import,
và adapter cũng cần dùng chung một bộ từ khoá với phần chẩn đoán.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

# field -> (cột chuẩn 0-indexed, từ khoá nhận diện trong ô tiêu đề).
BALANCE_EXPECT: dict[str, dict[str, Any]] = {
    "m15": {
        "data_start": 9,
        "code": (1, ["mã nvl", "mã npl", "mã vật tư", "mã nguyên", "ma nvl"]),
        "fields": {
            "Tồn đầu": (4, ["tồn đầu", "ton dau"]),
            "Nhập trong kỳ": (5, ["nhập", "nhap"]),
            "Xuất sản xuất": (8, ["xuất sản xuất", "đưa vào", "xuat san xuat"]),
            "Tồn cuối": (10, ["tồn cuối", "ton cuoi"]),
        },
    },
    "m15a": {
        "data_start": 9,
        "code": (1, ["mã sp", "mã thành phẩm", "mã sản phẩm", "ma sp"]),
        "fields": {
            "Tồn đầu": (4, ["tồn đầu", "ton dau"]),
            "Nhập kho": (5, ["nhập", "nhap"]),
            "Xuất khẩu": (7, ["xuất khẩu", "xuất", "xuat khau"]),
            "Tồn cuối": (9, ["tồn cuối", "ton cuoi"]),
        },
    },
}

_HEADER_SCAN_ROWS = 25


def norm(s: Any) -> str:
    """Bỏ dấu + hạ chữ thường để so tên cột.

    `đ`/`Đ` là U+0111/U+0110 — ký tự ĐỘC LẬP, không phải d + dấu tổ hợp, nên NFD
    không tách được. Phải thay tay trước, nếu không "Đơn vị tính" ra "đon vi tinh".
    """
    s = str(s).replace("đ", "d").replace("Đ", "D")
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s).strip().lower()


def find_header_columns(
    rows: list[list[Any]], code_kw: list[str], field_kw: dict[str, list[str]]
) -> tuple[int | None, dict[str, int]]:
    """Dò dòng tiêu đề thật + vị trí từng cột theo từ khoá.

    Trả (header_row_idx, {nhãn: col_idx_thực}); (None, {}) nếu không đủ tín hiệu.
    """
    # Ô đã bỏ dấu thì từ khoá cũng phải bỏ dấu — nếu không, mọi từ khoá CÓ dấu
    # không bao giờ khớp.
    all_kw = {
        label: [norm(k) for k in kws]
        for label, kws in {"__code__": code_kw, **field_kw}.items()
    }
    best_row, best_hits, best_map = None, 0, {}
    for ri, raw in enumerate(rows[:_HEADER_SCAN_ROWS]):
        cells = [norm(c) for c in raw]
        found: dict[str, int] = {}
        for label, kws in all_kw.items():
            for ci, cell in enumerate(cells):
                if cell and any(k in cell for k in kws):
                    found[label] = ci
                    break
        if len(found) > best_hits:
            best_hits, best_row, best_map = len(found), ri, found
    if best_hits < 2:
        return None, {}
    return best_row, best_map


__all__ = ["BALANCE_EXPECT", "find_header_columns", "norm"]
