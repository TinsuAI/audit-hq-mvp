"""Adapter for Báo cáo Hàng Chi Tiết (BCCT) — xuất từ VNACCS/ECUS."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from app.adapters._common import (
    ensure_excel,
    normalize_code,
    normalize_name,
    safe_get,
    to_date,
    to_float,
    to_str,
)
from app.adapters.sheet_select import select_sheet


@dataclass
class BcctRow:
    line_no: int | None
    declaration_no: str
    declaration_date: date | None
    customs_code: str | None
    item_code: str | None
    item_name: str | None
    hs_code: str | None
    origin: str | None
    quantity: float | None
    unit: str | None
    unit_price: float | None
    currency: str | None
    value_foreign: float | None
    value_total: float | None
    tax_total: float | None
    partner: str | None
    invoice_no: str | None


@dataclass
class BcctFile:
    rows: list[BcctRow]
    company_tax_id: str | None
    company_name: str | None
    source_file: str
    sheet: str | None = None


# BaoCaoHangChiTiet schema (HONG_AN 2024 sample, Sheet1):
# Header at row 9, data from row 10.
_COL = {
    "declaration_no": 1,
    "declaration_date": 2,
    "customs_code": 3,
    "line_no": 19,
    "item_code": 20,
    "hs_code": 21,
    "item_name": 22,
    "origin": 23,
    "unit_price": 24,
    "quantity": 26,
    "unit": 27,
    "currency": 11,
    "value_foreign": 30,
    "value_total": 31,
    "tax_total": 46,
    "company_tax_id": 47,
    "company_name": 48,
    "partner": 49,
    "invoice_no": 50,
}
_HEADER_ROW = 9
_DATA_START = 10
_MAIN_SHEET_CANDIDATES = ("Sheet1", "Sheet 1", "BCCT")
_DECLARATION_RE = re.compile(r"^\d{9,13}$")

# Nhãn tiêu đề → trường, theo THỨ TỰ ƯU TIÊN. `_COL` ở trên là bố cục ECUS "BC chi
# tiết" (tiêu đề dòng 9, 54–56 cột) — 8 DN pilot đều dùng nó. Bản xuất
# "BaoCaoHangChiTietMH" là bố cục KHÁC (tiêu đề dòng 0, 81 cột) mà `_COL` vẫn đọc
# trôi vì `Số TK`/`Ngày ĐK` tình cờ trùng cột: mọi trường còn lại rơi vào cột khác
# và KHÔNG có lỗi nào phát ra. Vì thế cột phải suy từ nhãn, không từ vị trí.
# So khớp là BẰNG ĐÚNG chuỗi đã chuẩn hoá, không phải "chứa": `Đơn giá` vs
# `Đơn giá tính thuế`, `Tổng trị giá` vs `Tổng trị giá hóa đơn` là hai cột khác nhau.
_LABEL_ALIASES: dict[str, tuple[str, ...]] = {
    "declaration_no": ("số tk",),
    "declaration_date": ("ngày đk",),
    "customs_code": ("mã loại hình",),
    "line_no": ("stt hàng",),
    "item_code": ("mã npl/sp", "mã hàng"),
    "hs_code": ("mã hs",),
    "item_name": ("tên hàng",),
    "origin": ("xuất xứ", "nước xuất xứ"),
    "unit_price": ("đơn giá", "đơn giá hóa đơn"),
    "quantity": ("tổng số lượng", "số lượng"),
    "unit": ("đơn vị tính",),
    "currency": ("đơn vị tiền tệ", "ng.tệ hóa đơn"),
    "value_foreign": ("trị giá nt", "trị giá hóa đơn"),
    "value_total": ("tổng trị giá", "trị giá tính thuế"),
    "tax_total": ("tổng tiền thuế",),
    "company_tax_id": ("mã doanh nghiệp",),
    "company_name": ("tên doanh nghiệp",),
    "partner": ("tên đối tác",),
    "invoice_no": ("số hóa đơn", "số hóa đơn tm"),
}
# Không có đủ ba trường này thì bản đồ theo nhãn vô dụng — rơi về `_COL`.
_LABEL_REQUIRED = ("declaration_no", "item_code", "quantity")
# Tiêu đề nằm ngay trên dòng dữ liệu, nhưng có bố cục chèn dòng đánh số ở giữa.
_HEADER_LOOKBACK = 6


def _header_labels(cells: list[list], data_start: int) -> dict[str, int]:
    """Nhãn (đã chuẩn hoá) → cột, lấy ở dòng tiêu đề nhiều nhãn khớp nhất.

    Nhãn trùng nhau lấy lần xuất hiện SAU: `Tổng tiền thuế` có ở cả cấp tờ khai lẫn
    cấp dòng hàng, cột cần đọc là cột cấp dòng hàng nằm sau.
    """
    known = {alias for aliases in _LABEL_ALIASES.values() for alias in aliases}
    best: dict[str, int] = {}
    for i in range(max(0, data_start - _HEADER_LOOKBACK), data_start):
        found: dict[str, int] = {}
        for col, raw in enumerate(cells[i]):
            label = to_str(raw)
            if label and label.strip().lower() in known:
                found[label.strip().lower()] = col
        if len(found) > len(best):
            best = found
    return best


def _resolve_columns(cells: list[list], data_start: int) -> dict[str, int]:
    """Bản đồ cột cho file này: theo nhãn nếu đọc được, không thì `_COL`."""
    labels = _header_labels(cells, data_start)
    if not labels:
        return _COL
    col: dict[str, int] = {}
    for field, aliases in _LABEL_ALIASES.items():
        for alias in aliases:
            if alias in labels:
                col[field] = labels[alias]
                break
    if any(f not in col for f in _LABEL_REQUIRED):
        return _COL
    return col


def _split_item_code_name(raw_name: str | None) -> tuple[str | None, str | None]:
    """BCCT col `Tên hàng` thường là `MA#&Tên`. Tách ra nếu cần."""
    if not raw_name:
        return None, None
    if "#&" in raw_name:
        code, _, name = raw_name.partition("#&")
        return normalize_code(code), normalize_name(name)
    return None, normalize_name(raw_name)


def parse_bcct(path: str | Path, sheet: str | None = None, year: int | None = None) -> BcctFile:
    p = ensure_excel(Path(path))
    xls = pd.ExcelFile(p)
    data_start = _DATA_START
    if sheet is None:
        # Sheet tổng hợp (cấp tờ khai) cũng có số tờ khai ở cột 1 nên khớp
        # `_DECLARATION_RE` — chọn nhầm nó sinh dòng SAI chứ không phải 0 dòng.
        choice = select_sheet(p, "bcct", year)
        sheet, data_start = choice.name, choice.data_start
    df = pd.read_excel(xls, sheet_name=sheet, header=None)
    cells = df.values.tolist()
    col = _resolve_columns(cells, data_start)

    company_tax_id: str | None = None
    company_name: str | None = None
    rows: list[BcctRow] = []

    def cell(row: list, name: str):
        idx = col.get(name)
        return None if idx is None else safe_get(row, idx)

    for raw in cells[data_start:]:
        declaration_no = normalize_code(to_str(cell(raw, "declaration_no")))
        if not declaration_no or not _DECLARATION_RE.match(declaration_no):
            continue

        item_code = normalize_code(to_str(cell(raw, "item_code")))
        fallback_code, item_name = _split_item_code_name(to_str(cell(raw, "item_name")))
        item_code = item_code or fallback_code

        if company_tax_id is None:
            company_tax_id = normalize_code(to_str(cell(raw, "company_tax_id")))
        if company_name is None:
            company_name = normalize_name(to_str(cell(raw, "company_name")))

        line_no_raw = to_str(cell(raw, "line_no"))
        try:
            line_no = int(float(line_no_raw)) if line_no_raw else None
        except ValueError:
            line_no = None

        rows.append(
            BcctRow(
                line_no=line_no,
                declaration_no=declaration_no,
                declaration_date=to_date(cell(raw, "declaration_date")),
                customs_code=normalize_code(to_str(cell(raw, "customs_code"))),
                item_code=item_code,
                item_name=item_name,
                hs_code=normalize_code(to_str(cell(raw, "hs_code"))),
                origin=normalize_code(to_str(cell(raw, "origin"))),
                quantity=to_float(cell(raw, "quantity")) or None,
                unit=normalize_code(to_str(cell(raw, "unit"))),
                unit_price=to_float(cell(raw, "unit_price")) or None,
                currency=normalize_code(to_str(cell(raw, "currency"))),
                value_foreign=to_float(cell(raw, "value_foreign")) or None,
                value_total=to_float(cell(raw, "value_total")) or None,
                tax_total=to_float(cell(raw, "tax_total")) or None,
                partner=normalize_name(to_str(cell(raw, "partner"))),
                invoice_no=normalize_code(to_str(cell(raw, "invoice_no"))),
            )
        )

    return BcctFile(
        rows=rows,
        company_tax_id=company_tax_id,
        company_name=company_name,
        source_file=str(p),
        sheet=sheet,
    )
