"""Tests — check mở rộng (SQL) tích hợp vào run_checks pipeline + scoring."""

from __future__ import annotations

from sqlalchemy import func, select

from app.models import CheckDefinition, CheckStatus, CompanyYearScore, Finding
from app.pipeline.run_checks import run_checks
from tests.conftest import add_nvl

_SQL_NEG = (
    "SELECT 'critical' AS severity, material_code AS subject_key, "
    "'Tồn âm ' || material_code AS title, '' AS detail "
    "FROM nvl_balances WHERE company_id = :company_id AND period_year = :period_year "
    "AND closing_qty < -0.01"
)


def _sql_check(code: str, status: str, sql: str = _SQL_NEG) -> CheckDefinition:
    return CheckDefinition(
        code=code, kind="sql", title="Tồn cuối âm (mở rộng)", description="",
        spec={}, sql_snippet=sql, subject_table="nvl_balances",
        subject_col="material_code", scope="nvl", default_severity="critical",
        status=status,
    )


def test_published_sql_check_runs_in_pipeline(session, company):
    session.add(_sql_check("X.1", CheckStatus.PUBLISHED))
    add_nvl(session, company.id, material_code="NVL_BAD", closing=-5)
    add_nvl(session, company.id, material_code="NVL_OK", closing=10)
    session.commit()

    stats = run_checks(company.code, 2024, session=session)

    findings = session.scalars(
        select(Finding).where(Finding.company_id == company.id, Finding.check_code == "X.1")
    ).all()
    assert len(findings) == 1
    assert findings[0].subject_key == "NVL_BAD"
    assert findings[0].evidence_refs[0]["table"] == "nvl_balances"
    assert "X.1" in stats.findings_per_check


def test_draft_sql_check_not_run(session, company):
    session.add(_sql_check("X.99", CheckStatus.DRAFT))
    add_nvl(session, company.id, material_code="NVL001", closing=-5)
    session.commit()

    run_checks(company.code, 2024, session=session)

    assert session.scalars(select(Finding).where(Finding.check_code == "X.99")).all() == []


def test_sql_check_findings_wiped_on_rerun(session, company):
    session.add(_sql_check("X.1", CheckStatus.PUBLISHED))
    add_nvl(session, company.id, material_code="NVL_BAD", closing=-5)
    session.commit()

    def _count():
        return session.scalar(
            select(func.count()).select_from(Finding).where(Finding.check_code == "X.1")
        )

    run_checks(company.code, 2024, session=session)
    c1 = _count()
    run_checks(company.code, 2024, session=session)
    c2 = _count()
    assert c1 == c2 == 1  # không nhân đôi


def test_scoped_rerun_of_dynamic_check_does_not_duplicate(session, company):
    """Chạy lẻ 1 check mở rộng (nút "Chạy lại X.1", WS2-2) phải xoá finding cũ trước
    khi dựng lại — pre-delete phải gồm cả mã dynamic, không chỉ built-in."""
    session.add(_sql_check("X.1", CheckStatus.PUBLISHED))
    add_nvl(session, company.id, material_code="NVL_BAD", closing=-5)
    session.commit()

    def _count():
        return session.scalar(
            select(func.count()).select_from(Finding).where(Finding.check_code == "X.1")
        )

    run_checks(company.code, 2024, session=session)  # full
    assert _count() == 1
    run_checks(company.code, 2024, only={"X.1"}, session=session)  # scoped
    assert _count() == 1  # không nhân đôi


def test_bad_sql_check_does_not_crash_run(session, company):
    """Check published có SQL lỗi → bỏ qua, không làm hỏng cả run."""
    session.add(_sql_check("X.1", CheckStatus.PUBLISHED, sql="SELECT broken FROM nope"))
    add_nvl(session, company.id, material_code="N", closing=-5)
    session.commit()
    stats = run_checks(company.code, 2024, session=session)  # không raise
    assert session.scalars(select(Finding).where(Finding.check_code == "X.1")).all() == []
    assert stats is not None


def test_published_check_counted_in_score_max_raw(session, company):
    """Check published mở rộng scope vào max_raw (trần điểm) — không lệch trần."""
    session.add(_sql_check("X.1", CheckStatus.PUBLISHED))
    add_nvl(session, company.id, material_code="NVL_BAD", closing=-5)
    # 2024 là kỳ sớm nhất của fixture; không xác nhận năm đầu nộp BCQT thì C4.3 trả
    # `not_evaluable` (issue #62) và bị gỡ khỏi trần → đếm 17 luật thay vì 18.
    company.first_bcqt_year = 2024
    session.commit()

    run_checks(company.code, 2024, session=session)

    cys = session.scalar(
        select(CompanyYearScore).where(
            CompanyYearScore.company_id == company.id, CompanyYearScore.period_year == 2024
        )
    )
    assert cys is not None
    # 18 built-in + 1 published dynamic = 19 rule → max_raw = 19*10 + 20 = 210.
    assert cys.breakdown["max_raw"] == 210.0
    assert "X.1" in cys.breakdown["rule_scores"]
