"""Adapter for Mẫu 15a — BCQT Thành phẩm (TT39)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from app.adapters._common import (
    CompanyHeader,
    ParseIssues,
    ParseProvenance,
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
from app.adapters.extended_layout import M15aResolution, select_extended_m15a
from app.adapters.layout import find_data_start
from app.adapters.sheet_select import SheetNotFound, select_sheet


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
    issues: ParseIssues = field(default_factory=ParseIssues)
    sheet: str | None = None
    provenance: ParseProvenance = field(default_factory=ParseProvenance)


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
    resolution: M15aResolution | None = None
    if sheet is None:
        try:
            sheet = select_sheet(p, "m15a", year).name
        except SheetNotFound:
            # Đường cột cố định trượt — thử bố cục MỞ RỘNG: suy map từ dòng đánh số,
            # chứng minh bằng đẳng thức + xác định export_qty theo nhãn (ADR #15).
            # Không xác thực được thì ném lại SheetNotFound gốc (không nạp bừa).
            picked = select_extended_m15a(p, year)
            if picked is None:
                raise
            sheet, resolution = picked

    df = pd.read_excel(xls, sheet_name=sheet, header=None)
    cells = df.values.tolist()
    header = parse_company_header(cells)

    if resolution is not None:
        rows = _rows_from_resolution(cells, resolution)
        scan_cols = [c for cols in resolution.cols.values() for c in cols]
        return M15aFile(
            header=header, rows=rows, source_file=str(p), sheet=sheet,
            issues=ParseIssues(
                error_cells=scan_error_cells(p, sheet, resolution.data_start, scan_cols),
                external_workbooks=count_external_workbooks(p),
                scanned=True,
            ),
            provenance=ParseProvenance(
                layout="extended",
                detail={
                    "formula": resolution.formula,
                    "matched": resolution.matched,
                    "checked": resolution.checked,
                    "match_rate": round(resolution.match_rate, 4),
                    "export_col": resolution.cols["export_qty"][0],
                    "export_label": resolution.export_label,
                },
            ),
        )

    data_start = find_data_start(cells, "m15a")

    rows = []
    for raw in cells[data_start:]:
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

    return M15aFile(
        header=header, rows=rows, source_file=str(p), sheet=sheet,
        issues=ParseIssues(
            error_cells=scan_error_cells(p, sheet, data_start, _COL.values()),
            external_workbooks=count_external_workbooks(p),
            scanned=True,
        ),
    )


def _rows_from_resolution(cells: list, res: M15aResolution) -> list[M15aRow]:
    """Dựng dòng M15a từ map cột đã xác thực (bố cục mở rộng)."""
    code_cols = res.cols["product_code"]
    name_cols = res.cols.get("product_name", [])
    unit_cols = res.cols.get("unit", [])
    rows: list[M15aRow] = []
    for raw in cells[res.data_start:]:
        code = next((normalize_code(to_str(safe_get(raw, c))) for c in code_cols
                     if normalize_code(to_str(safe_get(raw, c)))), None)
        if not code:
            continue
        rows.append(M15aRow(
            row_no=None,
            product_code=code,
            product_name=normalize_name(to_str(safe_get(raw, name_cols[0]))) if name_cols else None,
            unit=normalize_code(to_str(safe_get(raw, unit_cols[0]))) if unit_cols else None,
            opening_qty=res.value(raw, "opening_qty"),
            intake_qty=res.value(raw, "intake_qty"),
            repurpose_qty=res.value(raw, "repurpose_qty"),
            export_qty=res.value(raw, "export_qty"),
            other_out_qty=res.value(raw, "other_out_qty"),
            closing_qty=res.value(raw, "closing_qty"),
        ))
    return rows
