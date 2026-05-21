"""Phát hiện loại hình doanh nghiệp từ mã loại hình BCCT.

Theo §4.0 đề án:
    DNCX    — Doanh nghiệp chế xuất:     nhập E11/E15/E13 · xuất E42
    GIA_CONG — Gia công thương nhân NN: nhập E21/E23     · xuất E52/E54
    SXXK    — Sản xuất xuất khẩu:        nhập E31/E33    · xuất E62

Một số tờ khai chung: B13 (tái xuất), A42 (chuyển mục đích sử dụng nội địa).
"""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import DeclarationLine


class CompanyType(StrEnum):
    DNCX = "DNCX"
    GIA_CONG = "GIA_CONG"
    SXXK = "SXXK"
    UNKNOWN = "UNKNOWN"


IMPORT_CODES = {
    CompanyType.DNCX: {"E11", "E15", "E13"},
    CompanyType.GIA_CONG: {"E21", "E23"},
    CompanyType.SXXK: {"E31", "E33"},
}

EXPORT_CODES = {
    CompanyType.DNCX: {"E42"},
    CompanyType.GIA_CONG: {"E52", "E54"},
    CompanyType.SXXK: {"E62"},
}

# Tờ khai dùng chung, không phân biệt loại hình DN.
SHARED_CODES = {"B13", "A42"}


def detect_company_type(session: Session, company_id: int, year: int) -> CompanyType:
    """Đếm số dòng BCCT theo mã loại hình; chọn nhóm có nhiều dòng nhất."""
    rows = session.execute(
        select(DeclarationLine.customs_code, func.count())
        .where(
            DeclarationLine.company_id == company_id,
            DeclarationLine.period_year == year,
        )
        .group_by(DeclarationLine.customs_code)
    ).all()

    counts: dict[CompanyType, int] = {t: 0 for t in CompanyType if t != CompanyType.UNKNOWN}
    for code, n in rows:
        if not code:
            continue
        for t in counts:
            if code in IMPORT_CODES[t] or code in EXPORT_CODES[t]:
                counts[t] += n

    best_type, best_count = max(counts.items(), key=lambda kv: kv[1])
    return best_type if best_count > 0 else CompanyType.UNKNOWN


def import_codes_for(company_type: CompanyType) -> set[str]:
    return IMPORT_CODES.get(company_type, set())


def export_codes_for(company_type: CompanyType) -> set[str]:
    return EXPORT_CODES.get(company_type, set())
