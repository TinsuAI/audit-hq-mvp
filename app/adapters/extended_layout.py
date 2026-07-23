"""Suy map cột cho bố cục Mẫu 15/15a mở rộng, chứng minh bằng đẳng thức của biểu.

Một số DN chèn thêm cột (Mã kế toán) và tách một trường thành nhiều cột con
(`Nhập` → `(6a)`..`(6d)` + Tổng). Đọc bằng vị trí cột cố định thì mọi trường sai.

Bản thân file mang sẵn map: **dòng đánh số** `(1) (2) … (12)` gắn số biểu với cột,
và **cột tổng tự ghi công thức** dạng `(11)=(5)+(6)-(7)-(8)-(9)-(10)`. Map suy ra
phải làm đẳng thức đó đúng trên gần như mọi dòng, nếu không → báo lỗi, không nạp bừa.
Xem ADR #15.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.adapters._common import to_float, to_str

# Số biểu → trường, CỐ ĐỊNH theo Mẫu 15 TT39 (đã đo: 006 nén lẫn 004 mở rộng đều
# dùng cùng đẳng thức (11)=(5)+(6)-(7)-(8)-(9)-(10) với cùng ngữ nghĩa).
_M15_FORM_FIELD = {
    "2": "material_code",
    "3": "material_name",
    "4": "unit",
    "5": "opening_qty",
    "6": "import_qty",
    "7": "reexport_qty",
    "8": "repurpose_qty",
    "9": "production_out_qty",
    "10": "other_out_qty",
    "11": "closing_qty",
}
_M15_NUMERIC = ("opening_qty", "import_qty", "reexport_qty", "repurpose_qty",
                "production_out_qty", "other_out_qty", "closing_qty")

_MATCH_RATE = 0.98  # đẳng thức phải đúng ≥98% dòng dữ liệu mới nhận map


@dataclass
class ColMap:
    """Trường → cột(s). Đọc một trường có thể là CỘNG nhiều cột con (vd (6)=6a+..+6d)."""

    cols: dict[str, list[int]] = field(default_factory=dict)
    header_row: int = 0
    data_start: int = 0

    def value(self, row: list[Any], fieldname: str) -> float:
        return sum(to_float(row[c]) for c in self.cols.get(fieldname, ()) if c < len(row))

    def has(self, fieldname: str) -> bool:
        return fieldname in self.cols


_NUM_RE = re.compile(r"\(?(\d{1,2})([a-z]*)\)?")


def parse_numbering_row(
    cells: list[list[Any]], scan: int = 16
) -> tuple[int | None, dict[str, int], dict[str, list[int]], str | None]:
    """Tìm dòng đánh số. Trả (row, {số: cột}, {số gốc: [cột con]}, công thức|None).

    Chịu được nhãn hỏng: `-6` (thiếu ngoặc) vẫn nhận là số 6; `(6a)`..`(6d)` gom vào
    nhóm gốc "6". Nhận diện dòng khi có ≥5 ô khớp mẫu `(\\d+[a-z]*)`.
    """
    for ri in range(min(scan, len(cells))):
        direct: dict[str, int] = {}
        parts: dict[str, list[int]] = {}
        formula: str | None = None
        hits = 0
        for ci, v in enumerate(cells[ri]):
            s = to_str(v)
            if not s:
                continue
            m = re.match(r"^[(\-]\s*(\d{1,2})([a-z]*)\)?", s)
            if not m:
                continue
            hits += 1
            base, suffix = m.group(1), m.group(2)
            if suffix:
                parts.setdefault(base, []).append(ci)
            else:
                direct[base] = ci
            if "=" in s:
                formula = s
        if hits >= 5:
            return ri, direct, parts, formula
    return None, {}, {}, None


def _col_for(form: str, direct: dict[str, int], parts: dict[str, list[int]]) -> list[int] | None:
    """Cột cho một số biểu: cột trực tiếp nếu có, nếu không thì các cột con của nó."""
    if form in direct:
        return [direct[form]]
    if form in parts:
        return list(parts[form])
    return None


def parse_formula(formula: str) -> tuple[str | None, list[tuple[int, str]]]:
    """`(11)=(5)+(6)-(7)-(8)-(9)-(10)` → ('11', [(+1,'5'),(+1,'6'),(-1,'7'),...]).

    Bỏ hậu tố chữ trong số hạng (`(6abcd)` → '6', đã có ở parts). `-12` sau công thức
    (nhãn cột kế) không phải số hạng — cắt tại dấu `=` đầu.
    """
    if "=" not in formula:
        return None, []
    lhs, rhs = formula.split("=", 1)
    lm = _NUM_RE.search(lhs)
    target = lm.group(1) if lm else None
    # Số hạng ĐẦU thường không có dấu: `(5)+(6)-...`. Gắn dấu vào từng số hạng, số
    # hạng nào không có dấu đứng trước coi là cộng.
    terms: list[tuple[int, str]] = []
    for m in re.finditer(r"([+-]?)\s*\(?(\d{1,2})[a-z]*\)?", rhs):
        sign_str, num = m.group(1), m.group(2)
        if not num:
            continue
        terms.append((-1 if sign_str == "-" else 1, num))
    return target, terms


def _identity_match_rate(
    cells: list[list[Any]], data_start: int,
    target_cols: list[int], terms: list[tuple[int, list[int]]], code_cols: list[int],
) -> float:
    checked = ok = 0
    for row in cells[data_start:]:
        if not any(to_str(row[c]) for c in code_cols if c < len(row)):
            continue
        checked += 1
        acc = 0.0
        for sign, cols in terms:
            acc += sign * sum(to_float(row[c]) for c in cols if c < len(row))
        tgt = sum(to_float(row[c]) for c in target_cols if c < len(row))
        if abs(acc - tgt) < max(0.01, abs(tgt) * 1e-6):
            ok += 1
    return (ok / checked) if checked else 0.0


def resolve_m15(cells: list[list[Any]]) -> ColMap | None:
    """Map cột Mẫu 15 suy từ dòng đánh số, chứng minh bằng đẳng thức. None nếu không xác thực."""
    ri, direct, parts, formula = parse_numbering_row(cells)
    if ri is None or not formula:
        return None
    cmap = ColMap(header_row=ri, data_start=ri + 1)
    for form, fieldname in _M15_FORM_FIELD.items():
        cols = _col_for(form, direct, parts)
        if cols is not None:
            cmap.cols[fieldname] = cols
    code_cols = cmap.cols.get("material_code")
    if not code_cols or not all(cmap.has(f) for f in ("opening_qty", "closing_qty")):
        return None

    target, raw_terms = parse_formula(formula)
    if target != "11" or not raw_terms:
        return None
    terms: list[tuple[int, list[int]]] = []
    for sign, num in raw_terms:
        cols = _col_for(num, direct, parts)
        if cols is None:
            return None
        terms.append((sign, cols))
    tgt_cols = _col_for("11", direct, parts)
    if tgt_cols is None:
        return None

    rate = _identity_match_rate(cells, cmap.data_start, tgt_cols, terms, code_cols)
    if rate < _MATCH_RATE:
        return None
    return cmap


def select_extended_m15(path, year: int | None = None) -> tuple[str, ColMap] | None:
    """Sheet + map cột cho workbook Mẫu 15 bố cục mở rộng. None nếu không sheet nào xác thực.

    Chỉ gọi khi đường cột cố định (`select_sheet`) đã trượt. Trong các sheet xác thực
    được bằng đẳng thức, chọn theo kỳ báo cáo khớp `year` trước, rồi tới số dòng.
    """
    import pandas as pd

    from app.adapters._common import normalize_code, parse_company_header

    xls = pd.ExcelFile(path)
    candidates: list[tuple[int, int, str, ColMap]] = []
    for name in xls.sheet_names:
        cells = pd.read_excel(xls, sheet_name=name, header=None).values.tolist()
        cmap = resolve_m15(cells)
        if cmap is None:
            continue
        h = parse_company_header(cells, scan_rows=14)
        rank = 0
        if h.period_from is not None:
            if h.period_from.year == year:
                rank = 2
            elif h.period_to is not None and h.period_from.year <= (year or -1) <= h.period_to.year:
                rank = 1
        n = sum(
            1 for r in cells[cmap.data_start:]
            if any(c < len(r) and normalize_code(to_str(r[c])) for c in cmap.cols["material_code"])
        )
        candidates.append((rank, n, name, cmap))
    if not candidates:
        return None
    candidates.sort(key=lambda t: (-t[0], -t[1]))
    _, _, name, cmap = candidates[0]
    return name, cmap


__all__ = [
    "ColMap",
    "parse_formula",
    "parse_numbering_row",
    "resolve_m15",
    "select_extended_m15",
]
