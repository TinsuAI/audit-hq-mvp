"""Adapter for Báo cáo Hàng Chi Tiết (BCCT) — xuất từ VNACCS/ECUS."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pandas as pd

from app.adapters._common import (
    ParseIssues,
    ParseProvenance,
    ensure_excel,
    formula_cell_result,
    normalize_code,
    normalize_name,
    safe_get,
    to_date,
    to_float,
    to_str,
)
from app.adapters.evidence import HEADER_MATCHED, POSITION_ONLY
from app.adapters.form_signature import compute_form_signature
from app.adapters.layout import find_data_start, norm
from app.adapters.sheet_select import select_sheet
from app.adapters.templates import (
    apply_officer_evidence,
    match_source_for,
    officer_columns,
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
    sheet: str | None = None
    provenance: ParseProvenance = field(default_factory=ParseProvenance)
    issues: ParseIssues = field(default_factory=ParseIssues)


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

# --- Bản đồ cột theo NHÃN tiêu đề (mở rộng mô hình bằng chứng WS1, ADR #18) ---
#
# `_COL` ở trên là bố cục ECUS "BC chi tiết" (tiêu đề dòng 9, 54 cột) — 8 DN đã kiểm
# đều dùng nó. Bố cục khác (thiếu "Địa điểm dỡ hàng"/"Ghi chú", hoặc chèn thêm cột
# "Tên") đẩy mọi trường sang cột khác mà đọc theo `_COL` vẫn "thành công": `quantity`
# ra trị giá NT, `company_name` ra ngày hợp đồng, không ngoại lệ nào phát ra. Vì thế
# cột suy từ NHÃN trước; `_COL` chỉ dùng khi chính các nhãn đã khớp chứng minh file
# đúng bố cục chuẩn.
#
# So khớp là BẰNG ĐÚNG chuỗi đã `norm`, KHÔNG phải "chứa": `Đơn giá` (24) vs `Đơn giá
# tính thuế` (25), `Tổng số lượng` (26) vs `Tổng số lượng 2` (28), `Đơn vị tính` (27)
# vs `Đơn vị tính 2` (29) là các cột KHÁC nhau — khớp theo "chứa" lấy nhầm cột đầu tiên.
# Alias xếp theo THỨ TỰ ƯU TIÊN: alias đầu là nhãn của bố cục chuẩn.
_LABEL_ALIASES: dict[str, tuple[str, ...]] = {
    "declaration_no": ("Số TK",),
    "declaration_date": ("Ngày ĐK",),
    "customs_code": ("Mã loại hình",),
    "line_no": ("STT hàng",),
    "item_code": ("Mã NPL/SP", "Mã hàng"),
    "hs_code": ("Mã HS",),
    "item_name": ("Tên hàng",),
    "origin": ("Xuất xứ", "Nước xuất xứ"),
    "unit_price": ("Đơn giá", "Đơn giá hóa đơn"),
    "quantity": ("Tổng số lượng", "Số lượng"),
    "unit": ("Đơn vị tính",),
    "currency": ("Đơn vị tiền tệ", "Ng.tệ hóa đơn"),
    "value_foreign": ("Trị giá NT", "Trị giá hóa đơn"),
    "value_total": ("Tổng trị giá", "Trị giá tính thuế"),
    "tax_total": ("Tổng tiền thuế",),
    "company_tax_id": ("Mã doanh nghiệp",),
    "company_name": ("Tên doanh nghiệp",),
    "partner": ("Tên đối tác",),
    "invoice_no": ("Số hóa đơn", "Số hóa đơn TM"),
}

# Chuẩn hoá một lần lúc import. `norm` bỏ dấu, thay `đ/Đ` và GỘP whitespace, nên ô
# tiêu đề xuống dòng ("Tổng\nsố lượng") hay hai dấu cách vẫn khớp; `strip().lower()`
# thì không, và trượt khớp là rơi im lặng về `_COL` — đúng lớp lỗi cần diệt.
_ALIASES: dict[str, tuple[str, ...]] = {
    f: tuple(norm(a) for a in aliases) for f, aliases in _LABEL_ALIASES.items()
}
_KNOWN_LABELS = {alias for aliases in _ALIASES.values() for alias in aliases}

# Ba trường này thiếu là không dựng được dòng dữ liệu nào dùng được.
_REQUIRED_FIELDS = ("declaration_no", "item_code", "quantity")
# Tiêu đề nằm ngay trên dòng dữ liệu, nhưng có bố cục chèn dòng đánh số ở giữa.
_HEADER_LOOKBACK = 6
_MIN_HEADER_LABELS = 2
# Số nhãn tối thiểu phải cùng đúng vị trí `_COL` mới coi là đã xác nhận bố cục chuẩn.
# Một nhãn là trùng hợp: bố cục 81 cột `BaoCaoHangChiTietMH` đọc trôi bằng `_COL` chỉ
# vì `Số TK` tình cờ cùng cột.
_MIN_POSITION_ANCHORS = 3


class BcctColumnError(ValueError):
    """Không dựng được bản đồ cột BCCT — TỪ CHỐI parse thay vì đọc nhầm cột.

    Đọc nhầm cột không sinh lỗi nào: mọi dòng vẫn nạp, chỉ là nạp sai trường. Cùng
    lập luận với `IngestPlanError` (`app/pipeline/ingest.py`): hỏng ồn hơn ghi sai.
    """


def _norm_cells(row: list) -> dict[int, str]:
    """Cột → nhãn đã `norm` của các ô KHÔNG rỗng trong một dòng."""
    out: dict[int, str] = {}
    for i, raw in enumerate(row):
        s = to_str(raw)
        if s:
            out[i] = norm(s)
    return out


def _find_header_row(cells: list[list], data_start: int) -> tuple[int | None, dict[int, str]]:
    """Dòng tiêu đề = dòng khớp NHIỀU nhãn đã biết nhất trong cửa sổ ngay trên dữ liệu."""
    best_row: int | None = None
    best_hits = 0
    best: dict[int, str] = {}
    for r in range(max(0, data_start - _HEADER_LOOKBACK), min(data_start, len(cells))):
        labels = _norm_cells(cells[r])
        hits = sum(1 for v in labels.values() if v in _KNOWN_LABELS)
        if hits > best_hits:
            best_row, best_hits, best = r, hits, labels
    if best_hits < _MIN_HEADER_LABELS:
        return None, {}
    return best_row, best


def _band_labels(cells: list[list], header_row: int, data_start: int) -> dict[int, set[str]]:
    """Nhãn ứng viên mỗi cột trong vùng tiêu đề `[header_row - 1, data_start)`.

    Giữ từng ô làm MỘT ứng viên riêng và thêm chuỗi NỐI cả vùng: tiêu đề hai tầng (ô
    gộp cha "Tổng số lượng" + ô con "2") chỉ đọc được khi nối, còn khớp bằng đúng
    chuỗi (phân biệt `Đơn giá` với `Đơn giá tính thuế`) chỉ đúng khi từng ô còn riêng.
    Vùng bắt đầu ở `header_row - 1` chứ không phải đầu cửa sổ: các dòng tổng ở đầu
    file ("Tổng trị giá:", "Tổng tiền thuế:") nằm ở cột 0 và sẽ tranh nhãn với cột thật.
    """
    per_col: dict[int, set[str]] = {}
    joined: dict[int, list[str]] = {}
    for r in range(max(0, header_row - 1), min(data_start, len(cells))):
        for i, v in _norm_cells(cells[r]).items():
            per_col.setdefault(i, set()).add(v)
            joined.setdefault(i, []).append(v)
    for i, parts in joined.items():
        if len(parts) > 1:
            per_col[i].add(" ".join(parts))
    return per_col


def _resolve_by_label(header_cells: dict[int, str], band: dict[int, set[str]]) -> dict[str, int]:
    """field → cột theo nhãn: dòng tiêu đề trước, cả vùng tiêu đề sau.

    Hai lượt để nhãn ở dòng tiêu đề luôn thắng một nhãn tình cờ trùng ở dòng khác;
    lượt vùng chỉ vớt trường mà dòng tiêu đề không có (tiêu đề tách hai tầng).
    """
    head = {c: {label} for c, label in header_cells.items()}
    out: dict[str, int] = {}
    for fld, aliases in _ALIASES.items():
        col = _first_column(aliases, head)
        if col is None:
            col = _first_column(aliases, band)
        if col is not None:
            out[fld] = col
    return out


def _first_column(aliases: tuple[str, ...], labels: dict[int, set[str]]) -> int | None:
    """Cột trái nhất mang một trong các alias, xét alias theo thứ tự ưu tiên."""
    for alias in aliases:
        for c in sorted(labels):
            if alias in labels[c]:
                return c
    return None


def _reject_collisions(col: dict[str, int], source: str) -> None:
    """Hai trường về cùng một cột thì bản đồ sai — từ chối thay vì nhân đôi một cột."""
    seen: dict[int, str] = {}
    clashes: list[str] = []
    for fld, c in sorted(col.items()):
        if c in seen:
            clashes.append(f"{seen[c]} và {fld} cùng cột {c}")
        else:
            seen[c] = fld
    if clashes:
        raise BcctColumnError(
            f"{source}: bản đồ cột BCCT không đơn ánh ({'; '.join(clashes)}). "
            "Từ chối đọc để không nạp cùng một cột cho hai trường."
        )


def _resolve_columns(
    cells: list[list], data_start: int, source: str
) -> tuple[dict[str, int], dict[str, str], int | None]:
    """Bản đồ cột + nguồn bằng chứng mỗi trường + dòng tiêu đề đã dò được.

    `_COL` chỉ được dùng khi CHÍNH các nhãn đã khớp xác nhận bố cục chuẩn: đủ
    `_MIN_POSITION_ANCHORS` neo và mọi neo đúng vị trí `_COL`. Một neo lệch là bác bỏ
    `_COL` cho cả file — bố cục 50 cột lệch từ cột 6 trở đi mà `Số TK` / `Ngày ĐK` /
    `Mã loại hình` vẫn trùng vị trí.
    """
    hrow, header_cells = _find_header_row(cells, data_start)
    by_label: dict[str, int] = {}
    if hrow is not None:
        by_label = _resolve_by_label(header_cells, _band_labels(cells, hrow, data_start))
    anchors = [f for f in by_label if f in _COL]
    at_position = all(by_label[f] == _COL[f] for f in anchors)
    position_ok = len(anchors) >= _MIN_POSITION_ANCHORS and at_position
    col: dict[str, int] = dict(_COL) if position_ok else {}
    col.update(by_label)
    _reject_collisions(col, source)

    missing = [f for f in _REQUIRED_FIELDS if f not in col]
    if missing:
        found = "không dò được dòng tiêu đề"
        if hrow is not None:
            found = f"dòng tiêu đề {hrow}, {len(by_label)} nhãn khớp"
        raise BcctColumnError(
            f"{source}: không xác định được cột BCCT cho {', '.join(missing)} "
            f"({found}). Nhãn tiêu đề cũng không xác nhận bố cục chuẩn nên không suy "
            "được theo vị trí — từ chối đọc để không lấy nhầm cột."
        )
    evidence = {f: (HEADER_MATCHED if f in by_label else POSITION_ONLY) for f in col}
    return col, evidence, hrow


def _split_item_code_name(raw_name: str | None) -> tuple[str | None, str | None]:
    """BCCT col `Tên hàng` thường là `MA#&Tên`. Tách ra nếu cần."""
    if not raw_name:
        return None, None
    if "#&" in raw_name:
        code, _, name = raw_name.partition("#&")
        return normalize_code(code), normalize_name(name)
    return None, normalize_name(raw_name)


def parse_bcct(
    path: str | Path,
    sheet: str | None = None,
    year: int | None = None,
    officer_maps: dict[str, dict[str, int]] | None = None,
) -> BcctFile:
    """`officer_maps` = {vân tay form: {field: chỉ số cột}} cán bộ đã xác nhận cho DN
    này ở slot này. Vị trí của cán bộ THẮNG cả bản đồ suy từ nhãn tiêu đề (ADR #24
    mục 5). Tờ khai chưa có họ biểu curate nào, nên chỉ hai tầng: cán bộ > nhãn."""
    p = ensure_excel(Path(path))
    xls = pd.ExcelFile(p)
    data_start = _DATA_START
    picked = sheet is not None
    if sheet is None:
        # Sheet tổng hợp (cấp tờ khai) cũng có số tờ khai ở cột 1 nên khớp
        # `_DECLARATION_RE` — chọn nhầm nó sinh dòng SAI chứ không phải 0 dòng.
        choice = select_sheet(p, "bcct", year)
        sheet, data_start = choice.name, choice.data_start
    df = pd.read_excel(xls, sheet_name=sheet, header=None)
    cells = df.values.tolist()
    if picked:
        # Trang tính do cán bộ chỉ định: dò dòng dữ liệu đầu ngay trên trang đó thay vì
        # giữ hằng số của mẫu chuẩn — trang được chỉ định thường là trang lệch mẫu.
        data_start = find_data_start(cells, "bcct")
    col, evidence, header_row = _resolve_columns(cells, data_start, p.name)
    form_sig = compute_form_signature(cells, "bcct", data_start)
    officer = officer_columns(officer_maps, form_sig, col)
    col.update(officer)
    # Cổng trùng cột chạy LẠI sau khi áp map cán bộ (#95): lượt kiểm trong
    # `_resolve_columns` chỉ soi bản đồ suy từ nhãn, nên một map lưu đưa hai trường về
    # cùng một cột sẽ lọt qua và cả hai trường cùng đọc một cột, im lặng.
    _reject_collisions(col, p.name)
    apply_officer_evidence(evidence, officer)

    company_tax_id: str | None = None
    company_name: str | None = None
    rows: list[BcctRow] = []

    formula_cells: dict[str, int] = {}

    def cell(row: list, name: str):
        idx = col.get(name)
        return None if idx is None else safe_get(row, idx)

    def number(row: list, name: str) -> float:
        """`to_float` + đếm ô công thức bị ghi thành chuỗi JSON, theo tên trường."""
        raw = cell(row, name)
        if formula_cell_result(raw) is not None:
            formula_cells[name] = formula_cells.get(name, 0) + 1
        return to_float(raw)

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
                quantity=number(raw, "quantity") or None,
                unit=normalize_code(to_str(cell(raw, "unit"))),
                unit_price=number(raw, "unit_price") or None,
                currency=normalize_code(to_str(cell(raw, "currency"))),
                value_foreign=number(raw, "value_foreign") or None,
                value_total=number(raw, "value_total") or None,
                tax_total=number(raw, "tax_total") or None,
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
        provenance=ParseProvenance(
            # `labeled` = bản đồ LỆCH `_COL`, tức đọc theo vị trí sẽ sai. Bố cục chuẩn
            # vẫn để `standard` để badge bố cục không kêu ở 35/38 file bình thường.
            layout="standard" if col == _COL else "labeled",
            detail={
                "form_signature": form_sig,
                "column_map": col,
                "header_row": header_row,
                "template_id": None,
                "match_source": match_source_for(officer, None, evidence),
            },
            evidence=evidence,
        ),
        issues=ParseIssues(formula_cells=formula_cells),
    )
