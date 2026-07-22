"""Adapter for Mẫu 15 — BCQT Nguyên vật liệu (TT39)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from app.adapters._common import (
    CompanyHeader,
    ParseIssues,
    count_external_workbooks,
    ensure_excel,
    normalize_code,
    normalize_name,
    parse_company_header,
    safe_get,
    scan_error_cells,
    to_float,
    to_str,
)
from app.adapters.layout import find_data_start
from app.adapters.sheet_select import select_sheet


@dataclass
class M15Row:
    row_no: int | None
    material_code: str
    material_name: str | None
    unit: str | None
    opening_qty: float
    import_qty: float
    reexport_qty: float
    repurpose_qty: float
    production_out_qty: float
    other_out_qty: float
    closing_qty: float


@dataclass
class M15File:
    header: CompanyHeader
    rows: list[M15Row]
    source_file: str
    issues: ParseIssues = field(default_factory=ParseIssues)


# Column index within the data sheet (0-indexed). Schema observed on
# HONG_AN 2024 file `TT39_BaoCaoQuyetToan_NVL 2024.xlsx`, sheet `BCQT_NPL`:
#   col0=STT, col1=Mã NVL, col2=Tên NVL, col3=ĐVT,
#   col4=Tồn đầu, col5=Nhập trong kỳ,
#   col6=Tái xuất, col7=Chuyển MĐSD, col8=Xuất sản xuất, col9=Xuất khác,
#   col10=Tồn cuối kỳ
_COL = {
    "row_no": 0,
    "material_code": 1,
    "material_name": 2,
    "unit": 3,
    "opening_qty": 4,
    "import_qty": 5,
    "reexport_qty": 6,
    "repurpose_qty": 7,
    "production_out_qty": 8,
    "other_out_qty": 9,
    "closing_qty": 10,
}
_DATA_START_ROW = 9  # row index where first data row appears
_SHEET_NAMES = ("BCQT_NPL", "BCQT_NVL", "Sheet1")



def parse_m15(path: str | Path, sheet: str | None = None, year: int | None = None) -> M15File:
    p = ensure_excel(Path(path))
    xls = pd.ExcelFile(p)
    if sheet is None:
        sheet = select_sheet(p, "m15", year).name
    df = pd.read_excel(xls, sheet_name=sheet, header=None)
    cells = df.values.tolist()
    header = parse_company_header(cells)

    data_start = find_data_start(cells, "m15")

    rows: list[M15Row] = []
    for raw in cells[data_start:]:
        material_code = normalize_code(to_str(safe_get(raw, _COL["material_code"])))
        if not material_code:
            continue
        row_no_raw = to_str(safe_get(raw, _COL["row_no"]))
        try:
            row_no = int(float(row_no_raw)) if row_no_raw else None
        except ValueError:
            row_no = None

        rows.append(
            M15Row(
                row_no=row_no,
                material_code=material_code,
                material_name=normalize_name(to_str(safe_get(raw, _COL["material_name"]))),
                unit=normalize_code(to_str(safe_get(raw, _COL["unit"]))),
                opening_qty=to_float(safe_get(raw, _COL["opening_qty"])),
                import_qty=to_float(safe_get(raw, _COL["import_qty"])),
                reexport_qty=to_float(safe_get(raw, _COL["reexport_qty"])),
                repurpose_qty=to_float(safe_get(raw, _COL["repurpose_qty"])),
                production_out_qty=to_float(safe_get(raw, _COL["production_out_qty"])),
                other_out_qty=to_float(safe_get(raw, _COL["other_out_qty"])),
                closing_qty=to_float(safe_get(raw, _COL["closing_qty"])),
            )
        )

    return M15File(
        header=header, rows=rows, source_file=str(p),
        issues=ParseIssues(
            error_cells=scan_error_cells(p, sheet, data_start, _COL.values()),
            external_workbooks=count_external_workbooks(p),
            scanned=True,
        ),
    )
