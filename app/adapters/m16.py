"""Adapter for Mẫu 16 — Định mức thực tế sản xuất (TT39)."""

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
from app.adapters.sheet_select import SheetNotFound, select_sheet


@dataclass
class M16Row:
    product_code: str
    product_name: str | None
    product_unit: str | None
    material_code: str
    material_name: str | None
    material_unit: str | None
    norm_qty: float
    note: str | None = None


def is_domestic_origin(note: str | None) -> bool:
    """Ghi chú "x" ở Mẫu 16 = NVL xuất xứ trong nước (không nhập khẩu).

    Hàng xuất xứ VN không có tờ khai nhập nên không đối chiếu lệch nhập khẩu.
    """
    return bool(note) and note.strip().lower() == "x"


@dataclass
class M16File:
    header: CompanyHeader
    rows: list[M16Row]
    source_file: str
    issues: ParseIssues = field(default_factory=ParseIssues)
    sheet: str | None = None


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
    "note": 8,
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


def parse_m16(path: str | Path, sheet: str | None = None, year: int | None = None) -> M16File:
    p = ensure_excel(Path(path))
    xls = pd.ExcelFile(p)
    cols = _M16_TT39_COLS
    data_start = _M16_TT39_DATA_START
    if sheet is None:
        try:
            # Chọn theo nội dung trước: có DN gộp Mẫu 15/15a/16 vào một workbook,
            # tên sheet không nói được sheet nào là định mức.
            choice = select_sheet(p, "m16", year)
            sheet, data_start = choice.name, choice.data_start
        except SheetNotFound:
            if _detect_format(xls) == "tt39":
                sheet = next(
                    (s for s in _M16_TT39_SHEETS if s in xls.sheet_names), xls.sheet_names[0]
                )
            else:
                sheet, cols, data_start = "Sheet1", _M16_DINHMUC_COLS, 1

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
                note=(to_str(cell(raw, "note")) or None) if "note" in cols else None,
            )
        )

    return M16File(
        header=header, rows=rows, source_file=str(p), sheet=sheet,
        issues=ParseIssues(
            error_cells=scan_error_cells(p, sheet, data_start, cols.values()),
            external_workbooks=count_external_workbooks(p),
            scanned=True,
        ),
    )
