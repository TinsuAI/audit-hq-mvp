from __future__ import annotations

from datetime import date

from app.adapters._common import CompanyHeader
from app.models import Company, CompanyPeriod
from app.pipeline.period import (
    default_bounds,
    in_period,
    load_period_windows,
    resolve_period_bounds,
)


def test_load_period_windows_only_returns_custom(session, company: Company):
    session.add_all([
        CompanyPeriod(  # dương lịch → KHÔNG trả về
            company_id=company.id, period_year=2023,
            period_from=date(2023, 1, 1), period_to=date(2023, 12, 31),
        ),
        CompanyPeriod(  # năm tài chính → trả về
            company_id=company.id, period_year=2025,
            period_from=date(2025, 4, 1), period_to=date(2026, 3, 31),
        ),
    ])
    session.commit()
    windows = load_period_windows(session, company.id)
    assert windows == {2025: (date(2025, 4, 1), date(2026, 3, 31))}


def test_in_period_keeps_fiscal_row_that_calendar_filter_dropped():
    pf, pt = date(2024, 4, 1), date(2025, 3, 31)
    d = date(2025, 2, 15)  # Feb 2025 thuộc năm tài chính FY2024
    assert in_period(d, pf, pt) is True
    assert d.year != 2024  # lọc `== year` cũ sẽ loại dòng này


def test_in_period_drops_row_outside_window():
    pf, pt = date(2024, 4, 1), date(2025, 3, 31)
    assert in_period(date(2024, 3, 31), pf, pt) is False
    assert in_period(date(2025, 4, 1), pf, pt) is False


def test_in_period_keeps_boundaries_inclusive():
    pf, pt = date(2024, 4, 1), date(2025, 3, 31)
    assert in_period(pf, pf, pt) is True
    assert in_period(pt, pf, pt) is True


def test_in_period_keeps_none_date():
    # dòng thiếu ngày → quy về kỳ đang nạp (không suy được năm)
    assert in_period(None, date(2024, 4, 1), date(2025, 3, 31)) is True


def test_default_bounds_calendar_when_no_header():
    assert default_bounds(None, 2024) == (date(2024, 1, 1), date(2024, 12, 31))


def test_default_bounds_uses_complete_header():
    h = CompanyHeader(period_from=date(2024, 4, 1), period_to=date(2025, 3, 31))
    assert default_bounds(h, 2024) == (date(2024, 4, 1), date(2025, 3, 31))


def test_default_bounds_calendar_when_header_incomplete():
    h = CompanyHeader(period_from=date(2024, 4, 1), period_to=None)
    assert default_bounds(h, 2024) == (date(2024, 1, 1), date(2024, 12, 31))


def _get(session, company_id, year) -> CompanyPeriod | None:
    return (
        session.query(CompanyPeriod)
        .filter_by(company_id=company_id, period_year=year)
        .one_or_none()
    )


def test_no_header_defaults_to_calendar_year(session, company: Company):
    pf, pt = resolve_period_bounds(session, company.id, 2024, header=None)
    assert (pf, pt) == (date(2024, 1, 1), date(2024, 12, 31))
    row = _get(session, company.id, 2024)
    assert row is not None and row.is_manual is False


def test_header_with_both_dates_used(session, company: Company):
    header = CompanyHeader(period_from=date(2024, 4, 1), period_to=date(2025, 3, 31))
    pf, pt = resolve_period_bounds(session, company.id, 2024, header=header)
    assert (pf, pt) == (date(2024, 4, 1), date(2025, 3, 31))
    assert _get(session, company.id, 2024).period_to == date(2025, 3, 31)


def test_header_missing_one_date_falls_back_to_calendar(session, company: Company):
    header = CompanyHeader(period_from=date(2024, 4, 1), period_to=None)
    pf, pt = resolve_period_bounds(session, company.id, 2024, header=header)
    assert (pf, pt) == (date(2024, 1, 1), date(2024, 12, 31))


def test_manual_row_is_not_overwritten_by_header(session, company: Company):
    session.add(
        CompanyPeriod(
            company_id=company.id,
            period_year=2024,
            period_from=date(2024, 4, 1),
            period_to=date(2025, 3, 31),
            is_manual=True,
        )
    )
    session.commit()

    header = CompanyHeader(period_from=date(2024, 1, 1), period_to=date(2024, 12, 31))
    pf, pt = resolve_period_bounds(session, company.id, 2024, header=header)

    assert (pf, pt) == (date(2024, 4, 1), date(2025, 3, 31))
    row = _get(session, company.id, 2024)
    assert row.is_manual is True
    assert row.period_from == date(2024, 4, 1)


def test_auto_row_is_refreshed_on_reingest(session, company: Company):
    resolve_period_bounds(session, company.id, 2024, header=None)  # calendar
    header = CompanyHeader(period_from=date(2024, 4, 1), period_to=date(2025, 3, 31))
    pf, pt = resolve_period_bounds(session, company.id, 2024, header=header)

    assert (pf, pt) == (date(2024, 4, 1), date(2025, 3, 31))
    # vẫn đúng 1 dòng (upsert, không tạo trùng)
    assert (
        session.query(CompanyPeriod)
        .filter_by(company_id=company.id, period_year=2024)
        .count()
        == 1
    )
