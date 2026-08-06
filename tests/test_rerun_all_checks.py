"""`scripts.rerun_all_checks` phải phủ HẾT kỳ có finding, không chỉ kỳ có check_runs.

Lượt chạy lại trên prod 06/08/2026 chỉ đụng 7 cặp lấy từ `check_runs`, trong khi tổng
finding đi 18.745 → 17.337: còn 3.928 finding thuộc cặp KHÔNG có dòng `check_runs`,
giữ nguyên kết quả sinh bởi code cũ. `check_runs` chỉ có từ WS3, nên kỳ nào chạy check
trước đó mà chưa chạy lại thì có finding mà không có dòng run.

Trên màn hình chúng hiện "17/17 bài kiểm tra" — đọc như đã đánh giá trọn, thật ra là
số cũ. Đúng cách đọc sai mà #64 sinh ra để chặn.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.models import CheckRun, Company, Finding
from scripts.rerun_all_checks import pairs_to_run, pairs_without_run_record


@pytest.fixture
def two_companies(session):
    a = Company(code="DN_R1", tax_id="7777777771", name="DN R1")
    b = Company(code="DN_R2", tax_id="7777777772", name="DN R2")
    session.add_all([a, b])
    session.flush()
    # DN_R1 2024: có cả check_runs lẫn finding — cặp "bình thường".
    session.add(CheckRun(
        company_id=a.id, period_year=2024, check_code="C2.1",
        ran_at=datetime(2026, 8, 1), finding_count=0, status="ok", data_version=0,
    ))
    session.add(_finding(a.id, 2024, "MAT1"))
    # DN_R2 2023: CHỈ có finding, không có dòng check_runs — cặp bị bỏ sót.
    session.add(_finding(b.id, 2023, "MAT2"))
    session.commit()
    return a, b


def _finding(company_id: int, year: int, key: str) -> Finding:
    return Finding(
        company_id=company_id, period_year=year, check_code="C2.1",
        severity="critical", subject_type="material_code", subject_key=key, title="x",
    )


def test_pairs_include_a_period_that_only_has_findings(session, two_companies):
    assert pairs_to_run(session, None) == [("DN_R1", 2024), ("DN_R2", 2023)]


def test_pairs_can_be_filtered_to_one_company(session, two_companies):
    assert pairs_to_run(session, "DN_R2") == [("DN_R2", 2023)]


def test_periods_without_a_run_record_are_named(session, two_companies):
    """`report` phải chỉ đúng cặp đang giữ số cũ, không chỉ đếm tổng."""
    assert pairs_without_run_record(session, None) == [("DN_R2", 2023)]


def test_no_stale_pairs_when_every_period_has_a_run_record(session):
    c = Company(code="DN_R3", tax_id="7777777773", name="DN R3")
    session.add(c)
    session.flush()
    session.add(CheckRun(
        company_id=c.id, period_year=2025, check_code="C2.1",
        ran_at=datetime(2026, 8, 1), finding_count=1, status="ok", data_version=0,
    ))
    session.add(_finding(c.id, 2025, "MAT3"))
    session.commit()
    assert pairs_without_run_record(session, None) == []
    assert pairs_to_run(session, None) == [("DN_R3", 2025)]


def test_combo_only_period_is_still_covered(session):
    """Kỳ chỉ còn finding COMBO_* vẫn phải chạy lại — combo cũng là số cũ."""
    c = Company(code="DN_R4", tax_id="7777777774", name="DN R4")
    session.add(c)
    session.flush()
    session.add(Finding(
        company_id=c.id, period_year=2022, check_code="COMBO_HS_GAMING",
        severity="warning", subject_type="material_code", subject_key="K", title="x",
    ))
    session.commit()
    assert ("DN_R4", 2022) in pairs_to_run(session, None)
