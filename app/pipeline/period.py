"""Suy cửa sổ kỳ báo cáo (period_from, period_to) cho một (company, period_year).

Ưu tiên: bản `is_manual` cán bộ đã lưu > tiêu đề file (đủ cả 2 ngày) > dương lịch.
Upsert vào `company_periods` nhưng KHÔNG ghi đè bản `is_manual=True`.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select

from app.adapters._common import CompanyHeader
from app.models import CompanyPeriod


def default_bounds(
    header: CompanyHeader | None, period_year: int
) -> tuple[date, date]:
    """Cửa sổ kỳ suy tự động: tiêu đề file khi CÓ ĐỦ cả 2 ngày, ngược lại dương lịch."""
    period_from = header.period_from if header else None
    period_to = header.period_to if header else None
    if period_from is None or period_to is None:
        return date(period_year, 1, 1), date(period_year, 12, 31)
    return period_from, period_to


def in_period(
    declaration_date: date | None, period_from: date, period_to: date
) -> bool:
    """Dòng BCCT thuộc kỳ khi ngày tờ khai nằm trong `[from, to]` (bao gồm biên).
    Dòng thiếu ngày → quy về kỳ đang nạp (không suy được năm)."""
    if declaration_date is None:
        return True
    return period_from <= declaration_date <= period_to


def load_period_windows(session, company_id: int) -> dict[int, tuple[date, date]]:
    """`{period_year: (from, to)}` CHỈ cho kỳ KHÁC dương lịch — để UI hiện nhãn kỳ
    (năm tài chính) ở nơi vốn chỉ in "Năm N". Kỳ dương lịch bỏ qua (không cần chú)."""
    out: dict[int, tuple[date, date]] = {}
    for r in session.scalars(
        select(CompanyPeriod).where(CompanyPeriod.company_id == company_id)
    ).all():
        if (
            r.period_from is not None
            and r.period_to is not None
            and (r.period_from, r.period_to)
            != (date(r.period_year, 1, 1), date(r.period_year, 12, 31))
        ):
            out[r.period_year] = (r.period_from, r.period_to)
    return out


def resolve_period_bounds(
    session,
    company_id: int,
    period_year: int,
    header: CompanyHeader | None = None,
) -> tuple[date, date]:
    existing = session.scalar(
        select(CompanyPeriod).where(
            CompanyPeriod.company_id == company_id,
            CompanyPeriod.period_year == period_year,
        )
    )
    if existing is not None and existing.is_manual:
        return existing.period_from, existing.period_to

    period_from, period_to = default_bounds(header, period_year)

    if existing is None:
        session.add(
            CompanyPeriod(
                company_id=company_id,
                period_year=period_year,
                period_from=period_from,
                period_to=period_to,
                is_manual=False,
            )
        )
    else:
        existing.period_from = period_from
        existing.period_to = period_to
    session.flush()
    return period_from, period_to
