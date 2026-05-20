"""Adapter for Mẫu 16 — Định mức thực tế sản xuất (TT39)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from app.adapters._common import (
    CompanyHeader,
    ensure_excel,
    normalize_code,
    normalize_name,
    parse_company_header,
    safe_get,
    to_float,
    to_str,
)


@dataclass
class M16Row:
    product_code: str
    product_name: str | None
    product_unit: str | None
    material_code: str
    material_name: str | None
    material_unit: str | None
    norm_qty: float


@dataclass
class M16File:
    header: CompanyHeader
    rows: list[M16Row]
    source_file: str


# Mẫu 16 TT39 chuẩn (BCDM_TT39_*.xls, sheet `BCTT39`):
#   header rows 8-10 (multi-line subheader, then "(1)..(8)" row).
#   Data từ row 11. Columns:
#     col1=STT (Mã SP cấp), col2=Mã SP, col3=Tên SP, col4=ĐVT SP,
#     col5=Mã NVL, col6=Tên NVL, col7=ĐVT NVL, col8=Lượng định mức.
# Cấu trúc parent-child: dòng có Mã SP là "row sản phẩm" (không có NVL),
# các dòng dưới có Mã NVL nhưng trống Mã SP -> forward-fill SP từ dòng trên.
_M16_TT39_COLS = {
    "product_code": 1,
    "product_name": 2,
    "product_unit": 3,
    "material_code": 4,
    "material_name": 5,
    "material_unit": 6,
    "norm_qty": 7,
}
_M16_TT39_DATA_START = 11
_M16_TT39_SHEETS = ("BCTT39", "Bcqt", "Sheet1")

# Format thay thế (DINHMUC YYYY.xlsx, sheet `Sheet1`):
#   col1=Mã SP, col3=Tên SP, col4=Mã NVL, col5=Tên NVL, col6=Đơn vị,
#   col7=Định mức 1, col8=Định mức 2, col9=ĐM+HH
# Header row 0, data from row 1. Parent-child cũng forward-fill.
_M16_DINHMUC_COLS = {
    "product_code": 1,
    "product_name": 3,
    "material_code": 4,
    "material_name": 5,
    "material_unit": 6,
    "norm_qty": 7,
}


def _detect_format(xls: pd.ExcelFile) -> str:
    if any(s in xls.sheet_names for s in ("BCTT39", "Bcqt")):
        return "tt39"
    if "Sheet1" in xls.sheet_names:
        return "dinhmuc"
    return "tt39"


def parse_m16(path: str | Path) -> M16File:
    p = ensure_excel(Path(path))
    xls = pd.ExcelFile(p)
    fmt = _detect_format(xls)
    if fmt == "tt39":
        sheet = next((s for s in _M16_TT39_SHEETS if s in xls.sheet_names), xls.sheet_names[0])
        cols = _M16_TT39_COLS
        data_start = _M16_TT39_DATA_START
    else:
        sheet = "Sheet1"
        cols = _M16_DINHMUC_COLS
        data_start = 1

    df = pd.read_excel(xls, sheet_name=sheet, header=None)
    cells = df.values.tolist()
    header = parse_company_header(cells)

    current_product_code: str | None = None
    current_product_name: str | None = None
    current_product_unit: str | None = None
    rows: list[M16Row] = []

    def cell(row: list, name: str):
        idx = cols.get(name)
        return None if idx is None else safe_get(row, idx)

    for raw in cells[data_start:]:
        product_code = normalize_code(to_str(cell(raw, "product_code")))
        if product_code:
            current_product_code = product_code
            current_product_name = normalize_name(to_str(cell(raw, "product_name")))
            if "product_unit" in cols:
                current_product_unit = normalize_code(to_str(cell(raw, "product_unit")))

        material_code = normalize_code(to_str(cell(raw, "material_code")))
        if not material_code or not current_product_code:
            continue

        norm_qty = to_float(cell(raw, "norm_qty"))
        if norm_qty == 0:
            continue

        rows.append(
            M16Row(
                product_code=current_product_code,
                product_name=current_product_name,
                product_unit=current_product_unit,
                material_code=material_code,
                material_name=normalize_name(to_str(cell(raw, "material_name"))),
                material_unit=normalize_code(to_str(cell(raw, "material_unit"))),
                norm_qty=norm_qty,
            )
        )

    return M16File(header=header, rows=rows, source_file=str(p))
