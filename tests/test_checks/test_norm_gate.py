"""T6 (#62) — cổng độ phủ định mức chặn C4.3 (quyết định Q1 + Q3).

Hai điều kiện: độ phủ định mức (mã thành phẩm sản xuất trong kỳ chưa từng khai định
mức) và kỳ biên (kỳ sớm nhất hệ thống giữ, chưa xác nhận năm đầu nộp BCQT).
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

import app.checks.c4_norm as c4_mod
from app.checks.c4_norm import check_c4_3
from app.checks.norm_gate import (
    classify_boundary_period,
    classify_norm_coverage,
    earliest_period_held,
    periods_without_norms,
)
from app.checks.not_evaluable import (
    REMEDY_NEED_OTHER_PERIOD_OR_CONFIRMATION,
    REMEDY_NOTHING_TO_LOAD,
    TARGET_COMPANY_FIELD,
    TARGET_PERIOD,
    NotEvaluable,
    RemedyTarget,
)
from app.models import CompanyYearScore
from app.pipeline.run_checks import run_checks
from tests.conftest import add_nvl, add_sp
from tests.test_checks.test_c4_norm import add_norm


def _seed_period_2024(session, company, *, declare_norm_for_made: bool):
    """2023 có dữ liệu (nên 2024 không phải kỳ biên); 2024 sản xuất mã MADE.

    `declare_norm_for_made=False` → MADE chưa từng khai định mức → cổng độ phủ chặn.
    """
    add_norm(session, company.id, product_code="OTHER", material_code="X", norm_qty=1.0, year=2023)
    if declare_norm_for_made:
        add_norm(
            session, company.id, product_code="MADE", material_code="X",
            norm_qty=2.0, year=2023,
        )
    add_sp(session, company.id, product_code="MADE", intake=100, year=2024)
    add_nvl(session, company.id, material_code="X", imported=200, production_out=100, year=2024)
    session.commit()


# --- Điều kiện A: độ phủ định mức ---


def test_product_never_declaring_a_norm_blocks_the_whole_period(session, company):
    _seed_period_2024(session, company, declare_norm_for_made=False)
    result = check_c4_3(session, company.id, 2024)
    assert isinstance(result, NotEvaluable)
    assert "1 mã thành phẩm" in result.reason
    assert "chưa từng khai định mức" in result.reason


def test_an_inherited_norm_satisfies_the_coverage_gate(session, company):
    """Cùng fixture nhưng MADE có định mức khai từ 2023 → chạy bình thường."""
    _seed_period_2024(session, company, declare_norm_for_made=True)
    findings = check_c4_3(session, company.id, 2024)
    assert not isinstance(findings, NotEvaluable)
    # 2.0 × 100 = 200 tiêu hao lý thuyết vs 100 xuất SX → +100%.
    assert [f.subject_key for f in findings] == ["X"]
    assert findings[0].details["norm_source_years"] == [2023]


def test_a_product_with_no_production_does_not_trip_the_gate(session, company):
    """Chưa khai định mức nhưng cũng không sản xuất trong kỳ → không chặn."""
    _seed_period_2024(session, company, declare_norm_for_made=True)
    add_sp(session, company.id, product_code="IDLE", intake=0, export_qty=50, year=2024)
    session.commit()
    assert not isinstance(check_c4_3(session, company.id, 2024), NotEvaluable)


def test_one_book_missing_norms_blocks_the_run_and_the_reason_names_it(session, company):
    """Độ mịn theo sổ: `check_runs` khoá theo (DN, kỳ) nên một sổ vướng là chặn cả kỳ.

    Sổ EPE đủ định mức và có chênh lệch thật; sổ GC thiếu định mức của 1 mã. Cả lần
    chạy `not_evaluable`, kể cả phát hiện của sổ EPE.
    """
    add_norm(
        session, company.id, product_code="TP_E", material_code="X",
        norm_qty=2.0, year=2023, book="EPE",
    )
    add_sp(session, company.id, product_code="TP_E", intake=100, year=2024, book="EPE")
    add_nvl(session, company.id, material_code="X", production_out=100, year=2024, book="EPE")
    add_sp(session, company.id, product_code="TP_G", intake=100, year=2024, book="GC")
    session.commit()

    result = check_c4_3(session, company.id, 2024)
    assert isinstance(result, NotEvaluable)
    assert "1 mã thành phẩm" in result.reason
    assert "Sổ GC (gia công): 1 mã" in result.reason
    assert "EPE" not in result.reason


# --- Điều kiện B: kỳ biên ---


def test_earliest_period_without_first_bcqt_year_is_not_evaluable(session, company):
    add_norm(session, company.id, product_code="TP", material_code="X", norm_qty=2.0, year=2024)
    add_sp(session, company.id, product_code="TP", intake=100, year=2024)
    add_nvl(session, company.id, material_code="X", production_out=100, year=2024)
    session.commit()

    assert company.first_bcqt_year is None
    result = check_c4_3(session, company.id, 2024)
    assert isinstance(result, NotEvaluable)
    assert "kỳ sớm nhất" in result.reason
    assert "2024" in result.reason


def test_earliest_period_evaluates_once_the_officer_confirms_first_bcqt_year(session, company):
    add_norm(session, company.id, product_code="TP", material_code="X", norm_qty=2.0, year=2024)
    add_sp(session, company.id, product_code="TP", intake=100, year=2024)
    add_nvl(session, company.id, material_code="X", production_out=100, year=2024)
    company.first_bcqt_year = 2024
    session.commit()

    findings = check_c4_3(session, company.id, 2024)
    assert not isinstance(findings, NotEvaluable)
    assert [f.subject_key for f in findings] == ["X"]


def test_first_bcqt_year_of_another_year_does_not_unlock_the_boundary(session, company):
    """Cán bộ ghi năm đầu nộp BCQT là 2020 mà kỳ sớm nhất đang giữ là 2024 → vẫn chặn:
    xác nhận đó nói chính xác rằng còn bản khai trước cửa sổ dữ liệu."""
    add_norm(session, company.id, product_code="TP", material_code="X", norm_qty=2.0, year=2024)
    add_sp(session, company.id, product_code="TP", intake=100, year=2024)
    add_nvl(session, company.id, material_code="X", production_out=100, year=2024)
    company.first_bcqt_year = 2020
    session.commit()

    assert isinstance(check_c4_3(session, company.id, 2024), NotEvaluable)


def test_a_period_after_the_earliest_one_is_not_blocked_by_the_boundary(session, company):
    _seed_period_2024(session, company, declare_norm_for_made=True)
    assert earliest_period_held(session, company.id) == 2023
    assert company.first_bcqt_year is None
    # Kỳ 2024 > kỳ biên 2023 → điều kiện kỳ biên không áp, dù chưa biết năm đầu BCQT.
    assert not isinstance(check_c4_3(session, company.id, 2024), NotEvaluable)


def test_company_with_no_bcqt_data_has_no_earliest_period(session, company):
    """Không có dòng nào → không suy được kỳ biên, cổng kỳ biên không chặn."""
    assert earliest_period_held(session, company.id) is None
    assert check_c4_3(session, company.id, 2024) == []


# --- Nghiệm thu ticket: phát hiện biến mất không được làm điểm rủi ro giảm ---


def _seed_scored_company(session, company):
    """Hình dạng giống DN 10 pilot: C4.3 sinh phần lớn điểm, cổng độ phủ chặn kỳ 2024."""
    add_norm(session, company.id, product_code="TP", material_code="M0", norm_qty=1.0, year=2023)
    add_sp(session, company.id, product_code="TP", intake=100, year=2024)
    # Mã chưa từng khai định mức → cổng độ phủ bật ở kỳ 2024.
    add_sp(session, company.id, product_code="MADE", intake=50, year=2024)
    for i in range(6):
        add_norm(
            session, company.id, product_code="TP", material_code=f"M{i}",
            norm_qty=2.0, year=2024,
        )
        add_nvl(
            session, company.id, material_code=f"M{i}", opening=10, imported=100,
            production_out=100, closing=-5, year=2024,
        )
    session.commit()


def _year_score(session, company_id: int) -> CompanyYearScore:
    return session.scalar(
        select(CompanyYearScore).where(
            CompanyYearScore.company_id == company_id,
            CompanyYearScore.period_year == 2024,
        )
    )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Loại C4.3 khỏi cả tử số lẫn trần kéo điểm về trung bình các luật còn lại. "
        "Khi C4.3 đang chấm CAO hơn trung bình đó thì cổng làm điểm GIẢM. Đo trên "
        "pilot 06/08/2026: DN 10 kỳ 2024 3→2, kỳ 2025 3→1, kỳ 2026 8→6; DN 7/2025 "
        "6→4; DN 9/2025 28→27. Chỉ DN 8/2024 tăng 129→132. Điều kiện chính xác: "
        "điểm không giảm ⟺ rule_score(C4.3) ≤ 10 × raw / max_raw."
    ),
)
def test_gate_does_not_lower_the_risk_score(session, company, monkeypatch):
    """Nghiệm thu #62: phát hiện biến mất vì thiếu dữ liệu KHÔNG được làm DN sạch hơn.

    So trực tiếp cùng một fixture: cổng TẮT rồi cổng BẬT.
    """
    _seed_scored_company(session, company)

    monkeypatch.setattr(c4_mod, "norm_coverage_gate", lambda *_a, **_k: None)
    run_checks(company.code, 2024, session=session)
    off = _year_score(session, company.id)
    off_score, off_raw, off_max = off.score, off.breakdown["raw"], off.breakdown["max_raw"]
    off_c43 = off.breakdown["rule_scores"].get("C4.3")

    monkeypatch.undo()
    run_checks(company.code, 2024, session=session)
    on = _year_score(session, company.id)

    assert off_c43 and off_c43 > 0, "fixture phải sinh điểm C4.3 thì phép so mới có nghĩa"
    assert on.breakdown["not_evaluable"] == ["C4.3"]
    assert on.score >= off_score, (
        f"cổng làm điểm giảm {off_score} → {on.score}: "
        f"raw {off_raw} → {on.breakdown['raw']}, "
        f"max_raw {off_max} → {on.breakdown['max_raw']}, C4.3 = {off_c43}"
    )


# --- Lớp cách gỡ của cổng định mức (#82, ADR #24 mục 2) -----------------------


def test_the_boundary_branch_asks_for_a_company_level_confirmation(session, company):
    """Kỳ biên gỡ bằng trường `first_bcqt_year` của DN, không bằng file kỳ này."""
    add_norm(session, company.id, product_code="TP", material_code="X", norm_qty=2.0, year=2024)
    add_sp(session, company.id, product_code="TP", intake=100, year=2024)
    add_nvl(session, company.id, material_code="X", production_out=100, year=2024)
    session.commit()

    result = check_c4_3(session, company.id, 2024)
    assert isinstance(result, NotEvaluable)
    assert result.remedy == REMEDY_NEED_OTHER_PERIOD_OR_CONFIRMATION
    assert classify_boundary_period() == (
        REMEDY_NEED_OTHER_PERIOD_OR_CONFIRMATION,
        RemedyTarget(TARGET_COMPANY_FIELD, "first_bcqt_year"),
    )


def test_the_coverage_branch_is_class_two_while_an_earlier_period_has_no_norm_rows(
    session, company
):
    """Kỳ 2023 nằm trong khoảng dữ liệu mà chưa có dòng định mức nào → còn Mẫu 16
    nạp được, cách gỡ là nạp nó chứ không phải kết luận về DN."""
    add_sp(session, company.id, product_code="MADE", intake=10, year=2023)
    add_sp(session, company.id, product_code="MADE", intake=100, year=2024)
    add_nvl(session, company.id, material_code="X", production_out=100, year=2024)
    session.commit()

    assert earliest_period_held(session, company.id) == 2023
    assert periods_without_norms(session, company.id, 2024) == [2023]
    result = check_c4_3(session, company.id, 2024)
    assert isinstance(result, NotEvaluable)
    assert result.remedy == REMEDY_NEED_OTHER_PERIOD_OR_CONFIRMATION
    assert classify_norm_coverage(session, company.id, 2024) == (
        REMEDY_NEED_OTHER_PERIOD_OR_CONFIRMATION,
        RemedyTarget(TARGET_PERIOD, 2023),
    )


def test_the_coverage_branch_is_class_three_once_every_earlier_period_has_norms(
    session, company
):
    """Mọi kỳ trước trong khoảng dữ liệu đã có dòng định mức → hết đường nạp, đây là
    kết luận về DN (mã thành phẩm chưa từng khai định mức)."""
    _seed_period_2024(session, company, declare_norm_for_made=False)

    assert periods_without_norms(session, company.id, 2024) == []
    result = check_c4_3(session, company.id, 2024)
    assert isinstance(result, NotEvaluable)
    assert result.remedy == REMEDY_NOTHING_TO_LOAD
    assert classify_norm_coverage(session, company.id, 2024) == (
        REMEDY_NOTHING_TO_LOAD,
        None,
    )


def test_a_gap_year_inside_the_data_window_counts_as_loadable(session, company):
    """Kỳ 2023 không có dòng nào ở bảng Tầng 1 nào vẫn nằm trong khoảng dữ liệu:
    Mẫu 16 của kỳ đó vẫn nạp được."""
    add_norm(session, company.id, product_code="TP", material_code="X", norm_qty=1.0, year=2022)
    add_sp(session, company.id, product_code="MADE", intake=100, year=2024)
    session.commit()

    assert periods_without_norms(session, company.id, 2024) == [2023]
