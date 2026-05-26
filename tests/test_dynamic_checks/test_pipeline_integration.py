"""Tests — dynamic checks tích hợp vào run_checks pipeline."""

from __future__ import annotations

from sqlalchemy import select

from app.checks.dynamic_runner import DynamicCheckRunner
from app.models import CheckDefinition, CheckStatus, Finding
from app.pipeline.run_checks import run_checks
from tests.conftest import add_nvl


def test_published_dynamic_check_runs_in_pipeline(session, company):
    """Check động published được include trong run_checks tự động."""
    cd = CheckDefinition(
        code="X.1",
        kind="threshold_compare",
        title="Tồn cuối âm mở rộng",
        description="",
        spec={
            "kind": "threshold_compare",
            "table": "nvl_balances",
            "subject_col": "material_code",
            "metric_col": "closing_qty",
            "thresholds": [{"lt": 0, "severity": "critical"}],
            "title_template": "Tồn cuối {subject_key} âm",
        },
        status=CheckStatus.PUBLISHED,
    )
    session.add(cd)
    session.flush()

    add_nvl(session, company.id, material_code="NVL_BAD", closing=-5)
    add_nvl(session, company.id, material_code="NVL_OK", closing=10)
    session.commit()

    stats = run_checks(company.code, 2024, session=session)

    # Phải có finding X.1
    findings = session.scalars(
        select(Finding).where(
            Finding.company_id == company.id,
            Finding.check_code == "X.1",
        )
    ).all()
    assert len(findings) == 1
    assert findings[0].subject_key == "NVL_BAD"
    assert "X.1" in stats.findings_per_check


def test_draft_dynamic_check_not_run(session, company):
    """Draft check không chạy trong pipeline."""
    cd = CheckDefinition(
        code="X.99",
        kind="threshold_compare",
        title="Draft check",
        description="",
        spec={
            "kind": "threshold_compare",
            "table": "nvl_balances",
            "subject_col": "material_code",
            "metric_col": "closing_qty",
            "thresholds": [{"lt": 999999, "severity": "critical"}],
            "title_template": "Always fire {subject_key}",
        },
        status=CheckStatus.DRAFT,
    )
    session.add(cd)
    add_nvl(session, company.id, material_code="NVL001", closing=5)
    session.commit()

    run_checks(company.code, 2024, session=session)

    findings = session.scalars(
        select(Finding).where(Finding.check_code == "X.99")
    ).all()
    assert findings == []


def test_dynamic_check_included_in_wipe(session, company):
    """Khi chạy lại, findings X.* từ run trước bị xóa."""
    cd = CheckDefinition(
        code="X.1",
        kind="threshold_compare",
        title="T",
        description="",
        spec={
            "kind": "threshold_compare",
            "table": "nvl_balances",
            "subject_col": "material_code",
            "metric_col": "closing_qty",
            "thresholds": [{"lt": 0, "severity": "critical"}],
            "title_template": "Âm {subject_key}",
        },
        status=CheckStatus.PUBLISHED,
    )
    session.add(cd)
    add_nvl(session, company.id, material_code="NVL_BAD", closing=-5)
    session.commit()

    run_checks(company.code, 2024, session=session)
    count_1 = session.scalar(
        select(Finding).where(Finding.check_code == "X.1").with_only_columns(
            __import__("sqlalchemy").func.count()
        )
    )

    # Run lại — findings cũ phải bị wipe, không duplicate
    run_checks(company.code, 2024, session=session)
    count_2 = session.scalar(
        select(Finding).where(Finding.check_code == "X.1").with_only_columns(
            __import__("sqlalchemy").func.count()
        )
    )

    assert count_1 == count_2 == 1
