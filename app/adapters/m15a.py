"""Adapter for Mẫu 15a — BCQT Thành phẩm (TT39)."""

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
from app.adapters.layout import find_data_start
from app.adapters.sheet_select import select_sheet


@dataclass
class M15aRow:
    row_no: int | None
    product_code: str
    product_name: str | None
    unit: str | None
    opening_qty: float
    intake_qty: float
    repurpose_qty: float
    export_qty: float
    other_out_qty: float
    closing_qty: float


@dataclass
class M15aFile:
    header: CompanyHeader
    rows: list[M15aRow]
    source_file: str


# HONG_AN 2024 `TT39_BaoCaoQuyetToan_SP 2024.xlsx`, sheet `BCQT_SP`:
#   col0=STT, col1=Mã SP, col2=Tên SP, col3=ĐVT,
#   col4=Tồn đầu, col5=Nhập trong kỳ,
#   col6=Thay đổi MĐSD, col7=Xuất khẩu, col8=Xuất khác,
#   col9=Tồn cuối kỳ
_COL = {
    "row_no": 0,
    "product_code": 1,
    "product_name": 2,
    "unit": 3,
    "opening_qty": 4,
    "intake_qty": 5,
    "repurpose_qty": 6,
    "export_qty": 7,
    "other_out_qty": 8,
    "closing_qty": 9,
}
_DATA_START_ROW = 9
_SHEET_NAMES = ("BCQT_SP", "BCQT_SXXK", "Sheet1")


def parse_m15a(path: str | Path, sheet: str | None = None, year: int | None = None) -> M15aFile:
    p = ensure_excel(Path(path))
    xls = pd.ExcelFile(p)
    if sheet is None:
        sheet = select_sheet(p, "m15a", year).name
    df = pd.read_excel(xls, sheet_name=sheet, header=None)
    cells = df.values.tolist()
    header = parse_company_header(cells)

    rows: list[M15aRow] = []
    for raw in cells[find_data_start(cells, "m15a"):]:
        product_code = normalize_code(to_str(safe_get(raw, _COL["product_code"])))
        if not product_code:
            continue
        row_no_raw = to_str(safe_get(raw, _COL["row_no"]))
        try:
            row_no = int(float(row_no_raw)) if row_no_raw else None
        except ValueError:
            row_no = None

        rows.append(
            M15aRow(
                row_no=row_no,
                product_code=product_code,
                product_name=normalize_name(to_str(safe_get(raw, _COL["product_name"]))),
                unit=normalize_code(to_str(safe_get(raw, _COL["unit"]))),
                opening_qty=to_float(safe_get(raw, _COL["opening_qty"])),
                intake_qty=to_float(safe_get(raw, _COL["intake_qty"])),
                repurpose_qty=to_float(safe_get(raw, _COL["repurpose_qty"])),
                export_qty=to_float(safe_get(raw, _COL["export_qty"])),
                other_out_qty=to_float(safe_get(raw, _COL["other_out_qty"])),
                closing_qty=to_float(safe_get(raw, _COL["closing_qty"])),
            )
        )

    return M15aFile(header=header, rows=rows, source_file=str(p))
