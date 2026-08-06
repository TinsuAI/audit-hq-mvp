"""Banner độ phủ BCCT trên trang tài liệu (#48 ba số · #49 khoảng thiếu + chồng lấn)."""

from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import Company, CompanyPeriod, DeclarationLine
from tests.test_company_period_route import _login, _setup_db, _teardown


def _add_decl(db, company_id: int, *, year: int, no: str, day: date | None,
              line_no: int | None = 1, item_code: str = "A") -> None:
    db.add(DeclarationLine(
        company_id=company_id, period_year=year, declaration_no=no,
        declaration_date=day, customs_code="E31", line_no=line_no,
        item_code=item_code, quantity=1.0, unit="PCE",
    ))


def _seed(db, *, window: tuple[date, date], rows: list[tuple[int, str, date | None]],
          extra_periods: list[tuple[int, date, date]] = ()) -> Company:
    c = db.scalar(select(Company).where(Company.code == "DN_077"))
    db.add(CompanyPeriod(
        company_id=c.id, period_year=2025,
        period_from=window[0], period_to=window[1], is_manual=True,
    ))
    for year, pf, pt in extra_periods:
        db.add(CompanyPeriod(
            company_id=c.id, period_year=year, period_from=pf, period_to=pt, is_manual=True,
        ))
    for i, (year, no, day) in enumerate(rows):
        _add_decl(db, c.id, year=year, no=no, day=day, item_code=f"A{i}")
    db.commit()
    return c


def test_clean_period_shows_no_coverage_banner():
    new_engine, new_session = _setup_db()
    try:
        with new_session() as db:
            _seed(
                db,
                window=(date(2025, 1, 1), date(2025, 12, 31)),
                rows=[(2025, "9001", date(2025, 3, 1)), (2025, "9002", date(2025, 11, 1))],
            )
        client = TestClient(app)
        _login(client)
        r = client.get("/companies/DN_077/documents")
        assert r.status_code == 200
        assert "Dòng tờ khai lệch cửa sổ kỳ" not in r.text
    finally:
        _teardown(new_engine)


def test_banner_reports_out_of_window_and_undated_rows():
    new_engine, new_session = _setup_db()
    try:
        with new_session() as db:
            _seed(
                db,
                window=(date(2025, 4, 1), date(2026, 3, 31)),
                rows=[
                    (2025, "9001", date(2025, 6, 1)),    # trong kỳ
                    (2025, "9002", date(2025, 1, 5)),    # ngoài cửa sổ
                    (2025, "9003", None),                # không ngày
                ],
            )
        client = TestClient(app)
        _login(client)
        r = client.get("/companies/DN_077/documents")
        assert r.status_code == 200
        assert "Dòng tờ khai lệch cửa sổ kỳ" in r.text
        assert "ngày tờ khai nằm ngoài kỳ" in r.text
        assert "không có ngày tờ khai" in r.text
    finally:
        _teardown(new_engine)


def test_banner_reports_cross_label_duplicates():
    new_engine, new_session = _setup_db()
    try:
        with new_session() as db:
            c = db.scalar(select(Company).where(Company.code == "DN_077"))
            db.add(CompanyPeriod(
                company_id=c.id, period_year=2025,
                period_from=date(2025, 1, 1), period_to=date(2025, 12, 31), is_manual=True,
            ))
            _add_decl(db, c.id, year=2025, no="9001", day=date(2025, 6, 1))
            _add_decl(db, c.id, year=2024, no="9001", day=date(2025, 6, 1))
            db.commit()
        client = TestClient(app)
        _login(client)
        r = client.get("/companies/DN_077/documents")
        assert r.status_code == 200
        assert "trùng khoá" in r.text
    finally:
        _teardown(new_engine)


def test_documents_page_survives_a_year_with_findings_but_no_score_row():
    """Hồi quy: `checks_run` bật theo phát hiện, nhưng điểm năm có thể chưa có dòng —
    render nhãn rủi ro với `score=None` làm `tier_css_for` nổ, 500 cả trang."""
    new_engine, new_session = _setup_db()
    try:
        from app.models import Finding

        with new_session() as db:
            c = db.scalar(select(Company).where(Company.code == "DN_077"))
            db.add(Finding(
                company_id=c.id, period_year=2025, check_code="C1.2", severity="critical",
                subject_type="material_code", subject_key="A", title="x",
            ))
            db.commit()
        client = TestClient(app)
        _login(client)
        r = client.get("/companies/DN_077/documents")
        assert r.status_code == 200
        assert "/1000" not in r.text
    finally:
        _teardown(new_engine)
