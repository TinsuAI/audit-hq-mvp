"""#66 — cửa sổ kỳ phải hợp lệ, kiểm ở CẢ hai đường ghi.

Ca thật đẻ ra vé này: HIEP_QUANG kỳ 2024 nhận cửa sổ 01/01/2021–31/12/2021 vì thư mục
2024 có lẫn một bản sao báo cáo 2021, header của nó được `default_bounds` nhận nguyên.
Không màn nào báo. Hậu quả: lúc nạp bỏ hết dòng ngày 2024, lúc truy vấn
`declaration_scope` kéo dòng 2021 sang kỳ 2024.

Cửa sổ vào DB qua hai đường — cán bộ nhập tay, và hệ suy từ header file. Lỗi trên đến
từ đường thứ hai, nên chỉ chặn ở form là không đủ.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from app.adapters._common import CompanyHeader
from app.models import Company, CompanyPeriod
from app.pipeline.period import (
    MAX_PERIOD_MONTHS,
    QUARTER_START_MONTHS,
    duplicate_period_windows,
    fiscal_bounds,
    period_span_months,
    period_window_errors,
    resolve_period_bounds,
)

# --- Niên độ: nhận cả 12 tháng (owner chốt 06/08/2026) ------------------------


@pytest.mark.parametrize("month", range(1, 13))
def test_fiscal_bounds_accepts_every_month(month):
    pf, pt = fiscal_bounds(2025, month)
    assert pf == date(2025, month, 1)
    assert period_span_months(pf, pt) == 12


def test_fiscal_bounds_for_a_non_quarter_month():
    """Tháng 6 KHÔNG phải mốc luật cho phép, nhưng hệ vẫn tính được cửa sổ."""
    assert fiscal_bounds(2025, 6) == (date(2025, 6, 1), date(2026, 5, 31))


def test_fiscal_bounds_february_lands_on_the_last_day_of_january():
    assert fiscal_bounds(2024, 2) == (date(2024, 2, 1), date(2025, 1, 31))


def test_quarter_start_months_still_names_the_four_legal_marks():
    # Điểm a khoản 1 Điều 12 Luật Kế toán 88/2015 — dùng để CẢNH BÁO, không để chặn.
    assert QUARTER_START_MONTHS == (1, 4, 7, 10)


@pytest.mark.parametrize("month", [0, 13, -1])
def test_fiscal_bounds_rejects_a_month_outside_1_12(month):
    with pytest.raises(ValueError):
        fiscal_bounds(2025, month)


# --- Bất biến của cửa sổ ------------------------------------------------------


def test_window_matching_the_label_has_no_error():
    assert period_window_errors(2024, date(2024, 1, 1), date(2024, 12, 31)) == []


def test_fiscal_window_crossing_into_the_next_year_has_no_error():
    assert period_window_errors(2025, date(2025, 4, 1), date(2026, 3, 31)) == []


def test_window_with_no_overlap_at_all_is_rejected():
    """Đúng ca HIEP_QUANG: nhãn 2024, cửa sổ nằm trọn trong 2021."""
    errs = period_window_errors(2024, date(2021, 1, 1), date(2021, 12, 31))
    assert errs
    assert any("2024" in e and "2021" in e for e in errs)


def test_transitional_window_starting_the_previous_year_is_allowed():
    """DN đổi niên độ: kỳ nhãn 2025 bắt đầu 01/10/2024 — #49 đã chốt không chặn."""
    assert period_window_errors(2025, date(2024, 10, 1), date(2025, 12, 31)) == []


def test_window_starting_one_year_late_is_rejected():
    assert period_window_errors(2024, date(2025, 1, 1), date(2025, 12, 31)) != []


def test_reversed_window_is_rejected():
    assert period_window_errors(2024, date(2024, 12, 31), date(2024, 1, 1)) != []


def test_merged_first_period_up_to_15_months_is_allowed():
    """Khoản 4 Điều 12 (bản Luật 56/2024): kỳ đầu/cuối gộp được, tối đa 15 tháng."""
    assert period_span_months(date(2024, 10, 1), date(2025, 12, 31)) == 15
    assert period_window_errors(2024, date(2024, 10, 1), date(2025, 12, 31)) == []


def test_period_longer_than_15_months_is_rejected():
    assert period_span_months(date(2024, 1, 1), date(2025, 4, 30)) == 16
    errs = period_window_errors(2024, date(2024, 1, 1), date(2025, 4, 30))
    assert any(str(MAX_PERIOD_MONTHS) in e for e in errs)


# --- Trùng cửa sổ giữa hai kỳ của cùng DN ------------------------------------


def test_duplicate_window_of_another_period_is_reported(session, company: Company):
    session.add(CompanyPeriod(
        company_id=company.id, period_year=2021,
        period_from=date(2021, 1, 1), period_to=date(2021, 12, 31),
    ))
    session.commit()
    dups = duplicate_period_windows(
        session, company.id, 2024, date(2021, 1, 1), date(2021, 12, 31)
    )
    assert dups == [2021]


def test_a_period_does_not_duplicate_itself(session, company: Company):
    session.add(CompanyPeriod(
        company_id=company.id, period_year=2024,
        period_from=date(2024, 1, 1), period_to=date(2024, 12, 31),
    ))
    session.commit()
    assert duplicate_period_windows(
        session, company.id, 2024, date(2024, 1, 1), date(2024, 12, 31)
    ) == []


# --- Đường hệ suy từ header: cửa sổ hỏng thì rơi về niên độ DN ----------------


def test_resolve_falls_back_when_the_header_names_another_year(session, company: Company):
    """Header 2021 nạp dưới nhãn 2024 → KHÔNG nhận, quay về niên độ mặc định."""
    header = CompanyHeader(period_from=date(2021, 1, 1), period_to=date(2021, 12, 31))
    pf, pt = resolve_period_bounds(session, company.id, 2024, header=header)
    assert (pf, pt) == (date(2024, 1, 1), date(2024, 12, 31))
    row = session.scalar(
        select(CompanyPeriod).where(
            CompanyPeriod.company_id == company.id, CompanyPeriod.period_year == 2024
        )
    )
    assert (row.period_from, row.period_to) == (date(2024, 1, 1), date(2024, 12, 31))


def test_resolve_still_takes_a_header_that_matches_the_label(session, company: Company):
    header = CompanyHeader(period_from=date(2024, 4, 1), period_to=date(2025, 3, 31))
    assert resolve_period_bounds(session, company.id, 2024, header=header) == (
        date(2024, 4, 1), date(2025, 3, 31)
    )


def test_resolve_reports_the_rejected_header_window(session, company: Company):
    header = CompanyHeader(period_from=date(2021, 1, 1), period_to=date(2021, 12, 31))
    rejected: list[str] = []
    resolve_period_bounds(
        session, company.id, 2024, header=header, rejected=rejected
    )
    assert rejected and "2021" in rejected[0]


def test_resolve_never_overwrites_a_manual_window(session, company: Company):
    session.add(CompanyPeriod(
        company_id=company.id, period_year=2024,
        period_from=date(2024, 2, 1), period_to=date(2025, 1, 31), is_manual=True,
    ))
    session.commit()
    header = CompanyHeader(period_from=date(2021, 1, 1), period_to=date(2021, 12, 31))
    assert resolve_period_bounds(session, company.id, 2024, header=header) == (
        date(2024, 2, 1), date(2025, 1, 31)
    )
