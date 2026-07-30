"""Selector vế BCCT của một (DN, kỳ) — MỘT chỗ duy nhất (ADR #23, T1).

`declaration_lines.period_year` là NHÃN NẠP (provenance), không còn là tư cách
thuộc kỳ. Tư cách tính lúc QUERY:

- dòng CÓ `declaration_date` → thuộc kỳ khi ngày nằm trong cửa sổ
  `company_periods` của kỳ đó, BẤT KỂ nhãn;
- dòng KHÔNG có ngày → quy theo nhãn (giữ hành vi `in_period` cũ);
- (DN, kỳ) chưa có cửa sổ → quy toàn bộ theo nhãn.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import and_, or_, select
from sqlalchemy.sql.elements import ColumnElement

from app.models import CompanyPeriod, DeclarationLine


def period_window(session, company_id: int, year: int) -> tuple[date, date] | None:
    """Cửa sổ `[from, to]` đã lưu của (DN, kỳ); None khi chưa có hoặc thiếu biên."""
    row = session.execute(
        select(CompanyPeriod.period_from, CompanyPeriod.period_to).where(
            CompanyPeriod.company_id == company_id,
            CompanyPeriod.period_year == year,
        )
    ).first()
    if row is None or row[0] is None or row[1] is None:
        return None
    return row[0], row[1]


def declaration_scope(session, company_id: int, year: int) -> ColumnElement[bool]:
    """Điều kiện WHERE chọn dòng BCCT thuộc (DN, kỳ) — gồm cả lọc `company_id`."""
    window = period_window(session, company_id, year)
    if window is None:
        return and_(
            DeclarationLine.company_id == company_id,
            DeclarationLine.period_year == year,
        )
    period_from, period_to = window
    return and_(
        DeclarationLine.company_id == company_id,
        or_(
            and_(
                DeclarationLine.declaration_date.is_not(None),
                DeclarationLine.declaration_date >= period_from,
                DeclarationLine.declaration_date <= period_to,
            ),
            and_(
                DeclarationLine.declaration_date.is_(None),
                DeclarationLine.period_year == year,
            ),
        ),
    )


__all__ = ["declaration_scope", "period_window"]
