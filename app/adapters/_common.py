"""Shared helpers for Excel adapters."""

from __future__ import annotations

import json
import math
import re
import unicodedata
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any


@dataclass
class CompanyHeader:
    """Metadata trích từ phần đầu file BCQT (tên DN, MST, địa chỉ, kỳ báo cáo)."""

    name: str | None = None
    tax_id: str | None = None
    address: str | None = None
    period_from: date | None = None
    period_to: date | None = None


@dataclass
class ParseIssues:
    """Ô hỏng + liên kết ngoài + ô công thức ghi thành chuỗi, của một sheet đã parse.

    `error_cells` / `external_workbooks` KHÔNG đổi giá trị số: ô hỏng vẫn ra 0.0 như
    cũ, chỉ thôi im lặng. `formula_cells` thì có đổi — giá trị đọc được từ `result`
    thay cho 0.0 — nên vẫn đếm để cán bộ biết file đã qua tay công cụ gộp/xuất nào
    đó, đếm theo TÊN TRƯỜNG (`unit_price`, `value_total`, …).
    """

    error_cells: dict[str, int] = field(default_factory=dict)
    external_workbooks: int = 0
    formula_cells: dict[str, int] = field(default_factory=dict)
    scanned: bool = False

    @property
    def error_total(self) -> int:
        return sum(self.error_cells.values())

    @property
    def formula_total(self) -> int:
        return sum(self.formula_cells.values())

    def __bool__(self) -> bool:
        return (
            bool(self.error_cells)
            or self.external_workbooks > 0
            or bool(self.formula_cells)
        )


@dataclass
class ParseProvenance:
    """Cách một file được đọc — để hiển thị + lưu, không phải hộp đen (ADR #15).

    ``layout``: ``standard`` (cột cố định) · ``extended`` (suy map từ dòng đánh số,
    chứng minh bằng đẳng thức) · ``labeled`` (chọn cột theo nhãn, vd ĐM thực tế).
    ``detail``: bằng chứng (đẳng thức, tỉ lệ khớp, nhãn cột đã chọn).
    ``evidence``: field → nguồn bằng chứng mỗi cột đã đọc (WS1, ADR #18) — header-matched
    / balance-checked / position-only. Trạng thái review suy từ đây + registry check→cột.
    """

    layout: str = "standard"
    detail: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, str] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return self.layout != "standard" or bool(self.evidence)


def count_external_workbooks(path: Path) -> int:
    """Số workbook NGOÀI mà file này lấy giá trị sang.

    Công thức trỏ sang file trên máy chủ nội bộ của DN vẫn hiện giá trị cache đúng;
    nếu liên kết gãy thì giá trị lặng lẽ về 0. Đọc danh mục zip nên rất rẻ, không
    phải mở cả workbook.
    """
    if path.suffix.lower() != ".xlsx":
        return 0
    try:
        with zipfile.ZipFile(path) as z:
            return sum(
                1 for n in z.namelist()
                if n.startswith("xl/externalLinks/externalLink") and n.endswith(".xml")
            )
    except (zipfile.BadZipFile, OSError):
        return 0


def scan_error_cells(
    path: Path, sheet: str, data_start: int, columns: Iterable[int]
) -> dict[str, int]:
    """Đếm ô lỗi Excel (#REF!, #N/A, …) trong vùng dữ liệu của các cột được đọc.

    pandas đổi ô lỗi thành NaN trước khi adapter nhìn thấy, nên chỉ đếm được ở tầng
    openpyxl/xlrd. Chỉ quét đúng cột adapter đọc — ô lỗi ở cột phụ không thành số 0
    trong dữ liệu nạp nên không tính.
    """
    wanted = {c + 1 for c in columns}  # openpyxl đánh số cột từ 1
    counts: dict[str, int] = {}
    suffix = path.suffix.lower()
    try:
        if suffix == ".xlsx":
            import openpyxl

            wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
            try:
                ws = wb[sheet]
                for row in ws.iter_rows(min_row=data_start + 1):
                    for cell in row:
                        if cell.column in wanted and cell.data_type == "e":
                            key = str(cell.value)
                            counts[key] = counts.get(key, 0) + 1
            finally:
                wb.close()
        elif suffix == ".xls":
            import xlrd

            book = xlrd.open_workbook(path)
            ws = book.sheet_by_name(sheet)
            for r in range(data_start, ws.nrows):
                for c in wanted:
                    if c - 1 >= ws.ncols:
                        continue
                    if ws.cell_type(r, c - 1) == xlrd.XL_CELL_ERROR:
                        key = xlrd.error_text_from_code.get(ws.cell_value(r, c - 1), "#ERR")
                        counts[key] = counts.get(key, 0) + 1
    except Exception:  # noqa: BLE001 — chẩn đoán không được làm hỏng việc parse
        return counts
    return counts


def formula_cell_result(value: Any) -> float | None:
    """Số nằm trong ô công thức bị ghi thành chuỗi `{"formula":…,"result":…}`.

    Một số công cụ gộp/xuất file ghi ô công thức thành chuỗi JSON thay vì số. Ô như
    vậy KHÔNG parse được thành float nên trước đây thành 0.0 — số dòng và tập khoá
    vẫn đúng, chỉ tiền sai, nên không kiểm tra nào bắt được (ca 006: 2.076 ô,
    28.563.550.970,35 đ). `result` là giá trị Excel đã tính, đọc nó là đọc đúng ô.

    Trả None khi không phải dạng đó hoặc `result` không phải số — người gọi giữ
    nguyên đường xử lý cũ.
    """
    if not isinstance(value, str):
        return None
    s = value.strip()
    if not (s.startswith("{") and '"formula"' in s and '"result"' in s):
        return None
    try:
        obj = json.loads(s)
    except ValueError:
        return None
    if not isinstance(obj, dict) or "formula" not in obj or "result" not in obj:
        return None
    result = obj["result"]
    if isinstance(result, bool) or not isinstance(result, (int, float)):
        return None
    out = float(result)
    return None if math.isnan(out) else out


def to_float(value: Any) -> float:
    """Convert any cell value to float, defaulting to 0.0."""
    if value is None:
        return 0.0
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return 0.0 if math.isnan(float(value)) else float(value)
    s = str(value).strip()
    if not s:
        return 0.0
    formula_result = formula_cell_result(s)
    if formula_result is not None:
        return formula_result
    s = s.replace(",", "").replace(" ", "")
    try:
        return float(s)
    except ValueError:
        return 0.0


def to_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    s = str(value).strip()
    return s or None


def to_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s.split()[0], fmt).date()
        except ValueError:
            continue
    return None


_DATE_RE = re.compile(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})")


def find_date_in_text(text: str) -> date | None:
    m = _DATE_RE.search(text)
    if not m:
        return None
    d, mo, y = (int(g) for g in m.groups())
    try:
        return date(y, mo, d)
    except ValueError:
        return None


_JUNK_CODES = {"", ".", "..", "...", "-", "--", "---", "_", "n/a", "na", "nan", "none", "null"}


def normalize_code(code: str | None) -> str | None:
    """Chuẩn hoá mã: bỏ khoảng trắng đầu/cuối, loại các giá trị "không mã".

    Trả None với mọi placeholder phổ biến (".", "-", "n/a", "nan", …) để
    các check không bị xáo trộn bởi dòng tổng/tiêu đề trong tờ khai Excel.
    """
    if code is None:
        return None
    s = str(code).strip()
    if not s or s.lower() in _JUNK_CODES:
        return None
    return s


def normalize_name(text: str | None) -> str | None:
    if text is None:
        return None
    s = unicodedata.normalize("NFC", str(text).strip())
    return s or None


def parse_company_header(cells: list[list[Any]], scan_rows: int = 8) -> CompanyHeader:
    """Scan top rows for company metadata."""
    header = CompanyHeader()
    for row in cells[:scan_rows]:
        for cell in row:
            s = to_str(cell)
            if not s:
                continue
            lower = s.lower()
            if "tên tổ chức" in lower or "tên doanh nghiệp" in lower:
                _, _, rest = s.partition(":")
                header.name = normalize_name(rest) or header.name
            elif "địa chỉ" in lower:
                _, _, rest = s.partition(":")
                header.address = normalize_name(rest) or header.address
            elif "mã số thuế" in lower or lower.startswith("mst"):
                _, _, rest = s.partition(":")
                mst = re.search(r"\d{10,14}", rest or s)
                if mst:
                    header.tax_id = mst.group(0)
            elif "kỳ báo cáo" in lower or "từ ngày" in lower:
                # parse two dates
                dates = _DATE_RE.findall(s)
                if dates:
                    d, mo, y = (int(x) for x in dates[0])
                    try:
                        header.period_from = date(y, mo, d)
                    except ValueError:
                        pass
                    if len(dates) > 1:
                        d2, mo2, y2 = (int(x) for x in dates[1])
                        try:
                            header.period_to = date(y2, mo2, d2)
                        except ValueError:
                            pass
    # tax id may live in a cell by itself
    if header.tax_id is None:
        for row in cells[:scan_rows]:
            for cell in row:
                s = to_str(cell)
                if s and re.fullmatch(r"\d{10,14}", s):
                    header.tax_id = s
                    break
            if header.tax_id:
                break
    return header


def safe_get(row: list[Any], index: int) -> Any:
    """Return row[index] or None when missing."""
    if index < 0 or index >= len(row):
        return None
    return row[index]


def ensure_excel(path: Path) -> Path:
    """Resolve real path; raise informative error if missing."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Excel file not found: {p}")
    return p
