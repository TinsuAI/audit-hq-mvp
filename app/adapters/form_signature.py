"""Vân tay form — hash CẤU TRÚC vùng tiêu đề một slot (WS1, ADR #18).

Vân tay = danh sách nhãn tiêu đề cột theo THỨ TỰ + số cột, gập hoa/dấu/khoảng
trắng và BỎ chữ số năm; kèm dòng đánh số `(1)(2)…` khi form có. KHÔNG chứa mã DN
(tính từ vùng tiêu đề cột `[hrow, data_start)`, không đụng các dòng metadata DN ở
đầu file). Cùng bố cục khác NĂM → cùng vân tay (bỏ năm) nên map xác nhận tái dùng
chéo năm trong CÙNG DN; đổi số cột / thêm / hoán vị nhãn → vân tay khác.

Map đã xác nhận lưu theo `(DN, slot, vân tay)` (xem `app/pipeline/saved_map.py`).
"""

from __future__ import annotations

import hashlib
import re

from app.adapters._common import to_str
from app.adapters.layout import BALANCE_EXPECT, find_header_columns, norm

_HEADER_DEPTH = 6

# Chữ số năm (1900–2099) — bỏ khỏi nhãn để cùng bố cục khác năm ra cùng vân tay.
_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")

# Ô của dòng đánh số: "(1)", "(6a)", "(11)=(5)+(6)-(7)-(8)".
_NUM_CELL_RE = re.compile(r"^\(\d{1,2}[a-z]?\)(\s*=.*)?$")
# Số biểu đầu tiên trong một ô đánh số → chuẩn hoá về "(n)" (chịu được thiếu ngoặc).
_MARK_RE = re.compile(r"(\d{1,2}[a-z]?)")


def fold_label(text: str | None) -> str:
    """Gập một nhãn tiêu đề: bỏ dấu + hạ chữ + gộp khoảng trắng + bỏ chữ số năm."""
    if text is None:
        return ""
    s = norm(text)
    s = _YEAR_RE.sub("", s)
    return re.sub(r"\s+", " ", s).strip()


def _fold_marker(cell: str | None) -> str:
    """Ô đánh số → marker chuẩn "(n)"; rỗng nếu không phải ô đánh số."""
    if cell is None:
        return ""
    m = _MARK_RE.search(str(cell))
    return f"({m.group(1)})" if m else ""


def form_signature(
    labels: list[str], col_count: int, numbering: list[str] | None = None
) -> str:
    """Hash ổn định từ (nhãn cột theo thứ tự, số cột, dòng đánh số nếu có).

    Nhãn được gập trong hàm (bỏ dấu/hoa/năm) nên hai bố cục chỉ khác năm cho cùng
    vân tay. Số cột + dòng đánh số là thành phần riêng: đổi số cột hay hoán vị nhãn
    đổi vân tay.
    """
    folded = [fold_label(x) for x in labels]
    parts = [f"n={col_count}", "cols=" + "\x1f".join(folded)]
    if numbering:
        marks = [m for m in (_fold_marker(x) for x in numbering) if m]
        if marks:
            parts.append("num=" + " ".join(marks))
    canonical = "\x1e".join(parts)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


def _is_numbering_row(vals: list[str | None]) -> bool:
    non_empty = [v for v in vals if v]
    if len(non_empty) < 2:
        return False
    hits = sum(1 for v in non_empty if _NUM_CELL_RE.match(v))
    return hits >= max(2, len(non_empty) // 2)


def _extract_band(band: list[list]) -> tuple[list[str], int, list[str] | None]:
    """Từ vùng tiêu đề: (nhãn mỗi cột theo thứ tự, số cột, ô dòng đánh số | None)."""
    width = 0
    label_rows: list[list[str | None]] = []
    numbering: list[str] | None = None
    for row in band:
        vals = [to_str(v) for v in row]
        for i, v in enumerate(vals):
            if v:
                width = max(width, i + 1)
        if _is_numbering_row(vals):
            numbering = [v for v in vals if v and _NUM_CELL_RE.match(v)]
        else:
            label_rows.append(vals)
    labels: list[str] = []
    for c in range(width):
        parts = [row[c] for row in label_rows if c < len(row) and row[c]]
        labels.append(" ".join(parts))
    return labels, width, (numbering or None)


def compute_form_signature(cells: list[list], slot: str, data_start: int) -> str:
    """Vân tay form của một sheet đã đọc: neo dòng tiêu đề rồi hash vùng `[hrow, data_start)`.

    Neo vào dòng tiêu đề `find_header_columns` dò được (KHÔNG lấy metadata DN ở đầu
    file). Không dò được thì lùi về `data_start - _HEADER_DEPTH`.
    """
    hrow: int | None = None
    exp = BALANCE_EXPECT.get(slot)
    if exp:
        code_kw = exp["code"][1]
        hrow, _ = find_header_columns(
            cells, code_kw, {k: v[1] for k, v in exp["fields"].items()}
        )
    if hrow is None:
        hrow = max(0, data_start - _HEADER_DEPTH)
    band = cells[hrow:data_start] if data_start > hrow else cells[hrow:hrow + 1]
    labels, col_count, numbering = _extract_band(band)
    return form_signature(labels, col_count, numbering)


__all__ = ["compute_form_signature", "fold_label", "form_signature"]
