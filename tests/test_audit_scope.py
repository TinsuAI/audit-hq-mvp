"""KTSTQ-2 (#54, ADR #23 T4) — phạm vi kiểm tra 5 năm là VIEW, không phải khoá dữ liệu.

`companies.audit_decision_date` nullable; cửa sổ `[D − 5 năm, D]` TÍNH lúc render,
không lưu; neo trên `declaration_date` (= "Ngày ĐK", khoản 3 Điều 77 Luật HQ
54/2014). NULL → mọi màn như cũ. Đổi ngày = re-render, không đụng dữ liệu.
"""

from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import Company, CompanyPeriod, DeclarationLine
from app.pipeline.audit_scope import (
    audit_window,
    classify_period,
    finding_scope_tag,
    scope_coverage,
)
from tests.conftest import add_nvl
from tests.test_company_period_route import _login, _period, _setup_db, _teardown


def _decl(session, company_id: int, *, year: int, day: date, no: str, item: str = "A") -> None:
    session.add(DeclarationLine(
        company_id=company_id, period_year=year, declaration_no=no,
        declaration_date=day, customs_code="E31", line_no=1,
        item_code=item, quantity=1.0, unit="PCE",
    ))


# --- Cửa sổ 5 năm -------------------------------------------------------------


def test_window_is_five_years_back_from_the_decision_date():
    assert audit_window(date(2026, 8, 1)) == (date(2021, 8, 1), date(2026, 8, 1))


def test_window_handles_leap_day_decision_dates():
    assert audit_window(date(2028, 2, 29)) == (date(2023, 2, 28), date(2028, 2, 29))


# --- Phân loại từng kỳ --------------------------------------------------------


def test_period_fully_inside_the_window():
    window = (date(2021, 8, 1), date(2026, 8, 1))
    assert classify_period(window, date(2023, 1, 1), date(2023, 12, 31)) == "inside"


def test_period_cut_at_its_start():
    window = (date(2021, 8, 1), date(2026, 8, 1))
    assert classify_period(window, date(2021, 1, 1), date(2021, 12, 31)) == "cut_start"


def test_period_cut_at_its_end():
    window = (date(2021, 8, 1), date(2026, 8, 1))
    assert classify_period(window, date(2026, 4, 1), date(2027, 3, 31)) == "cut_end"


def test_period_entirely_outside_the_window():
    window = (date(2021, 8, 1), date(2026, 8, 1))
    assert classify_period(window, date(2019, 1, 1), date(2019, 12, 31)) == "outside"
    assert classify_period(window, date(2027, 1, 1), date(2027, 12, 31)) == "outside"


def test_period_wider_than_the_window_at_both_ends():
    window = (date(2021, 8, 1), date(2026, 8, 1))
    assert classify_period(window, date(2020, 1, 1), date(2027, 12, 31)) == "cut_both"


# --- Màn độ phủ ---------------------------------------------------------------


def test_no_coverage_when_no_decision_date(session, company):
    assert scope_coverage(session, company) is None


def test_coverage_lists_every_fiscal_period_touching_the_window(session, company):
    company.fiscal_start_month = 4
    company.audit_decision_date = date(2026, 8, 1)
    session.commit()
    rows = scope_coverage(session, company)
    # Niên độ tháng 4: nhãn 2021 (01/04/2021–31/03/2022) … nhãn 2026 (01/04/2026–31/03/2027).
    assert [r.period_year for r in rows] == [2021, 2022, 2023, 2024, 2025, 2026]
    assert rows[0].status == "cut_start"     # kỳ 2021 bắt đầu trước 01/08/2021
    assert rows[1].status == "inside"
    assert rows[-1].status == "cut_end"      # kỳ đuôi kéo quá 01/08/2026


def test_coverage_uses_the_stored_window_when_the_period_has_one(session, company):
    company.audit_decision_date = date(2026, 8, 1)
    session.add(CompanyPeriod(
        company_id=company.id, period_year=2024,
        period_from=date(2024, 7, 1), period_to=date(2025, 6, 30), is_manual=True,
    ))
    session.commit()
    rows = {r.period_year: r for r in scope_coverage(session, company)}
    assert (rows[2024].period_from, rows[2024].period_to) == (date(2024, 7, 1), date(2025, 6, 30))


def test_tail_period_without_bcqt_is_flagged_and_counts_waiting_checks(session, company):
    from datetime import datetime

    from app.models import CheckRun

    company.audit_decision_date = date(2026, 8, 1)
    add_nvl(session, company.id, material_code="A", imported=1, year=2025)
    _decl(session, company.id, year=2026, day=date(2026, 5, 1), no="9001")
    session.add_all([
        CheckRun(company_id=company.id, period_year=2026, check_code="C3.1",
                 ran_at=datetime(2026, 8, 1), finding_count=0, status="ok", data_version=0),
        CheckRun(company_id=company.id, period_year=2026, check_code="C2.1",
                 ran_at=datetime(2026, 8, 1), finding_count=0, status="not_evaluable",
                 data_version=0, status_reason="Kỳ này chưa có Mẫu 15 — Cân đối NVL"),
    ])
    session.commit()
    rows = {r.period_year: r for r in scope_coverage(session, company)}
    assert rows[2026].has_bcqt is False
    assert rows[2026].checks_run == 1
    assert rows[2026].checks_waiting == 1
    assert rows[2025].has_bcqt is True


# --- Tag lúc render trên phát hiện --------------------------------------------


def test_finding_with_dates_inside_the_window_has_no_tag():
    window = (date(2021, 8, 1), date(2026, 8, 1))
    assert finding_scope_tag(window, (date(2023, 1, 1), date(2023, 6, 1)), "inside") is None


def test_finding_dated_entirely_before_the_window_is_out_of_scope():
    window = (date(2021, 8, 1), date(2026, 8, 1))
    tag = finding_scope_tag(window, (date(2020, 1, 1), date(2020, 6, 1)), "cut_start")
    assert tag == "outside"


def test_finding_straddling_the_window_boundary_is_partial():
    window = (date(2021, 8, 1), date(2026, 8, 1))
    tag = finding_scope_tag(window, (date(2021, 1, 1), date(2021, 12, 1)), "cut_start")
    assert tag == "partial"


def test_undated_finding_in_a_cut_period_reports_the_wider_settlement_period():
    window = (date(2021, 8, 1), date(2026, 8, 1))
    assert finding_scope_tag(window, None, "cut_start") == "period_wider"
    assert finding_scope_tag(window, None, "cut_end") == "period_wider"


def test_undated_finding_in_a_fully_covered_period_has_no_tag():
    window = (date(2021, 8, 1), date(2026, 8, 1))
    assert finding_scope_tag(window, None, "inside") is None


# --- Routes -------------------------------------------------------------------


def test_null_decision_date_leaves_screens_unchanged():
    new_engine, _ = _setup_db()
    try:
        client = TestClient(app)
        _login(client)
        r = client.get("/companies/DN_077?year=2025")
        assert r.status_code == 200
        assert "Phạm vi kiểm tra sau thông quan" not in r.text
        assert client.get("/companies/DN_077/scope").status_code == 404
    finally:
        _teardown(new_engine)


def test_saving_the_decision_date_persists_and_does_not_touch_data_version():
    new_engine, new_session = _setup_db()
    try:
        with new_session() as db:
            c = db.scalar(select(Company).where(Company.code == "DN_077"))
            db.add(CompanyPeriod(
                company_id=c.id, period_year=2025,
                period_from=date(2025, 1, 1), period_to=date(2025, 12, 31), data_version=7,
            ))
            db.commit()
        client = TestClient(app)
        _login(client)
        r = client.post(
            "/companies/DN_077/edit",
            data={"name": "Cơ khí Test", "tax_id": "111", "address": "", "industry": "",
                  "fiscal_start_month": "1", "audit_decision_date": "2026-08-01"},
            follow_redirects=False,
        )
        assert r.status_code == 303
        with new_session() as db:
            c = db.scalar(select(Company).where(Company.code == "DN_077"))
            assert c.audit_decision_date == date(2026, 8, 1)
        assert _period(new_session, "DN_077").data_version == 7   # không đụng dữ liệu
    finally:
        _teardown(new_engine)


def test_clearing_the_decision_date_is_allowed():
    new_engine, new_session = _setup_db()
    try:
        client = TestClient(app)
        _login(client)
        client.post(
            "/companies/DN_077/edit",
            data={"name": "x", "tax_id": "", "address": "", "industry": "",
                  "fiscal_start_month": "1", "audit_decision_date": "2026-08-01"},
            follow_redirects=False,
        )
        client.post(
            "/companies/DN_077/edit",
            data={"name": "x", "tax_id": "", "address": "", "industry": "",
                  "fiscal_start_month": "1", "audit_decision_date": ""},
            follow_redirects=False,
        )
        with new_session() as db:
            c = db.scalar(select(Company).where(Company.code == "DN_077"))
            assert c.audit_decision_date is None
    finally:
        _teardown(new_engine)


def test_scope_screen_states_both_the_date_range_and_the_period_list():
    new_engine, new_session = _setup_db()
    try:
        with new_session() as db:
            c = db.scalar(select(Company).where(Company.code == "DN_077"))
            c.fiscal_start_month = 4
            c.audit_decision_date = date(2026, 8, 1)
            add_nvl(db, c.id, material_code="A", imported=1, year=2024)
            db.commit()
        client = TestClient(app)
        _login(client)
        r = client.get("/companies/DN_077/scope")
        assert r.status_code == 200
        assert "01/08/2021 – 01/08/2026" in r.text          # ngôn ngữ khoảng ngày
        assert "01/04/2024 – 31/03/2025" in r.text          # ngôn ngữ kỳ quyết toán
        assert "Cắt đầu" in r.text
        assert "chưa có BCQT" in r.text
    finally:
        _teardown(new_engine)


def test_company_detail_tags_findings_outside_the_audit_window():
    new_engine, new_session = _setup_db()
    try:
        from app.models import Finding

        with new_session() as db:
            c = db.scalar(select(Company).where(Company.code == "DN_077"))
            c.audit_decision_date = date(2026, 8, 1)
            db.add(CompanyPeriod(
                company_id=c.id, period_year=2021,
                period_from=date(2021, 1, 1), period_to=date(2021, 12, 31),
            ))
            _decl(db, c.id, year=2021, day=date(2021, 2, 1), no="9001", item="OLD")
            db.add(Finding(
                company_id=c.id, period_year=2021, check_code="C1.2", severity="critical",
                subject_type="material_code", subject_key="OLD", title="Mã OLD thiếu M15",
            ))
            db.commit()
        client = TestClient(app)
        _login(client)
        r = client.get("/companies/DN_077?year=2021")
        assert r.status_code == 200
        assert "hết thời hiệu" in r.text
    finally:
        _teardown(new_engine)
