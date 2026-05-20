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


def _split_item_code_name(raw_name: str | None) -> tuple[str | None, str | None]:
    """BCCT col `Tên hàng` thường là `MA#&Tên`. Tách ra nếu cần."""
    if not raw_name:
        return None, None
    if "#&" in raw_name:
        code, _, name = raw_name.partition("#&")
        return normalize_code(code), normalize_name(name)
    return None, normalize_name(raw_name)


def parse_bcct(path: str | Path) -> BcctFile:
    p = ensure_excel(Path(path))
    xls = pd.ExcelFile(p)
    sheet = next((s for s in _MAIN_SHEET_CANDIDATES if s in xls.sheet_names), xls.sheet_names[0])
    df = pd.read_excel(xls, sheet_name=sheet, header=None)
    cells = df.values.tolist()

    company_tax_id: str | None = None
    company_name: str | None = None
    rows: list[BcctRow] = []

    def cell(row: list, name: str):
        return safe_get(row, _COL[name])

    for raw in cells[_DATA_START:]:
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
    )
