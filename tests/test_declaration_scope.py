"""BCCT-1 (#47, ADR #23 T1) — tư cách thuộc kỳ của dòng BCCT tính lúc QUERY.

`declaration_lines.period_year` là nhãn nạp; dòng CÓ ngày thuộc kỳ theo cửa sổ
`company_periods`, dòng KHÔNG ngày quy theo nhãn.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from sqlalchemy import func, select

from app.checks.c1_quantity import check_c1_1, check_c1_2
from app.checks.company_type import detect_company_type
from app.checks.denominators import compute_denominators
from app.checks.scope import declaration_scope, period_window
from app.models import DeclarationLine
from tests.conftest import add_decl, add_nvl


def set_period(session, company_id: int, year: int, period_from: date, period_to: date) -> None:
    from app.models import CompanyPeriod

    session.add(
        CompanyPeriod(
            company_id=company_id,
            period_year=year,
            period_from=period_from,
            period_to=period_to,
            is_manual=True,
        )
    )
    session.commit()


def count_in_scope(session, company_id: int, year: int) -> int:
    return session.scalar(
        select(func.count()).select_from(DeclarationLine).where(
            declaration_scope(session, company_id, year)
        )
    )


# --- Cửa sổ kỳ ---------------------------------------------------------------


def test_period_window_none_when_no_row(session, company):
    assert period_window(session, company.id, 2025) is None


def test_period_window_reads_company_periods(session, company):
    set_period(session, company.id, 2025, date(2025, 4, 1), date(2026, 3, 31))
    assert period_window(session, company.id, 2025) == (date(2025, 4, 1), date(2026, 3, 31))


# --- Ba nhánh của selector ---------------------------------------------------


def test_dated_row_with_other_label_inside_window_is_in_scope(session, company):
    set_period(session, company.id, 2025, date(2025, 4, 1), date(2026, 3, 31))
    add_decl(
        session, company.id, declaration_no="1", customs_code="E31", item_code="A",
        quantity=10, year=2026, declaration_date=date(2026, 2, 1),
    )
    session.commit()
    assert count_in_scope(session, company.id, 2025) == 1


def test_dated_row_with_matching_label_outside_window_is_out_of_scope(session, company):
    set_period(session, company.id, 2025, date(2025, 4, 1), date(2026, 3, 31))
    add_decl(
        session, company.id, declaration_no="1", customs_code="E31", item_code="A",
        quantity=10, year=2025, declaration_date=date(2025, 1, 15),
    )
    session.commit()
    assert count_in_scope(session, company.id, 2025) == 0


def test_undated_row_falls_back_to_label(session, company):
    set_period(session, company.id, 2025, date(2025, 4, 1), date(2026, 3, 31))
    row_in = add_decl(
        session, company.id, declaration_no="1", customs_code="E31", item_code="A", quantity=10,
        year=2025,
    )
    row_in.declaration_date = None
    row_out = add_decl(
        session, company.id, declaration_no="2", customs_code="E31", item_code="B", quantity=10,
        year=2024,
    )
    row_out.declaration_date = None
    session.commit()
    assert count_in_scope(session, company.id, 2025) == 1


def test_no_period_row_falls_back_to_label_for_dated_rows(session, company):
    add_decl(
        session, company.id, declaration_no="1", customs_code="E31", item_code="A",
        quantity=10, year=2025, declaration_date=date(2025, 6, 1),
    )
    add_decl(
        session, company.id, declaration_no="2", customs_code="E31", item_code="B",
        quantity=10, year=2024, declaration_date=date(2024, 6, 1),
    )
    session.commit()
    assert count_in_scope(session, company.id, 2025) == 1


def test_scope_never_leaks_across_companies(session, company):
    from app.models import Company

    other = Company(code="OTHER_DN", tax_id="8888888888", name="DN khác", address="Hà Nội")
    session.add(other)
    session.commit()
    set_period(session, company.id, 2025, date(2025, 1, 1), date(2025, 12, 31))
    set_period(session, other.id, 2025, date(2025, 1, 1), date(2025, 12, 31))
    add_decl(
        session, other.id, declaration_no="1", customs_code="E31", item_code="A",
        quantity=10, year=2025, declaration_date=date(2025, 6, 1),
    )
    session.commit()
    assert count_in_scope(session, company.id, 2025) == 0
    assert count_in_scope(session, other.id, 2025) == 1


# --- Check thật đọc theo cửa sổ ----------------------------------------------


def test_c1_1_reads_declaration_rows_by_window_not_label(session, company):
    """Niên độ 04/2025–03/2026: tờ khai 01/2026 nằm ở file nhãn 2026 vẫn thuộc kỳ 2025."""
    set_period(session, company.id, 2025, date(2025, 4, 1), date(2026, 3, 31))
    add_nvl(session, company.id, material_code="A", imported=1000, year=2025)
    add_decl(
        session, company.id, declaration_no="1", customs_code="E31", item_code="A",
        quantity=600, year=2025, declaration_date=date(2025, 9, 1),
    )
    add_decl(
        session, company.id, declaration_no="2", customs_code="E31", item_code="A",
        quantity=400, year=2026, declaration_date=date(2026, 1, 20),
    )
    session.commit()
    assert check_c1_1(session, company.id, 2025) == []


def test_c1_2_ignores_declaration_rows_dated_outside_window(session, company):
    set_period(session, company.id, 2025, date(2025, 4, 1), date(2026, 3, 31))
    add_nvl(session, company.id, material_code="A", imported=1000, year=2025)
    add_decl(
        session, company.id, declaration_no="1", customs_code="E31", item_code="A",
        quantity=1000, year=2025, declaration_date=date(2025, 9, 1),
    )
    # Mã B chỉ xuất hiện ở dòng ngoài cửa sổ → không được báo "có tờ khai, thiếu M15".
    add_decl(
        session, company.id, declaration_no="2", customs_code="E31", item_code="B",
        quantity=50, year=2025, declaration_date=date(2025, 2, 1),
    )
    session.commit()
    assert check_c1_2(session, company.id, 2025) == []


def test_detect_company_type_reads_by_window(session, company):
    from app.checks.company_type import CompanyType

    set_period(session, company.id, 2025, date(2025, 4, 1), date(2026, 3, 31))
    add_decl(
        session, company.id, declaration_no="1", customs_code="E11", item_code="A",
        quantity=10, year=2026, declaration_date=date(2026, 2, 1),
    )
    session.commit()
    assert detect_company_type(session, company.id, 2025) == CompanyType.DNCX


def test_denominator_counts_declaration_rows_in_window(session, company):
    set_period(session, company.id, 2025, date(2025, 4, 1), date(2026, 3, 31))
    add_decl(
        session, company.id, declaration_no="1", customs_code="E31", item_code="A",
        quantity=10, year=2026, declaration_date=date(2026, 2, 1),
    )
    add_decl(
        session, company.id, declaration_no="2", customs_code="E31", item_code="B",
        quantity=10, year=2025, declaration_date=date(2025, 1, 5),
    )
    session.commit()
    assert compute_denominators(session, company.id, 2025)["nvl"] == 1


# --- Cổng: không còn filter nhãn rải rác ------------------------------------


def test_no_direct_period_year_filter_on_declaration_line_outside_helper():
    """Mọi vế BCCT phải đi qua `declaration_scope` — không check nào tự lọc nhãn."""
    checks_dir = Path(__file__).resolve().parent.parent / "app" / "checks"
    pattern = re.compile(r"DeclarationLine\.period_year")
    offenders = [
        path.name
        for path in sorted(checks_dir.glob("*.py"))
        if path.name != "scope.py" and pattern.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []
