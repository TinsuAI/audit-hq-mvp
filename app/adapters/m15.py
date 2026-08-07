"""Adapter for Mẫu 15 — BCQT Nguyên vật liệu (TT39)."""

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
from app.adapters.evidence import (
    evidence_m15_extended,
    evidence_m15_standard,
)
from app.adapters.extended_layout import ColMap, select_extended_m15
from app.adapters.form_signature import compute_form_signature
from app.adapters.layout import find_data_start
from app.adapters.sheet_select import SheetNotFound, select_sheet
from app.adapters.templates import (
    MATCH_EXTENDED,
    match_template,
    resolve_columns,
    resolve_template_evidence,
)


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
    sheet: str | None = None
    provenance: ParseProvenance = field(default_factory=ParseProvenance)


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



def parse_m15(
    path: str | Path,
    sheet: str | None = None,
    year: int | None = None,
    officer_maps: dict[str, dict[str, int]] | None = None,
) -> M15File:
    """`officer_maps` = {vân tay form: {field: chỉ số cột}} cán bộ đã xác nhận cho DN
    này ở slot này. Vị trí của cán bộ THẮNG template lẫn cột mặc định, theo TỪNG
    trường (ADR #24 mục 5)."""
    p = ensure_excel(Path(path))
    xls = pd.ExcelFile(p)
    colmap: ColMap | None = None
    # colmap select_sheet đã tính (nhãn tiêu đề khớp đúng vị trí) — giữ để tính nguồn
    # bằng chứng, không vứt như trước.
    cand_colmap: dict[str, int] | None = None
    if sheet is None:
        try:
            cand = select_sheet(p, "m15", year)
            sheet, cand_colmap = cand.name, cand.colmap
        except SheetNotFound:
            # Đường cột cố định trượt — thử bố cục MỞ RỘNG: suy map từ dòng đánh số,
            # chứng minh bằng đẳng thức của biểu (ADR #15). Không xác thực được thì
            # ném lại SheetNotFound gốc (không nạp bừa).
            picked = select_extended_m15(p, year)
            if picked is None:
                raise
            sheet, colmap = picked

    df = pd.read_excel(xls, sheet_name=sheet, header=None)
    cells = df.values.tolist()
    header = parse_company_header(cells)

    if colmap is not None:
        rows = _rows_from_colmap(cells, colmap)
        scan_cols = [c for cols in colmap.cols.values() for c in cols]
        evidence = evidence_m15_extended([f for f in _EVIDENCE_FIELDS if colmap.has(f)])
        return M15File(
            header=header, rows=rows, source_file=str(p), sheet=sheet,
            issues=ParseIssues(
                error_cells=scan_error_cells(p, sheet, colmap.data_start, scan_cols),
                external_workbooks=count_external_workbooks(p),
                scanned=True,
            ),
            provenance=ParseProvenance(
                layout="extended",
                detail={
                    "formula": colmap.formula,
                    "matched": colmap.matched,
                    "checked": colmap.checked,
                    "match_rate": round(colmap.match_rate, 4),
                    "form_signature": compute_form_signature(cells, "m15", colmap.data_start),
                    "column_map": {
                        f: colmap.cols[f][0] for f in evidence if colmap.cols.get(f)
                    },
                    # Bố cục mở rộng KHÔNG nhận vị trí của cán bộ: một trường ở đây có
                    # thể là TỔNG nhiều cột con, map lưu chỉ giữ cột đầu nhóm.
                    "template_id": None,
                    "match_source": MATCH_EXTENDED,
                },
                evidence=evidence,
            ),
        )

    data_start = find_data_start(cells, "m15")
    # Vân tay đo TRƯỚC khi áp template (template khai vân tay theo đúng cách đo này).
    form_sig = compute_form_signature(cells, "m15", data_start)
    template = match_template("m15", form_sig, data_start)
    col, officer = resolve_columns(_COL, template, officer_maps, form_sig)
    if template is not None:
        data_start = template.data_start

    rows = []
    for raw in cells[data_start:]:
        material_code = normalize_code(to_str(safe_get(raw, col["material_code"])))
        if not material_code:
            continue
        row_no_raw = to_str(safe_get(raw, col["row_no"]))
        try:
            row_no = int(float(row_no_raw)) if row_no_raw else None
        except ValueError:
            row_no = None

        rows.append(
            M15Row(
                row_no=row_no,
                material_code=material_code,
                material_name=normalize_name(to_str(safe_get(raw, col["material_name"]))),
                unit=normalize_code(to_str(safe_get(raw, col["unit"]))),
                opening_qty=to_float(safe_get(raw, col["opening_qty"])),
                import_qty=to_float(safe_get(raw, col["import_qty"])),
                reexport_qty=to_float(safe_get(raw, col["reexport_qty"])),
                repurpose_qty=to_float(safe_get(raw, col["repurpose_qty"])),
                production_out_qty=to_float(safe_get(raw, col["production_out_qty"])),
                other_out_qty=to_float(safe_get(raw, col["other_out_qty"])),
                closing_qty=to_float(safe_get(raw, col["closing_qty"])),
            )
        )

    evidence, detail = resolve_template_evidence(
        template, _EVIDENCE_FIELDS, col, form_sig,
        lambda: evidence_m15_standard(cells, data_start, cand_colmap),
        officer=officer,
    )
    return M15File(
        header=header, rows=rows, source_file=str(p), sheet=sheet,
        issues=ParseIssues(
            error_cells=scan_error_cells(p, sheet, data_start, col.values()),
            external_workbooks=count_external_workbooks(p),
            scanned=True,
        ),
        provenance=ParseProvenance(detail=detail, evidence=evidence),
    )


# Cột giá trị + mã mang nguồn bằng chứng ở badge truy nguồn.
_EVIDENCE_FIELDS = (
    "material_code", "opening_qty", "import_qty", "reexport_qty", "repurpose_qty",
    "production_out_qty", "other_out_qty", "closing_qty",
)


def _rows_from_colmap(cells: list, colmap: ColMap) -> list[M15Row]:
    """Dựng dòng M15 từ map cột đã xác thực (bố cục mở rộng)."""
    code_cols = colmap.cols["material_code"]
    name_cols = colmap.cols.get("material_name", [])
    unit_cols = colmap.cols.get("unit", [])
    rows: list[M15Row] = []
    for raw in cells[colmap.data_start:]:
        code = next((normalize_code(to_str(safe_get(raw, c))) for c in code_cols
                     if normalize_code(to_str(safe_get(raw, c)))), None)
        if not code:
            continue
        rows.append(M15Row(
            row_no=None,
            material_code=code,
            material_name=normalize_name(to_str(safe_get(raw, name_cols[0]))) if name_cols else None,
            unit=normalize_code(to_str(safe_get(raw, unit_cols[0]))) if unit_cols else None,
            opening_qty=colmap.value(raw, "opening_qty"),
            import_qty=colmap.value(raw, "import_qty"),
            reexport_qty=colmap.value(raw, "reexport_qty"),
            repurpose_qty=colmap.value(raw, "repurpose_qty"),
            production_out_qty=colmap.value(raw, "production_out_qty"),
            other_out_qty=colmap.value(raw, "other_out_qty"),
            closing_qty=colmap.value(raw, "closing_qty"),
        ))
    return rows
