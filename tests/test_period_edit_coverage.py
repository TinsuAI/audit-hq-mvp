"""BCCT-3 (#49, ADR #23 T1) — sửa cửa sổ kỳ đổi kết quả check mà KHÔNG qua ingest.

- Sửa kỳ bump `company_periods.data_version` trong CÙNG transaction (ca WS3 sinh ra
  để bắt: dữ liệu check đọc đổi mà `ran_at` không dời).
- Cửa sổ chồng lấn kỳ liền kề → CẢNH BÁO, không chặn (kỳ chuyển tiếp đổi niên độ
  là hợp pháp — khoản 4 Điều 2 Luật 56/2024).
- Banner độ phủ nêu ĐÚNG khoảng tháng thiếu.
"""

from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import Company, CompanyPeriod, DeclarationLine
from app.pipeline.coverage import coverage_gaps, overlapping_periods
from tests.test_company_period_route import _login, _period, _setup_db, _teardown


def _decl(db, company_id: int, *, year: int, day: date, no: str = "9001") -> None:
    db.add(DeclarationLine(
        company_id=company_id, period_year=year, declaration_no=no,
        declaration_date=day, customs_code="E31", line_no=1,
        item_code="A", quantity=1.0, unit="PCE",
    ))


# --- data_version bump --------------------------------------------------------


def test_saving_period_bumps_data_version():
    new_engine, new_session = _setup_db()
    try:
        client = TestClient(app)
        _login(client)
        client.post(
            "/companies/DN_077/documents/period",
            data={"year": 2025, "period_from": "2025-01-01", "period_to": "2025-12-31"},
            follow_redirects=False,
        )
        first = _period(new_session, "DN_077").data_version
        client.post(
            "/companies/DN_077/documents/period",
            data={"year": 2025, "period_from": "2025-04-01", "period_to": "2026-03-31"},
            follow_redirects=False,
        )
        assert _period(new_session, "DN_077").data_version == first + 1
    finally:
        _teardown(new_engine)


def test_reset_to_default_also_bumps_data_version():
    new_engine, new_session = _setup_db()
    try:
        client = TestClient(app)
        _login(client)
        client.post(
            "/companies/DN_077/documents/period",
            data={"year": 2025, "period_from": "2025-04-01", "period_to": "2026-03-31"},
            follow_redirects=False,
        )
        before = _period(new_session, "DN_077").data_version
        client.post(
            "/companies/DN_077/documents/period",
            data={"year": 2025, "reset": "1"},
            follow_redirects=False,
        )
        assert _period(new_session, "DN_077").data_version == before + 1
    finally:
        _teardown(new_engine)


def test_flash_message_no_longer_asks_for_reingest():
    new_engine, _ = _setup_db()
    try:
        client = TestClient(app)
        _login(client)
        r = client.post(
            "/companies/DN_077/documents/period",
            data={"year": 2025, "period_from": "2025-04-01", "period_to": "2026-03-31"},
            follow_redirects=False,
        )
        from urllib.parse import parse_qs, unquote, urlparse

        msg = parse_qs(urlparse(unquote(r.headers["location"])).query)["msg"][0]
        assert "Nạp dữ liệu" not in msg
        assert "Chạy kiểm tra" in msg
    finally:
        _teardown(new_engine)


# --- Chồng lấn kỳ liền kề -----------------------------------------------------


def test_overlapping_window_warns_but_still_saves():
    new_engine, new_session = _setup_db()
    try:
        with new_session() as db:
            c = db.scalar(select(Company).where(Company.code == "DN_077"))
            db.add(CompanyPeriod(
                company_id=c.id, period_year=2024,
                period_from=date(2024, 1, 1), period_to=date(2024, 12, 31), is_manual=True,
            ))
            db.commit()
        client = TestClient(app)
        _login(client)
        r = client.post(
            "/companies/DN_077/documents/period",
            data={"year": 2025, "period_from": "2024-10-01", "period_to": "2025-12-31"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert "error" not in r.headers["location"]     # cảnh báo, KHÔNG chặn
        cp = _period(new_session, "DN_077", 2025)
        assert cp is not None and cp.period_from == date(2024, 10, 1)   # đã lưu
    finally:
        _teardown(new_engine)


def test_overlapping_periods_lists_the_neighbour(session, company):
    session.add_all([
        CompanyPeriod(company_id=company.id, period_year=2024,
                      period_from=date(2024, 1, 1), period_to=date(2024, 12, 31)),
        CompanyPeriod(company_id=company.id, period_year=2025,
                      period_from=date(2024, 10, 1), period_to=date(2025, 12, 31)),
        CompanyPeriod(company_id=company.id, period_year=2026,
                      period_from=date(2026, 1, 1), period_to=date(2026, 12, 31)),
    ])
    session.commit()
    assert overlapping_periods(session, company.id, 2025) == [2024]
    assert overlapping_periods(session, company.id, 2026) == []


def test_documents_page_shows_overlap_warning():
    new_engine, new_session = _setup_db()
    try:
        with new_session() as db:
            c = db.scalar(select(Company).where(Company.code == "DN_077"))
            db.add_all([
                CompanyPeriod(company_id=c.id, period_year=2024,
                              period_from=date(2024, 1, 1), period_to=date(2024, 12, 31)),
                CompanyPeriod(company_id=c.id, period_year=2025,
                              period_from=date(2024, 10, 1), period_to=date(2025, 12, 31)),
            ])
            db.commit()
        client = TestClient(app)
        _login(client)
        r = client.get("/companies/DN_077/documents")
        assert r.status_code == 200
        assert "chồng lấn" in r.text
    finally:
        _teardown(new_engine)


# --- Khoảng thiếu -------------------------------------------------------------


def test_no_gap_when_every_month_has_rows(session, company):
    session.add(CompanyPeriod(
        company_id=company.id, period_year=2025,
        period_from=date(2025, 1, 1), period_to=date(2025, 3, 31),
    ))
    for m in (1, 2, 3):
        _decl(session, company.id, year=2025, day=date(2025, m, 10), no=f"900{m}")
    session.commit()
    assert coverage_gaps(session, company.id, 2025) == []


def test_gap_names_the_missing_month_range(session, company):
    """Niên độ 04/2025–03/2026, chỉ nạp file dương lịch 2025 → thiếu quý 01–03/2026."""
    session.add(CompanyPeriod(
        company_id=company.id, period_year=2025,
        period_from=date(2025, 4, 1), period_to=date(2026, 3, 31),
    ))
    for m in range(4, 13):
        _decl(session, company.id, year=2025, day=date(2025, m, 10), no=f"90{m:02d}")
    session.commit()
    assert coverage_gaps(session, company.id, 2025) == [(date(2026, 1, 1), date(2026, 3, 31))]


def test_gap_at_the_start_of_the_window(session, company):
    session.add(CompanyPeriod(
        company_id=company.id, period_year=2025,
        period_from=date(2025, 1, 1), period_to=date(2025, 6, 30),
    ))
    for m in (4, 5, 6):
        _decl(session, company.id, year=2025, day=date(2025, m, 10), no=f"90{m:02d}")
    session.commit()
    assert coverage_gaps(session, company.id, 2025) == [(date(2025, 1, 1), date(2025, 3, 31))]


def test_gap_in_the_middle_is_reported_as_its_own_range(session, company):
    session.add(CompanyPeriod(
        company_id=company.id, period_year=2025,
        period_from=date(2025, 1, 1), period_to=date(2025, 5, 31),
    ))
    for m in (1, 2, 5):
        _decl(session, company.id, year=2025, day=date(2025, m, 10), no=f"90{m:02d}")
    session.commit()
    assert coverage_gaps(session, company.id, 2025) == [(date(2025, 3, 1), date(2025, 4, 30))]


def test_no_gap_reported_when_period_has_no_declaration_rows_at_all(session, company):
    """Chưa nạp gì thì không phải "thiếu khoảng" — trạng thái đó đã có nhãn riêng."""
    session.add(CompanyPeriod(
        company_id=company.id, period_year=2025,
        period_from=date(2025, 1, 1), period_to=date(2025, 12, 31),
    ))
    session.commit()
    assert coverage_gaps(session, company.id, 2025) == []


def test_documents_page_names_the_missing_range():
    new_engine, new_session = _setup_db()
    try:
        with new_session() as db:
            c = db.scalar(select(Company).where(Company.code == "DN_077"))
            db.add(CompanyPeriod(
                company_id=c.id, period_year=2025,
                period_from=date(2025, 4, 1), period_to=date(2026, 3, 31), is_manual=True,
            ))
            for m in range(4, 13):
                _decl(db, c.id, year=2025, day=date(2025, m, 10), no=f"90{m:02d}")
            db.commit()
        client = TestClient(app)
        _login(client)
        r = client.get("/companies/DN_077/documents")
        assert r.status_code == 200
        assert "01/01/2026 – 31/03/2026" in r.text
    finally:
        _teardown(new_engine)
