"""Dò dòng tiêu đề + dòng dữ liệu đầu tiên cho file BCQT.

Các adapter trước đây bắt đầu đọc từ một hằng số (`_DATA_START_ROW`). File thật đặt
dữ liệu ở dòng khác nhau: tiêu đề có thể chiếm hai dòng (dòng cha + dòng con), rồi có
thêm một dòng đánh số `(1) (2) (3)`. Đọc từ hằng số sẽ nuốt các dòng đó thành "dữ liệu"
— mã nguyên liệu ra `'(2)'` hoặc `'Mã sản phẩm xuất khẩu'`.

Module nằm trong `app/adapters` chứ không phải `app/pipeline/validate` vì validate đã
import ngược lại adapters — đặt ở đây mới không tạo vòng import.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from app.adapters._common import to_str

# field -> (cột chuẩn 0-indexed, từ khoá nhận diện trong ô tiêu đề).
# Nguồn sự thật duy nhất cho cả dò tiêu đề (module này) lẫn chẩn đoán (validate.py).
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

# Dòng đánh số dưới tiêu đề: "(1)", "(6a)", "(11)=(5)+(6)-(7)-(8)".
# BẮT BUỘC có ngoặc: dòng dữ liệu thật cũng đầy số nguyên nhỏ (0, 30, 80…), nhận
# diện theo "chữ số trần" sẽ nuốt luôn dòng dữ liệu đầu tiên.
_NUMBERING_RE = re.compile(r"^\(\d{1,2}[a-z]?\)(\s*=.*)?$")

_HEADER_SCAN_ROWS = 25
_MAX_HEADER_DEPTH = 6


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


def _is_numbering_row(values: list[str]) -> bool:
    non_empty = [v for v in values if v]
    if len(non_empty) < 2:
        return False
    hits = sum(1 for v in non_empty if _NUMBERING_RE.match(v))
    return hits >= max(2, len(non_empty) // 2)


def find_data_start(rows: list[list[Any]], slot: str) -> int:
    """Dòng dữ liệu đầu tiên của sheet cân đối (m15 / m15a).

    Dò dòng tiêu đề rồi bỏ qua các dòng tiêu đề con và dòng đánh số ngay dưới nó.
    Không dò được thì trả hằng số cũ — không làm xấu đi file đang parse bình thường.
    """
    exp = BALANCE_EXPECT[slot]
    default = exp["data_start"]
    code_col, code_kw = exp["code"]
    hrow, _ = find_header_columns(
        rows, code_kw, {k: v[1] for k, v in exp["fields"].items()}
    )
    if hrow is None:
        return default

    code_kw_norm = [norm(k) for k in code_kw]
    i = hrow + 1
    while i < len(rows) and i - hrow <= _MAX_HEADER_DEPTH:
        values = [to_str(c) or "" for c in rows[i]]
        cell = values[code_col] if code_col < len(values) else ""
        # Ô gộp chỉ mang giá trị ở ô neo, nên dòng tiêu đề con đọc ra gần như rỗng:
        # phải tiến tới khi cột mã có một mã hàng thật, không chỉ khi dòng rỗng hẳn.
        if not cell:
            i += 1
            continue
        if _NUMBERING_RE.match(cell) or _is_numbering_row(values):
            i += 1
            continue
        # Dòng tiêu đề con: ô ở cột mã vẫn là chữ tiêu đề, không phải mã hàng.
        normalized = norm(cell)
        if normalized and any(k in normalized for k in code_kw_norm):
            i += 1
            continue
        break
    return i


__all__ = [
    "BALANCE_EXPECT",
    "find_data_start",
    "find_header_columns",
    "norm",
]
