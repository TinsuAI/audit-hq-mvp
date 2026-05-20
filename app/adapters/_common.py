"""Shared helpers for Excel adapters."""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
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


def normalize_code(code: str | None) -> str | None:
    """Chuẩn hoá mã: bỏ khoảng trắng đầu/cuối, không đụng nội dung."""
    if code is None:
        return None
    s = str(code).strip()
    return s or None


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
