"""T2 (#82) — lớp cách gỡ đi kèm mọi lần `not_evaluable` (ADR #24 mục 2).

Ba lớp: cần file kỳ này · cần kỳ khác hoặc một xác nhận · không nạp gì thêm được.
Lớp gắn tại chỗ QUYẾT ĐỊNH là không đánh giá được, không suy theo mã kiểm tra, và
đi cùng đường ghi trạng thái — kể cả đường cổng thiếu nguồn ở bộ điều phối, chỗ
trước đây tự ghi `check_runs.status` mà không dựng `NotEvaluable` nào.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.checks.c3_classify import check_c3_3
from app.checks.c6_cross_period import check_c6_1, classify_missing_prev_period
from app.checks.not_evaluable import (
    REMEDY_CLASSES,
    REMEDY_NEED_FILE_THIS_PERIOD,
    REMEDY_NEED_OTHER_PERIOD_OR_CONFIRMATION,
    REMEDY_NOTHING_TO_LOAD,
    TARGET_COMPANY_FIELD,
    TARGET_DOCUMENT,
    TARGET_PERIOD,
    NotEvaluable,
    RemedyTarget,
)
from app.checks.sources import classify_missing_sources
from app.models import CheckRun
from tests.conftest import add_decl, add_nvl
from tests.test_checks.test_c4_norm import add_norm

# --- Kiểu mang (lý do, lớp) ---------------------------------------------------


def test_the_three_remedy_classes_are_exactly_these():
    assert REMEDY_CLASSES == frozenset({
        "need-file-this-period",
        "need-other-period-or-confirmation",
        "nothing-to-load",
    })


def test_not_evaluable_without_a_remedy_class_is_a_construction_error():
    """Trường bắt buộc: không có mặc định nào để một chỗ gọi mới quên gán lớp."""
    with pytest.raises(TypeError):
        NotEvaluable("Thiếu Mẫu 15.")


def test_not_evaluable_rejects_a_remedy_class_outside_the_three():
    with pytest.raises(ValueError):
        NotEvaluable("Thiếu Mẫu 15.", remedy="cần-gì-đó")


def test_not_evaluable_keeps_the_class_it_was_built_with():
    ne = NotEvaluable("Thiếu Mẫu 15.", remedy=REMEDY_NEED_FILE_THIS_PERIOD)
    assert ne.remedy == REMEDY_NEED_FILE_THIS_PERIOD


def test_a_remedy_target_names_one_of_three_kinds():
    with pytest.raises(ValueError):
        RemedyTarget("chỗ-nào-đó", "2023")


# --- Nguồn sinh 1: cổng thiếu nguồn ở bộ điều phối -----------------------------


def test_the_missing_source_gate_is_class_one_and_points_at_a_document_type():
    remedy, target = classify_missing_sources(("m15", "m16"))
    assert remedy == REMEDY_NEED_FILE_THIS_PERIOD
    assert target == RemedyTarget(TARGET_DOCUMENT, "m15")


def test_the_missing_source_gate_has_no_target_when_nothing_is_missing():
    remedy, target = classify_missing_sources(())
    assert remedy == REMEDY_NEED_FILE_THIS_PERIOD
    assert target is None


def test_run_checks_stores_the_class_of_the_missing_source_gate(session, company):
    """Đường thiếu nguồn dựng `NotEvaluable` và ghi lớp — không còn ghi thẳng."""
    from app.pipeline.run_checks import run_checks

    add_decl(session, company.id, declaration_no="1", customs_code="E31",
             item_code="A", quantity=100, year=2025)
    session.commit()
    run_checks(company.code, 2025, session=session)

    runs = {
        r.check_code: r
        for r in session.scalars(
            select(CheckRun).where(CheckRun.company_id == company.id)
        ).all()
    }
    assert runs["C2.1"].status == "not_evaluable"
    assert runs["C2.1"].remedy == REMEDY_NEED_FILE_THIS_PERIOD
    # Check chạy được không mang lớp nào.
    assert runs["C3.1"].status == "ok"
    assert runs["C3.1"].remedy is None


def test_the_stored_class_clears_when_the_check_becomes_evaluable(session, company):
    """Chạy lại sau khi nguồn về: lớp cũ phải mất, như `status_reason` vẫn làm."""
    from app.pipeline.run_checks import run_checks

    add_decl(session, company.id, declaration_no="1", customs_code="E31",
             item_code="A", quantity=100, year=2025)
    session.commit()
    run_checks(company.code, 2025, session=session)

    add_nvl(session, company.id, material_code="A", imported=100, closing=100, year=2025)
    session.commit()
    run_checks(company.code, 2025, session=session)

    run = session.scalar(
        select(CheckRun).where(
            CheckRun.company_id == company.id, CheckRun.check_code == "C2.1"
        )
    )
    assert run.status == "ok"
    assert run.remedy is None


# --- Nguồn sinh 2: phân loại loại hình DN (C3.3) ------------------------------


def test_c3_3_missing_both_comparison_sides_is_class_one(session, company):
    """Vế đối chiếu là HOẶC (tờ khai hoặc Mẫu 16) — cả hai đều là file của kỳ này."""
    add_nvl(session, company.id, material_code="A", unit="KG")
    session.commit()
    result = check_c3_3(session, company.id, 2024)
    assert isinstance(result, NotEvaluable)
    assert result.remedy == REMEDY_NEED_FILE_THIS_PERIOD


# --- Nguồn sinh 3: đối chiếu liên kỳ (C6.1) -----------------------------------


def test_c6_1_missing_previous_period_is_class_two(session, company):
    add_nvl(session, company.id, material_code="A", opening=100, year=2024)
    session.commit()
    result = check_c6_1(session, company.id, 2024)
    assert isinstance(result, NotEvaluable)
    assert result.remedy == REMEDY_NEED_OTHER_PERIOD_OR_CONFIRMATION


def test_the_previous_period_gate_points_at_that_period():
    remedy, target = classify_missing_prev_period(2023)
    assert remedy == REMEDY_NEED_OTHER_PERIOD_OR_CONFIRMATION
    assert target == RemedyTarget(TARGET_PERIOD, 2023)


# --- Bộ ba xuất hiện đủ trên cùng một mã kiểm tra ------------------------------


def test_c4_3_produces_more_than_one_class_across_periods(session, company):
    """Lớp không suy được từ mã kiểm tra: C4.3 sinh cả ba lớp tuỳ kỳ (ADR #24)."""
    from app.checks.c4_norm import check_c4_3
    from tests.conftest import add_sp

    # Kỳ biên chưa xác nhận năm đầu nộp BCQT → lớp 2.
    add_norm(session, company.id, product_code="TP", material_code="X",
             norm_qty=2.0, year=2024)
    add_sp(session, company.id, product_code="TP", intake=100, year=2024)
    add_nvl(session, company.id, material_code="X", production_out=100, year=2024)
    session.commit()
    boundary = check_c4_3(session, company.id, 2024)
    assert isinstance(boundary, NotEvaluable)
    assert boundary.remedy == REMEDY_NEED_OTHER_PERIOD_OR_CONFIRMATION

    # Kỳ 2025: mọi kỳ trước đã có dòng định mức, mã mới sản xuất chưa từng khai → lớp 3.
    add_sp(session, company.id, product_code="MADE", intake=50, year=2025)
    add_nvl(session, company.id, material_code="X", production_out=50, year=2025)
    session.commit()
    coverage = check_c4_3(session, company.id, 2025)
    assert isinstance(coverage, NotEvaluable)
    assert coverage.remedy == REMEDY_NOTHING_TO_LOAD


def test_every_class_used_by_the_producers_is_one_of_the_three():
    for value in (
        REMEDY_NEED_FILE_THIS_PERIOD,
        REMEDY_NEED_OTHER_PERIOD_OR_CONFIRMATION,
        REMEDY_NOTHING_TO_LOAD,
    ):
        assert value in REMEDY_CLASSES
    assert RemedyTarget(TARGET_COMPANY_FIELD, "first_bcqt_year").kind == "company-field"
