"""Nhãn tiếng Việt cho `job.result` — không khoá thô nào lọt ra trang công việc.

Test then chốt: chạy THẬT cả ba handler rồi đối chiếu tập khoá với bảng nhãn.
Handler thêm trường mới mà quên khai nhãn thì test đỏ ngay, không đợi tới lúc
cán bộ nhìn thấy `findings_per_check` trên màn hình.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.jobs.handlers import run_batch_handler, run_checks_handler
from app.jobs.result_labels import (
    JOB_KIND_LABEL_VI,
    RESULT_LABEL_VI,
    describe_result,
)
from app.models import Company, DeclarationLine, NvlBalance
from app.models.job import JobKind


def _company_with_data(session: Session, code: str = "DN_LB") -> Company:
    c = Company(code=code, tax_id="1", name=code)
    session.add(c)
    session.flush()
    session.add_all([
        NvlBalance(company_id=c.id, period_year=2024, material_code="A", unit="KG"),
        DeclarationLine(
            company_id=c.id, period_year=2024, declaration_no="1",
            declaration_date=date(2024, 1, 1), customs_code="E31",
            item_code="A", hs_code="1", quantity=1, unit="KG",
        ),
    ])
    session.commit()
    return c


def test_run_checks_result_keys_all_have_labels(session: Session) -> None:
    c = _company_with_data(session)
    result = run_checks_handler({"company_code": c.code, "year": 2024}, session)
    assert set(result) <= set(RESULT_LABEL_VI), (
        f"khoá chưa có nhãn: {set(result) - set(RESULT_LABEL_VI)}"
    )


def test_run_batch_result_keys_all_have_labels(session: Session) -> None:
    c = _company_with_data(session)
    result = run_batch_handler({"company_code": c.code}, session)
    assert set(result) <= set(RESULT_LABEL_VI), (
        f"khoá chưa có nhãn: {set(result) - set(RESULT_LABEL_VI)}"
    )


def test_run_batch_no_data_result_keys_all_have_labels(session: Session) -> None:
    """Nhánh 'không có dữ liệu' trả bộ khoá khác — cũng phải có nhãn đủ."""
    c = Company(code="DN_EMPTY", tax_id="2", name="DN_EMPTY")
    session.add(c)
    session.commit()
    result = run_batch_handler({"company_code": c.code}, session)
    assert set(result) <= set(RESULT_LABEL_VI), (
        f"khoá chưa có nhãn: {set(result) - set(RESULT_LABEL_VI)}"
    )


def test_overview_batch_result_keys_all_have_labels() -> None:
    """`run_overview_batch_job` cần LLM nên chốt trên bộ khoá nó khai ở return."""
    keys = {
        "company_code", "year", "created", "skipped", "skipped_fresh",
        "skipped_not_reached", "failed", "created_checks", "failed_checks",
        "stopped_reason",
    }
    assert keys <= set(RESULT_LABEL_VI), (
        f"khoá chưa có nhãn: {keys - set(RESULT_LABEL_VI)}"
    )


def test_every_job_kind_has_a_label() -> None:
    assert {k.value for k in JobKind} <= set(JOB_KIND_LABEL_VI)


@pytest.mark.parametrize(("value", "expected"), [
    (None, "—"),
    ([], "—"),
    ({}, "—"),
    ("", "—"),
    (0, "0"),
    (True, "Có"),
    (False, "Không"),
    (["C1.1", "C1.3"], "C1.1, C1.3"),
    ({"C1.1": 3, "C1.3": 5}, "C1.1: 3 · C1.3: 5"),
    ({2024: {"total_findings": 7}}, "2024 — total_findings: 7"),
])
def test_value_formatting(value: object, expected: str) -> None:
    assert describe_result({"total_findings": value})[0]["value"] == expected


def test_unknown_key_falls_back_to_the_key_itself() -> None:
    rows = describe_result({"khoa_la": 1})
    assert rows == [{"label": "khoa_la", "value": "1"}]


def test_empty_result_gives_no_rows() -> None:
    assert describe_result(None) == []
    assert describe_result({}) == []
