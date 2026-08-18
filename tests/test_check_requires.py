"""KTSTQ-1 (#53, ADR #23 T4) — hết "0 phát hiện = sạch giả".

Mỗi spec khai `requires` ⊆ {bcct, m15, m15a, m16} = nguồn dữ liệu check THỰC đọc.
`run_checks` kiểm presence per (DN, năm) TRƯỚC khi dispatch: thiếu nguồn → ghi
`check_runs.status_reason` với `status = not_evaluable` — cùng đường với
`NotEvaluable` các check tự trả (#58) — không chạy join rỗng, không tính là sạch.
"""

from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.checks import ALL_CHECKS
from app.checks.registry import SOURCES, SPECS, missing_sources
from app.checks.sources import available_sources
from app.main import app
from app.models import CheckRun, Company
from tests.conftest import add_decl, add_nvl, add_sp
from tests.test_company_period_route import _login, _setup_db, _teardown

# Đầu câu lý do do cổng NGUỒN sinh ra — phân biệt với lý do cổng khác
# (độ phủ định mức #62) vì cả hai cùng ghi vào `status_reason`.
MISSING_PREFIX = "Kỳ này chưa có"

# --- Fact audit: mọi check built-in đều khai nguồn --------------------------------------


def test_every_builtin_check_declares_requires():
    for code in ALL_CHECKS:
        assert code in SPECS, f"{code} thiếu spec"
        assert SPECS[code].requires, f"{code} chưa khai requires"
        assert set(SPECS[code].requires) <= set(SOURCES), f"{code} khai nguồn lạ"


def test_requires_matches_the_source_audit():
    """Bảng đối chiếu nguồn-thực-đọc (đọc từ code từng check, không đoán)."""
    expected = {
        "C1.1": {"bcct", "m15"},        # Σ tờ khai nhập vs M15.import
        "C1.2": {"bcct", "m15"},        # mã trên tờ khai, không có trong M15
        "C1.3": {"bcct", "m15"},        # M15.import > 0, không có tờ khai
        "C1.4": {"bcct", "m15a"},       # Σ tờ khai xuất vs M15a.export
        "C1.6": {"bcct", "m15"},        # M15.repurpose > 0, không có tờ khai A42
        "C1.7": {"m15"},                # tỉ lệ repurpose/(opening+import), thuần M15
        "C2.1": {"m15"},
        "C2.2": {"m15a"},
        "C2.3": {"m15"},
        "C2.4": {"m15a"},
        "C3.1": {"bcct"},               # mã loại hình trên tờ khai, thuần BCCT
        "C3.2": {"bcct"},               # mã HS trên tờ khai, thuần BCCT
        # Đơn vị M15 vs đơn vị M16 và tờ khai. Vế đối chiếu là HOẶC (tờ khai HOẶC
        # M16) mà `requires` chỉ khai được quan hệ VÀ → chỉ gác M15, thiếu cả hai vế
        # thì chính check trả `NotEvaluable`.
        "C3.3": {"m15"},
        "C4.1": {"m15", "m16"},
        "C4.3": {"m15", "m15a", "m16"},
        "C4.9": {"m15a", "m16"},        # M15a sản lượng → M16 định mức, không đọc M15
        "C5.1": {"m15"},
        "C6.1": {"m15"},                # kỳ N và N-1, cả hai đều M15
        "C6.2": {"m15a"},               # kỳ N và N-1, cả hai đều M15a
    }
    actual = {code: set(SPECS[code].requires) for code in ALL_CHECKS}
    assert actual == expected


# --- Presence per (DN, kỳ) ----------------------------------------------------


def test_available_sources_is_empty_for_a_fresh_period(session, company):
    assert available_sources(session, company.id, 2025) == set()


def test_available_sources_lists_each_loaded_source(session, company):
    add_nvl(session, company.id, material_code="A", imported=1, year=2025)
    add_sp(session, company.id, product_code="P", export_qty=1, year=2025)
    add_decl(session, company.id, declaration_no="1", customs_code="E31",
             item_code="A", quantity=1, year=2025)
    session.commit()
    assert available_sources(session, company.id, 2025) == {"m15", "m15a", "bcct"}


def test_bcct_presence_follows_the_period_window_not_the_label(session, company):
    from app.models import CompanyPeriod

    session.add(CompanyPeriod(
        company_id=company.id, period_year=2025,
        period_from=date(2025, 4, 1), period_to=date(2026, 3, 31), is_manual=True,
    ))
    add_decl(session, company.id, declaration_no="1", customs_code="E31", item_code="A",
             quantity=1, year=2025, declaration_date=date(2025, 1, 5))
    session.commit()
    assert "bcct" not in available_sources(session, company.id, 2025)


def test_missing_sources_reports_what_the_check_cannot_read():
    assert missing_sources("C1.1", {"m15"}) == ("bcct",)
    assert missing_sources("C1.1", {"m15", "bcct"}) == ()
    assert missing_sources("C4.3", {"m15"}) == ("m15a", "m16")


def test_unknown_check_never_skips():
    assert missing_sources("X.1", set()) == ()


# --- run_checks ghi not_evaluable --------------------------------------------


def _run(company_code: str, year: int, session):
    from app.pipeline.run_checks import run_checks

    return run_checks(company_code, year, session=session)


def test_bcct_only_period_skips_the_checks_that_need_bcqt(session, company):
    add_decl(session, company.id, declaration_no="1", customs_code="E31",
             item_code="A", quantity=100, year=2025)
    session.commit()

    stats = _run(company.code, 2025, session)

    runs = {
        r.check_code: r
        for r in session.scalars(
            select(CheckRun).where(CheckRun.company_id == company.id)
        ).all()
    }
    # Thuần BCCT → chạy thật.
    assert runs["C3.1"].status == "ok"
    assert runs["C3.2"].status == "ok"
    # Cần BCQT → skip, KHÔNG phải "chạy rồi, 0 phát hiện".
    assert runs["C2.1"].status == "not_evaluable"
    assert "Mẫu 15 — Cân đối NVL" in runs["C2.1"].status_reason
    assert runs["C4.3"].status == "not_evaluable"
    for label in ("Mẫu 15 — Cân đối NVL", "Mẫu 15a", "Mẫu 16"):
        assert label in runs["C4.3"].status_reason
    assert runs["C2.1"].finding_count == 0
    assert stats.findings_per_check.get("C2.1", 0) == 0
    assert "Mẫu 15 — Cân đối NVL" in stats.not_evaluable["C2.1"]


def test_not_evaluable_clears_once_the_source_arrives(session, company):
    add_decl(session, company.id, declaration_no="1", customs_code="E31",
             item_code="A", quantity=100, year=2025)
    session.commit()
    _run(company.code, 2025, session)

    add_nvl(session, company.id, material_code="A", imported=100, closing=100, year=2025)
    session.commit()
    _run(company.code, 2025, session)

    run = session.scalar(
        select(CheckRun).where(
            CheckRun.company_id == company.id, CheckRun.check_code == "C2.1"
        )
    )
    assert run.status_reason is None
    assert run.status == "ok"


def test_full_sources_leave_nothing_unevaluated(session, company):
    """Đủ nguồn → không check nào bị cổng NGUỒN chặn.

    Không khẳng định `not_evaluable == {}`: cổng độ phủ định mức (#62) vẫn có thể
    dừng C4.3 ở kỳ biên vì lý do KHÁC — thiếu `first_bcqt_year`, không phải thiếu
    nguồn. Hai cổng dùng chung một trạng thái nên phải phân biệt bằng lý do.
    """
    from app.models import Norm

    add_nvl(session, company.id, material_code="A", imported=100, closing=100, year=2025)
    add_sp(session, company.id, product_code="P", export_qty=10, closing=0, year=2025)
    session.add(Norm(company_id=company.id, period_year=2025, product_code="P",
                     material_code="A", norm_qty=1.0))
    add_decl(session, company.id, declaration_no="1", customs_code="E31",
             item_code="A", quantity=100, year=2025)
    session.commit()

    stats = _run(company.code, 2025, session)
    assert not [r for r in stats.not_evaluable.values() if MISSING_PREFIX in r]
    runs = session.scalars(
        select(CheckRun).where(CheckRun.company_id == company.id)
    ).all()
    assert all(MISSING_PREFIX not in (r.status_reason or "") for r in runs)


# --- Điểm năm không coi check chưa đánh giá được là sạch ----------------------


def test_not_evaluable_checks_are_excluded_from_the_score_ceiling(session, company):
    from app.checks.scoring import compute_company_year_score
    from app.models import Finding

    findings = [Finding(
        company_id=company.id, period_year=2025, check_code="C3.2",
        severity="critical", subject_type="item_code", subject_key="A", title="x",
    )]
    denominators = {"nvl": 1, "tp": 1, "m16": 1}
    full = compute_company_year_score(findings, denominators)
    partial = compute_company_year_score(
        findings, denominators, not_evaluable={"C2.1", "C2.3"}
    )
    assert partial["max_raw"] < full["max_raw"]
    assert partial["score"] > full["score"]
    assert partial["not_evaluable"] == ["C2.1", "C2.3"]


# --- UI phân biệt "chưa chạy" với "0 phát hiện" -------------------------------


def test_company_detail_separates_not_run_from_no_findings():
    new_engine, new_session = _setup_db()
    try:
        from datetime import datetime

        from app.models import DeclarationLine

        with new_session() as db:
            c = db.scalar(select(Company).where(Company.code == "DN_077"))
            db.add(DeclarationLine(
                company_id=c.id, period_year=2025, declaration_no="9001",
                declaration_date=date(2025, 6, 1), customs_code="E31", line_no=1,
                item_code="A", quantity=1.0, unit="PCE",
            ))
            db.add(CheckRun(
                company_id=c.id, period_year=2025, check_code="C2.1",
                ran_at=datetime(2026, 7, 31, 0, 0, 0), finding_count=0,
                status="not_evaluable", data_version=0,
                status_reason="Kỳ này chưa có Mẫu 15 — Cân đối NVL",
            ))
            db.commit()
        client = TestClient(app)
        _login(client)
        r = client.get("/companies/DN_077?year=2025")
        assert r.status_code == 200
        assert "Chưa đánh giá được" in r.text
        assert "Mẫu 15" in r.text
    finally:
        _teardown(new_engine)
