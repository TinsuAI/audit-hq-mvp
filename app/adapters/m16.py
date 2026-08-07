"""Adapter for Mẫu 16 — Định mức thực tế sản xuất (TT39)."""

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
    scan_error_cells,
    to_float,
    to_str,
)
from app.adapters.evidence import evidence_m16
from app.adapters.form_signature import compute_form_signature
from app.adapters.layout import find_data_start
from app.adapters.sheet_select import SheetNotFound, select_sheet
from app.adapters.templates import (
    apply_officer_evidence,
    match_source_for,
    officer_columns,
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
    provenance: ParseProvenance = field(default_factory=ParseProvenance)


# 004 tách định mức thành 2 cột: "Định mức kỹ thuật / Technical BOM" và "Lượng NL,
# VT thực tế sử dụng… / Actual BOM". Kiểm tra hải quan dùng ĐM THỰC TẾ. Cột cố định
# đọc cột kỹ thuật (c7) → phải chọn lại theo nhãn. DN chỉ một cột ĐM → giữ nguyên.
_M16_ACTUAL = ("thực tế", "actual")
_M16_TECHNICAL = ("kỹ thuật", "technical")


def _detect_actual_norm_col(
    cells: list[list], data_start: int, default_col: int
) -> tuple[int, str | None, int | None]:
    """Nếu có CẢ cột ĐM kỹ thuật lẫn ĐM thực tế → trả (cột thực tế, nhãn, cột kỹ thuật).

    Chỉ chọn lại khi hai cột phân biệt được: DN một cột ĐM (6 DN whitelist) không có
    nhãn "thực tế" cạnh "kỹ thuật" nên giữ nguyên cột mặc định → kết quả bất biến.
    """
    labels: dict[int, str] = {}
    for r in range(max(0, data_start - 4), data_start):
        if r >= len(cells):
            continue
        for ci, v in enumerate(cells[r]):
            s = to_str(v)
            if s:
                labels[ci] = (labels.get(ci, "") + " " + s).strip().lower()
    actual = [c for c, t in labels.items() if any(k in t for k in _M16_ACTUAL)]
    technical = [c for c, t in labels.items() if any(k in t for k in _M16_TECHNICAL)]
    if actual and technical and actual[0] != technical[0]:
        return actual[0], labels.get(actual[0]), technical[0]
    return default_col, None, None


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


def parse_m16(
    path: str | Path,
    sheet: str | None = None,
    year: int | None = None,
    officer_maps: dict[str, dict[str, int]] | None = None,
) -> M16File:
    """`officer_maps` = {vân tay form: {field: chỉ số cột}} cán bộ đã xác nhận cho DN
    này ở slot này. Vị trí của cán bộ THẮNG cả cột ĐM chọn theo nhãn (ADR #24 mục 5).
    Mẫu 16 chưa có họ biểu curate nào, nên chỉ còn hai tầng: cán bộ > dò từ khoá."""
    p = ensure_excel(Path(path))
    xls = pd.ExcelFile(p)
    cols = _M16_TT39_COLS
    data_start = _M16_TT39_DATA_START
    picked = sheet is not None
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
    if picked:
        # Trang tính do cán bộ chỉ định: dò dòng dữ liệu đầu ngay trên trang đó thay vì
        # giữ hằng số của mẫu chuẩn — trang được chỉ định thường là trang lệch mẫu.
        data_start = find_data_start(cells, "m16")
    header = parse_company_header(cells)

    # ĐM thực tế thắng ĐM kỹ thuật khi có cả hai (004). Copy trước khi sửa — `cols` là
    # dict module-level dùng chung.
    norm_col, norm_label, tech_col = _detect_actual_norm_col(cells, data_start, cols["norm_qty"])
    norm_labeled = norm_col != cols["norm_qty"]
    cols = dict(cols)
    if norm_labeled:
        cols["norm_qty"] = norm_col
    form_sig = compute_form_signature(cells, "m16", data_start)
    # Cán bộ đã chỉ cột nào thì cột đó thắng — kể cả cột ĐM vừa chọn theo nhãn: nhãn
    # là suy đoán của máy, map lưu là kết luận của người đã nhìn file.
    officer = officer_columns(officer_maps, form_sig, cols)
    cols.update(officer)
    # Cán bộ dời sang cột KHÁC → không còn đọc theo nhãn nữa, không được giữ nhãn
    # "ĐM thực tế theo nhãn X". Cán bộ xác nhận ĐÚNG cột đó thì giữ nguyên.
    norm_labeled = norm_labeled and cols["norm_qty"] == norm_col
    # Bố cục 004 có HAI cột định mức: `_detect_actual_norm_col` dời `norm_qty` sang cột
    # ĐM thực tế, và chỉ số đó chính là cột `note` của mẫu chuẩn → adapter đọc MỘT cột
    # vào HAI trường. Đo 08/08: `norms.note` bằng đúng `norm_qty` ở 880/880 dòng của
    # PILOT_004 2025. Trường mất chỗ về *chưa gán* (màn gán, lát 2) — không bịa vị trí.
    if cols.get("note") == cols["norm_qty"]:
        del cols["note"]
    evidence = evidence_m16(cells, data_start, cols, norm_labeled=norm_labeled)
    apply_officer_evidence(evidence, officer)
    # Map cột là NGUỒN, bằng chứng suy từ nó (chiều của bcct) — không lọc ngược lại.
    column_map = dict(cols)
    detail = {
        "form_signature": form_sig,
        "column_map": column_map,
        "template_id": None,
        "match_source": match_source_for(officer, None, evidence),
        "column_choices": column_choices(cells, data_start),
    }
    if norm_labeled:
        provenance = ParseProvenance(
            layout="labeled",
            detail={
                "norm_col": norm_col,
                "norm_label": norm_label,
                "technical_col": tech_col,
                **detail,
            },
            evidence=evidence,
        )
    else:
        provenance = ParseProvenance(detail=detail, evidence=evidence)

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
        provenance=provenance,
    )
