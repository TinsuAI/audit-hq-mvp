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


class OfficerMapBalanceError(ValueError):
    """Áp vị trí cột của cán bộ vào bố cục mở rộng làm vỡ đẳng thức cân đối của biểu.

    Bố cục mở rộng KHÔNG có nhãn tiêu đề để pin cột — thứ duy nhất chứng minh cách
    đọc là đẳng thức của chính biểu (ADR #15). Map cán bộ vì thế phải qua lại đúng
    cổng đó. Không đạt thì TỪ CHỐI đọc: quay về map suy được mà vẫn báo "đã nạp" là
    đọc một bố cục cán bộ không chọn, im lặng.
    """


@dataclass
class ColMap:
    """Trường → cột(s). Đọc một trường có thể là CỘNG nhiều cột con (vd (6)=6a+..+6d).

    ``identity_target`` / ``identity_terms`` là đẳng thức của biểu viết theo TRƯỜNG
    thay vì theo số biểu, để kiểm lại được sau khi thay vị trí cột (map cán bộ dùng
    tên trường, không dùng số biểu). ``identity_target is None`` = công thức của file
    có số hạng không quy về trường nào → không kiểm lại được → không nhận map cán bộ.
    """

    cols: dict[str, list[int]] = field(default_factory=dict)
    header_row: int = 0
    data_start: int = 0
    formula: str = ""
    checked: int = 0
    matched: int = 0
    code_field: str = "material_code"
    identity_target: str | None = None
    identity_terms: tuple[tuple[int, str], ...] = ()

    def value(self, row: list[Any], fieldname: str) -> float:
        return sum(to_float(row[c]) for c in self.cols.get(fieldname, ()) if c < len(row))

    def has(self, fieldname: str) -> bool:
        return fieldname in self.cols

    @property
    def match_rate(self) -> float:
        return (self.matched / self.checked) if self.checked else 0.0


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
    checked, ok = _identity_counts(cells, data_start, target_cols, terms, code_cols)
    return (ok / checked) if checked else 0.0


def _identity_counts(
    cells: list[list[Any]], data_start: int,
    target_cols: list[int], terms: list[tuple[int, list[int]]], code_cols: list[int],
) -> tuple[int, int]:
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
    return checked, ok


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

    checked, matched = _identity_counts(cells, cmap.data_start, tgt_cols, terms, code_cols)
    if checked == 0 or (matched / checked) < _MATCH_RATE:
        return None
    cmap.formula = formula.strip()
    cmap.checked = checked
    cmap.matched = matched
    # Đẳng thức viết lại theo TRƯỜNG — chỉ giữ khi mọi số hạng quy được về một trường
    # của Mẫu 15; không thì để None và map cán bộ sẽ bị từ chối thay vì áp mà không
    # kiểm lại được.
    fields = [(sign, _M15_FORM_FIELD.get(num)) for sign, num in raw_terms]
    if all(f is not None for _sign, f in fields):
        cmap.identity_target = _M15_FORM_FIELD[target]
        cmap.identity_terms = tuple((sign, f) for sign, f in fields if f is not None)
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


# ---------------------------------------------------------------------------
# Mẫu 15a — bố cục mở rộng. KHÁC Mẫu 15: số biểu KHÔNG ổn định giữa DN, nên
# KHÔNG map field theo số biểu. `export_qty` (cột duy nhất C1.4 dùng) phải
# xác định theo NHÃN cột, và phải là một số hạng TRỪ trong đẳng thức cân đối
# (cổng đẳng thức riêng — ADR #15). Không xác định được → trả None → không nạp.
#   006      : "Lượng sản phẩm xuất khẩu"                       biểu (8)  [thực ra là bố cục CHUẨN]
#   004 EPE  : "…đăng ký tờ khai và xuất kho năm nay / Export this year"  biểu (9)
#   004 GC   : cùng nhãn "Export this year"                     biểu (8b), đẳng thức nhãn gộp

_M15A_EXPORT_INCLUDE = ("xuất khẩu", "export")
_M15A_EXPORT_EXCLUDE = (
    "năm trước", "last year", "chưa đăng ký", "chưa đăng kí", "next year",
    "trả lại", "return", "xuất bán", "dncx", "without customs",
    "nghiên cứu", "research", "hư hỏng", "damage", "mất mát", "loss",
    "thiên tai", "hỏa hoạn", "fire", "xuất kho khác", "other",
)


# Đẳng thức cân đối Mẫu 15a viết theo TRƯỜNG. Đúng theo CÁCH DỰNG của `resolve_m15a`:
# vế cộng được chia hết thành `opening_qty` + `intake_qty`, vế trừ thành `export_qty` +
# `other_out_qty`, nên tổng theo trường bằng đúng tổng theo số hạng của công thức.
_M15A_IDENTITY_TARGET = "closing_qty"
_M15A_IDENTITY_TERMS: tuple[tuple[int, str], ...] = (
    (1, "opening_qty"), (1, "intake_qty"), (-1, "export_qty"), (-1, "other_out_qty"),
)


@dataclass
class M15aResolution:
    """Map cột Mẫu 15a mở rộng đã xác thực + bằng chứng để hiển thị/lưu."""

    cols: dict[str, list[int]]
    header_row: int
    data_start: int
    formula: str
    checked: int
    matched: int
    export_label: str | None = None
    code_field: str = "product_code"
    identity_target: str | None = _M15A_IDENTITY_TARGET
    identity_terms: tuple[tuple[int, str], ...] = _M15A_IDENTITY_TERMS

    def value(self, row: list[Any], fieldname: str) -> float:
        return sum(to_float(row[c]) for c in self.cols.get(fieldname, ()) if c < len(row))

    @property
    def match_rate(self) -> float:
        return (self.matched / self.checked) if self.checked else 0.0


def parse_formula_terms(formula: str) -> tuple[str | None, list[tuple[int, str, str]]]:
    """`(10)=(5)+(6ab)-(7)-(8ab)-(9abc)` → ('10', [(+1,'5',''),(+1,'6','ab'),...]).

    Giữ NHÓM CHỮ của từng số hạng để khai triển đúng cột con (`(8ab)`=8a+8b, KHÔNG
    gồm 8c). Số hạng đầu không dấu = cộng. Cắt tại `=` đầu để bỏ nhãn cột kế (`-12`).
    """
    if "=" not in formula:
        return None, []
    lhs, rhs = formula.split("=", 1)
    lm = re.search(r"(\d{1,2})", lhs)
    target = lm.group(1) if lm else None
    terms: list[tuple[int, str, str]] = []
    for m in re.finditer(r"([+-]?)\s*\(?(\d{1,2})([a-z]*)\)?", rhs):
        terms.append((-1 if m.group(1) == "-" else 1, m.group(2), m.group(3)))
    return target, terms


def _numbering_letter_cols(cells: list[list[Any]], ri: int) -> dict[str, dict[str, int]]:
    """base → {chữ: cột} cho các cột con đánh số `(8a)(8b)(8c)` trên dòng đánh số."""
    out: dict[str, dict[str, int]] = {}
    for ci, v in enumerate(cells[ri]):
        m = re.match(r"^[(\-]\s*(\d{1,2})([a-z]+)\)?", to_str(v) or "")
        if m:
            out.setdefault(m.group(1), {})[m.group(2)] = ci
    return out


def _term_cols(
    base: str, letters: str,
    direct: dict[str, int], parts: dict[str, list[int]], letter_cols: dict[str, dict[str, int]],
) -> list[int] | None:
    """Cột(s) cho một số hạng. `(8ab)` → cột 8a,8b CỤ THỂ; `(6)` → cột tổng nếu có, nếu
    không thì mọi cột con của 6."""
    if letters:
        lc = letter_cols.get(base, {})
        cols = [lc[ch] for ch in letters if ch in lc]
        return cols if len(cols) == len(letters) else None
    if base in direct:
        return [direct[base]]
    if base in parts:
        return list(parts[base])
    return None


def _column_labels(cells: list[list[Any]], ri: int) -> dict[int, str]:
    """cột → nhãn (gộp 3 dòng ngay trên dòng đánh số, đã lowercase)."""
    labels: dict[int, str] = {}
    for r in range(max(0, ri - 3), ri):
        if r >= len(cells):
            continue
        for ci, v in enumerate(cells[r]):
            s = to_str(v)
            if s:
                labels[ci] = (labels.get(ci, "") + " " + s).strip().lower()
    return labels


def _resolve_export_col(
    cells: list[list[Any]], ri: int, minus_cols: list[int]
) -> tuple[int | None, str | None]:
    """Cột xuất khẩu = cột TRỪ có nhãn khớp 'xuất khẩu/export' và không khớp nhãn loại
    trừ. Phải DUY NHẤT; 0 hoặc >1 → không xác định (trả None → không nạp M15a)."""
    labels = _column_labels(cells, ri)
    cands = [
        c for c in minus_cols
        if any(k in labels.get(c, "") for k in _M15A_EXPORT_INCLUDE)
        and not any(k in labels.get(c, "") for k in _M15A_EXPORT_EXCLUDE)
    ]
    if len(cands) == 1:
        return cands[0], labels.get(cands[0])
    return None, None


def resolve_m15a(cells: list[list[Any]]) -> M15aResolution | None:
    """Map cột Mẫu 15a mở rộng: đẳng thức cân đối làm cổng + export_qty theo nhãn.

    None nếu (a) không có dòng đánh số/công thức, (b) đẳng thức < ngưỡng, hoặc
    (c) không xác định được DUY NHẤT cột xuất khẩu. Thà không nạp còn hơn nạp sai.
    """
    ri, direct, parts, formula = parse_numbering_row(cells)
    if ri is None or not formula:
        return None
    letter_cols = _numbering_letter_cols(cells, ri)
    target, raw_terms = parse_formula_terms(formula)
    if not target or not raw_terms:
        return None

    resolved: list[tuple[int, list[int]]] = []
    for sign, base, letters in raw_terms:
        cols = _term_cols(base, letters, direct, parts, letter_cols)
        if cols is None:
            return None
        resolved.append((sign, cols))
    tgt_cols = _term_cols(target, "", direct, parts, letter_cols)
    code_cols = _col_for("2", direct, parts)
    if tgt_cols is None or not code_cols:
        return None

    checked, matched = _identity_counts(cells, ri + 1, tgt_cols, resolved, code_cols)
    if checked == 0 or (matched / checked) < _MATCH_RATE:
        return None

    minus_cols = [c for sign, cols in resolved if sign < 0 for c in cols]
    export_col, export_label = _resolve_export_col(cells, ri, minus_cols)
    if export_col is None:
        return None

    plus_cols = [c for sign, cols in resolved if sign > 0 for c in cols]
    opening = _term_cols("5", "", direct, parts, letter_cols) or []
    cols = {
        "product_code": code_cols,
        "product_name": _col_for("3", direct, parts) or [],
        "unit": _col_for("4", direct, parts) or [],
        "opening_qty": opening,
        "closing_qty": tgt_cols,
        "export_qty": [export_col],
        "intake_qty": [c for c in plus_cols if c not in opening],
        "other_out_qty": [c for c in minus_cols if c != export_col],
    }
    return M15aResolution(
        cols=cols, header_row=ri, data_start=ri + 1, formula=formula.strip(),
        checked=checked, matched=matched, export_label=export_label,
    )


def select_extended_m15a(path, year: int | None = None) -> tuple[str, M15aResolution] | None:
    """Sheet + map cột Mẫu 15a bố cục mở rộng. None nếu không sheet nào xác thực.

    Chỉ gọi khi đường cột cố định (`select_sheet`) trượt. Chọn theo kỳ khớp `year`
    trước, rồi số dòng — như `select_extended_m15`.
    """
    import pandas as pd

    from app.adapters._common import normalize_code, parse_company_header

    xls = pd.ExcelFile(path)
    candidates: list[tuple[int, int, str, M15aResolution]] = []
    for name in xls.sheet_names:
        cells = pd.read_excel(xls, sheet_name=name, header=None).values.tolist()
        res = resolve_m15a(cells)
        if res is None:
            continue
        h = parse_company_header(cells, scan_rows=14)
        rank = 0
        if h.period_from is not None:
            if h.period_from.year == year:
                rank = 2
            elif h.period_to is not None and h.period_from.year <= (year or -1) <= h.period_to.year:
                rank = 1
        n = sum(
            1 for r in cells[res.data_start:]
            if any(c < len(r) and normalize_code(to_str(r[c])) for c in res.cols["product_code"])
        )
        candidates.append((rank, n, name, res))
    if not candidates:
        return None
    candidates.sort(key=lambda t: (-t[0], -t[1]))
    _, _, name, res = candidates[0]
    return name, res


def identity_counts_by_field(
    cells: list[list[Any]], data_start: int, cols: dict[str, list[int]],
    target: str, terms: tuple[tuple[int, str], ...], code_field: str,
) -> tuple[int, int]:
    """(số dòng đã kiểm, số dòng khớp) của đẳng thức cân đối viết theo TRƯỜNG."""
    return _identity_counts(
        cells, data_start,
        cols.get(target, []),
        [(sign, cols.get(f, [])) for sign, f in terms],
        cols.get(code_field, []),
    )


def apply_officer_map(
    cells: list[list[Any]], layout: Any, officer: dict[str, list[int]], slot: str,
) -> tuple[dict[str, list[int]], int, int]:
    """Áp vị trí cột của cán bộ lên map suy được, rồi KIỂM LẠI đẳng thức cân đối.

    ``layout`` là ``ColMap`` hoặc ``M15aResolution``. ``officer`` = `{trường: [cột…]}`
    đã lọc theo đúng vân tay và đúng các trường slot này đọc. Trả
    `(map cột sẽ đọc, số dòng đã kiểm, số dòng khớp)`.

    Đẳng thức không đạt ngưỡng → ném ``OfficerMapBalanceError``. KHÔNG có nhánh nào
    quay về map cũ: cán bộ phải biết vị trí họ vừa chỉ định không đọc được, chứ không
    phải nhận một lượt nạp "thành công" đọc bằng bố cục khác.
    """
    if not officer:
        return dict(layout.cols), layout.checked, layout.matched
    fields = ", ".join(sorted(officer))
    if layout.identity_target is None:
        raise OfficerMapBalanceError(
            f"{slot}: không kiểm lại được đẳng thức cân đối của biểu sau khi áp map cột "
            f"của cán bộ (công thức trên file có số hạng không quy về trường nào). "
            f"Trường cán bộ chỉ định: {fields}. Không nạp để không ghi số chưa chứng minh."
        )
    cols = {**layout.cols, **{f: list(c) for f, c in officer.items()}}
    checked, matched = identity_counts_by_field(
        cells, layout.data_start, cols,
        layout.identity_target, layout.identity_terms, layout.code_field,
    )
    if checked == 0 or (matched / checked) < _MATCH_RATE:
        raise OfficerMapBalanceError(
            f"{slot}: áp map cột của cán bộ làm vỡ đẳng thức cân đối của biểu — khớp "
            f"{matched}/{checked} dòng, cần từ {int(_MATCH_RATE * 100)}% trở lên. "
            f"Trường cán bộ chỉ định: {fields}. Không nạp dữ liệu; sửa lại chỉ số cột "
            f"ở màn xác nhận rồi xác nhận lại."
        )
    return cols, checked, matched


__all__ = [
    "ColMap",
    "M15aResolution",
    "OfficerMapBalanceError",
    "apply_officer_map",
    "identity_counts_by_field",
    "parse_formula",
    "parse_formula_terms",
    "parse_numbering_row",
    "resolve_m15",
    "resolve_m15a",
    "select_extended_m15",
    "select_extended_m15a",
]
