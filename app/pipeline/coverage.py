"""Độ phủ BCCT của một (DN, kỳ) — TÍNH lúc render, không lưu (ADR #23 T1).

Từ #48, ingest lưu TRỌN mọi dòng BCCT parse được; dòng ngoài cửa sổ kỳ không còn bị
bỏ im lặng mà được ĐẾM để báo. Ba số của banner trang tài liệu:

- `out_of_window` — dòng mang nhãn kỳ này nhưng ngày tờ khai nằm ngoài cửa sổ;
  vẫn lưu, thuộc kỳ khác lúc query (xem `app.checks.scope`).
- `undated` — dòng không có ngày tờ khai, quy theo nhãn nạp.
- `cross_label_duplicates` — dòng THUỘC kỳ này mà khoá (`declaration_no`, `line_no`;
  `line_no` NULL → (`declaration_no`, `item_code`)) đã tồn tại ở nhãn kỳ khác cùng DN.

KHÔNG dedup, KHÔNG chặn: số lượng có thể lệch giữa hai bản export nên mọi auto-pick
là đoán — cán bộ sửa file nguồn.

Tính lúc đọc (không lưu cột đếm) để số vẫn đúng sau khi cán bộ sửa cửa sổ kỳ mà
không nạp lại (#49).
"""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import aliased

from app.checks.scope import declaration_scope, period_window
from app.models import CompanyPeriod, DeclarationLine


@dataclass(frozen=True)
class BcctCoverage:
    """Ba số cảnh báo + số dòng thuộc kỳ của một (DN, kỳ)."""

    label_rows: int
    in_scope: int
    out_of_window: int
    undated: int
    cross_label_duplicates: int

    @property
    def has_warning(self) -> bool:
        return bool(self.out_of_window or self.undated or self.cross_label_duplicates)


def _count(session, condition) -> int:
    return session.scalar(
        select(func.count()).select_from(DeclarationLine).where(condition)
    ) or 0


def _cross_label_duplicate_condition() -> object:
    """Khoá trùng ở nhãn kỳ KHÁC, cùng DN. `line_no` NULL → so bằng `item_code`."""
    other = aliased(DeclarationLine)
    return exists(
        select(other.id).where(
            other.company_id == DeclarationLine.company_id,
            other.period_year != DeclarationLine.period_year,
            other.declaration_no == DeclarationLine.declaration_no,
            or_(
                and_(
                    DeclarationLine.line_no.is_not(None),
                    other.line_no == DeclarationLine.line_no,
                ),
                and_(
                    DeclarationLine.line_no.is_(None),
                    other.line_no.is_(None),
                    other.item_code == DeclarationLine.item_code,
                ),
            ),
        )
    )


def bcct_coverage(session, company_id: int, year: int) -> BcctCoverage:
    labelled = and_(
        DeclarationLine.company_id == company_id,
        DeclarationLine.period_year == year,
    )
    scope = declaration_scope(session, company_id, year)
    window = period_window(session, company_id, year)

    if window is None:
        out_of_window = 0
    else:
        period_from, period_to = window
        out_of_window = _count(
            session,
            and_(
                labelled,
                DeclarationLine.declaration_date.is_not(None),
                or_(
                    DeclarationLine.declaration_date < period_from,
                    DeclarationLine.declaration_date > period_to,
                ),
            ),
        )

    return BcctCoverage(
        label_rows=_count(session, labelled),
        in_scope=_count(session, scope),
        out_of_window=out_of_window,
        undated=_count(session, and_(labelled, DeclarationLine.declaration_date.is_(None))),
        cross_label_duplicates=_count(
            session, and_(scope, _cross_label_duplicate_condition())
        ),
    )


def _month_end(year: int, month: int) -> date:
    return date(year, month, monthrange(year, month)[1])


def _months_between(period_from: date, period_to: date) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    y, m = period_from.year, period_from.month
    while (y, m) <= (period_to.year, period_to.month):
        out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def coverage_gaps(session, company_id: int, year: int) -> list[tuple[date, date]]:
    """Các khoảng ngày trong cửa sổ kỳ KHÔNG có dòng tờ khai nào (#49).

    Đếm theo tháng: tháng không có dòng nào là tháng thiếu; các tháng thiếu liền
    nhau gộp thành MỘT khoảng, cắt theo biên cửa sổ. Kỳ chưa có dòng nào trả `[]`
    — "chưa nạp" đã có nhãn trạng thái riêng, không phải "thiếu khoảng".
    """
    window = period_window(session, company_id, year)
    if window is None:
        return []
    period_from, period_to = window

    present = {
        (d.year, d.month)
        for (d,) in session.execute(
            select(DeclarationLine.declaration_date)
            .where(
                declaration_scope(session, company_id, year),
                DeclarationLine.declaration_date.is_not(None),
            )
            .distinct()
        ).all()
    }
    if not present:
        return []

    gaps: list[tuple[date, date]] = []
    run: list[tuple[int, int]] = []
    for ym in _months_between(period_from, period_to):
        if ym in present:
            if run:
                gaps.append(_run_to_range(run, period_from, period_to))
                run = []
        else:
            run.append(ym)
    if run:
        gaps.append(_run_to_range(run, period_from, period_to))
    return gaps


def _run_to_range(
    run: list[tuple[int, int]], period_from: date, period_to: date
) -> tuple[date, date]:
    start = max(date(run[0][0], run[0][1], 1), period_from)
    end = min(_month_end(*run[-1]), period_to)
    return start, end


def overlapping_periods(session, company_id: int, year: int) -> list[int]:
    """Nhãn kỳ KHÁC của cùng DN có cửa sổ giao với cửa sổ kỳ này.

    Chồng lấn là CẢNH BÁO, không phải lỗi: kỳ chuyển tiếp khi đổi niên độ hợp pháp
    (khoản 4 Điều 2 Luật 56/2024 — gộp ≤ 3 kỳ tháng liên tiếp, tối đa 15 tháng).
    """
    window = period_window(session, company_id, year)
    if window is None:
        return []
    period_from, period_to = window
    rows = session.execute(
        select(CompanyPeriod.period_year, CompanyPeriod.period_from, CompanyPeriod.period_to)
        .where(
            CompanyPeriod.company_id == company_id,
            CompanyPeriod.period_year != year,
            CompanyPeriod.period_from.is_not(None),
            CompanyPeriod.period_to.is_not(None),
        )
    ).all()
    return sorted(
        y for y, pf, pt in rows if pf <= period_to and period_from <= pt
    )


def declaration_date_span(session, company_id: int, year: int) -> tuple[date, date] | None:
    """min/max `declaration_date` của các dòng THUỘC kỳ; None khi không dòng nào có ngày."""
    row = session.execute(
        select(
            func.min(DeclarationLine.declaration_date),
            func.max(DeclarationLine.declaration_date),
        ).where(
            declaration_scope(session, company_id, year),
            DeclarationLine.declaration_date.is_not(None),
        )
    ).first()
    if row is None or row[0] is None or row[1] is None:
        return None
    return row[0], row[1]


__all__ = [
    "BcctCoverage",
    "bcct_coverage",
    "coverage_gaps",
    "declaration_date_span",
    "overlapping_periods",
]
