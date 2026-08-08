"""Adapter for Mẫu 15a — BCQT Thành phẩm (TT39)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from app.adapters._common import (
    CompanyHeader,
    ParseIssues,
    ParseProvenance,
    column_choices,
    count_external_workbooks,
    ensure_excel,
    normalize_code,
    normalize_name,
    parse_company_header,
    safe_get,
    sample_rows,
    scan_error_cells,
    to_float,
    to_str,
)
from app.adapters.evidence import (
    evidence_m15a_extended,
    evidence_m15a_standard,
)
from app.adapters.extended_layout import (
    M15aResolution,
    apply_officer_map,
    resolve_m15a,
    select_extended_m15a,
)
from app.adapters.form_signature import compute_form_signature
from app.adapters.layout import find_data_start
from app.adapters.sheet_select import SheetNotFound, select_sheet, standard_layout_colmap
from app.adapters.templates import (
    MATCH_EXTENDED,
    MATCH_OFFICER,
    apply_officer_evidence,
    match_template,
    officer_column_groups,
    resolve_columns,
    resolve_template_evidence,
)


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


def parse_m15a(
    path: str | Path,
    sheet: str | None = None,
    year: int | None = None,
    officer_maps: dict[str, dict[str, int]] | None = None,
) -> M15aFile:
    """`officer_maps` = {vân tay form: {field: chỉ số cột}} cán bộ đã xác nhận cho DN
    này ở slot này. Vị trí của cán bộ THẮNG template lẫn cột mặc định, theo TỪNG
    trường (ADR #24 mục 5)."""
    p = ensure_excel(Path(path))
    xls = pd.ExcelFile(p)
    resolution: M15aResolution | None = None
    cand_colmap: dict[str, int] | None = None
    pinned = sheet is not None
    if sheet is None:
        try:
            cand = select_sheet(p, "m15a", year)
            sheet, cand_colmap = cand.name, cand.colmap
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

    if pinned and standard_layout_colmap(cells, "m15a") is None:
        # Xem chú thích cùng chỗ trong `app/adapters/m15.py`: trang tính đã ghim mà nhãn
        # tiêu đề không xác nhận bố cục chuẩn thì phải thử bố cục mở rộng.
        resolution = resolve_m15a(cells)

    if resolution is not None:
        form_sig = compute_form_signature(cells, "m15a", resolution.data_start)
        officer = officer_column_groups(officer_maps, form_sig, resolution.cols)
        # Áp vị trí của cán bộ rồi KIỂM LẠI đẳng thức cân đối trên map đã áp (#95).
        resolution.cols, resolution.checked, resolution.matched = apply_officer_map(
            cells, resolution, officer, "m15a"
        )
        rows = _rows_from_resolution(cells, resolution)
        scan_cols = [c for cols in resolution.cols.values() for c in cols]
        # Mọi trường map cột đặt được, không chỉ cột lượng: bằng chứng suy TỪ map (#111).
        evidence = evidence_m15a_extended(
            [f for f in resolution.cols if resolution.cols.get(f)]
        )
        apply_officer_evidence(evidence, officer)
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
                    "form_signature": form_sig,
                    # CẢ nhóm cột, không phải cột đầu nhóm — xem chú thích ở m15.py.
                    "column_map": {
                        f: list(resolution.cols[f]) for f in evidence if resolution.cols.get(f)
                    },
                    "template_id": None,
                    "match_source": MATCH_OFFICER if officer else MATCH_EXTENDED,
                    "column_choices": column_choices(cells, resolution.data_start),
                    "sample_rows": sample_rows(cells, resolution.data_start),
                },
                evidence=evidence,
            ),
        )

    data_start = find_data_start(cells, "m15a")
    # Vân tay đo TRƯỚC khi áp template (template khai vân tay theo đúng cách đo này).
    form_sig = compute_form_signature(cells, "m15a", data_start)
    template = match_template("m15a", form_sig, data_start)
    col, officer = resolve_columns(_COL, template, officer_maps, form_sig)
    if template is not None:
        data_start = template.data_start

    rows = []
    for raw in cells[data_start:]:
        product_code = normalize_code(to_str(safe_get(raw, col["product_code"])))
        if not product_code:
            continue
        row_no_raw = to_str(safe_get(raw, col["row_no"]))
        try:
            row_no = int(float(row_no_raw)) if row_no_raw else None
        except ValueError:
            row_no = None

        rows.append(
            M15aRow(
                row_no=row_no,
                product_code=product_code,
                product_name=normalize_name(to_str(safe_get(raw, col["product_name"]))),
                unit=normalize_code(to_str(safe_get(raw, col["unit"]))),
                opening_qty=to_float(safe_get(raw, col["opening_qty"])),
                intake_qty=to_float(safe_get(raw, col["intake_qty"])),
                repurpose_qty=to_float(safe_get(raw, col["repurpose_qty"])),
                export_qty=to_float(safe_get(raw, col["export_qty"])),
                other_out_qty=to_float(safe_get(raw, col["other_out_qty"])),
                closing_qty=to_float(safe_get(raw, col["closing_qty"])),
            )
        )

    evidence, detail = resolve_template_evidence(
        template, tuple(col), col, form_sig,
        lambda: evidence_m15a_standard(cells, data_start, cand_colmap, cols=col),
        officer=officer,
    )
    detail["column_choices"] = column_choices(cells, data_start)
    detail["sample_rows"] = sample_rows(cells, data_start)
    return M15aFile(
        header=header, rows=rows, source_file=str(p), sheet=sheet,
        issues=ParseIssues(
            error_cells=scan_error_cells(p, sheet, data_start, col.values()),
            external_workbooks=count_external_workbooks(p),
            scanned=True,
        ),
        provenance=ParseProvenance(detail=detail, evidence=evidence),
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
