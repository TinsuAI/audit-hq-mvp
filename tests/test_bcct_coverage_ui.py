"""Độ phủ BCCT trên màn dữ liệu (#48 ba số · #49 khoảng thiếu + chồng lấn).

Từ #86 ba khối cảnh báo cũ không còn là khối riêng: chúng là mục trong danh sách
vướng mắc của dòng kỳ. Bất biến giữ nguyên — cán bộ vẫn phải thấy dòng lệch cửa sổ,
dòng không ngày và dòng trùng khoá chéo nhãn — chỉ đổi chỗ hiện.

Test ở mức DỮ LIỆU: khẳng định trên ngữ cảnh màn hình, không dò chuỗi tiếng Việt
trong HTML. Số liệu của từng cảnh báo là việc của `tests/test_bcct_coverage.py`.
"""

from __future__ import annotations

from datetime import date

from app.models import CompanyPeriod, DeclarationLine
from app.pipeline.data_screen import build_data_screen
from app.pipeline.readiness import BLOCKER_COVERAGE


def _add_decl(session, company_id: int, *, year: int, no: str, day: date | None,
              item_code: str = "A") -> None:
    session.add(DeclarationLine(
        company_id=company_id, period_year=year, declaration_no=no,
        declaration_date=day, customs_code="E31", line_no=1,
        item_code=item_code, quantity=1.0, unit="PCE",
    ))


def _coverage_keys(session, company, year: int = 2025) -> set[str]:
    row = next(
        p for p in build_data_screen(session, company).periods if p.year == year
    )
    return {
        item.key
        for group in row.groups
        for item in group.items
        if item.kind == BLOCKER_COVERAGE
    }


def _seed(session, company, *, window: tuple[date, date],
          rows: list[tuple[int, str, date | None]]) -> None:
    session.add(CompanyPeriod(
        company_id=company.id, period_year=2025,
        period_from=window[0], period_to=window[1], is_manual=True,
    ))
    for i, (year, no, day) in enumerate(rows):
        _add_decl(session, company.id, year=year, no=no, day=day, item_code=f"A{i}")
    session.commit()


def test_a_clean_period_raises_none_of_the_three_warnings(session, company):
    _seed(
        session, company,
        window=(date(2025, 1, 1), date(2025, 12, 31)),
        rows=[(2025, "9001", date(2025, 3, 1)), (2025, "9002", date(2025, 11, 1))],
    )

    keys = _coverage_keys(session, company)
    assert "coverage:out-of-window" not in keys
    assert "coverage:undated" not in keys
    assert "coverage:cross-label-duplicates" not in keys


def test_out_of_window_and_undated_rows_become_blocker_items(session, company):
    _seed(
        session, company,
        window=(date(2025, 4, 1), date(2026, 3, 31)),
        rows=[
            (2025, "9001", date(2025, 6, 1)),   # trong kỳ
            (2025, "9002", date(2025, 1, 5)),   # ngoài cửa sổ
            (2025, "9003", None),               # không ngày
        ],
    )

    keys = _coverage_keys(session, company)
    assert "coverage:out-of-window" in keys
    assert "coverage:undated" in keys


def test_cross_label_duplicates_become_a_blocker_item(session, company):
    session.add(CompanyPeriod(
        company_id=company.id, period_year=2025,
        period_from=date(2025, 1, 1), period_to=date(2025, 12, 31), is_manual=True,
    ))
    _add_decl(session, company.id, year=2025, no="9001", day=date(2025, 6, 1))
    _add_decl(session, company.id, year=2024, no="9001", day=date(2025, 6, 1))
    session.commit()

    assert "coverage:cross-label-duplicates" in _coverage_keys(session, company)
