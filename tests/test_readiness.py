"""T5 (#85) — nguồn duy nhất cho "đủ dữ liệu cho N/M" + danh sách vướng mắc.

Phép đếm đo theo DÒNG đã nạp (kiểm tra đọc dòng), nhưng câu chữ cách gỡ tra BẢN GHI
FILE trước khi chọn động từ: file có thể đã nằm trên đĩa, đã đăng ký, mà chưa ghi
dòng nào (lượt nạp dừng ở cổng xác nhận cột). Đo theo dòng một mình thì hệ thống bảo
cán bộ tải lên thứ họ vừa tải; đo theo file một mình thì xoá file xong vẫn báo "đủ".

Dấu hiệu cũ là TRỤC RIÊNG: sau khi xoá file, "đủ dữ liệu" vẫn đúng — kiểm tra vẫn
chạy được, chỉ là dữ liệu không còn khớp bộ file (ADR #24 mục 1, spec mục 3).
"""

from __future__ import annotations

import json

from sqlalchemy import select

from app.checks import ALL_CHECKS
from app.checks.not_evaluable import (
    REMEDY_NEED_FILE_THIS_PERIOD,
    REMEDY_NEED_OTHER_PERIOD_OR_CONFIRMATION,
    REMEDY_NOTHING_TO_LOAD,
    TARGET_DOCUMENT,
    TARGET_PERIOD,
    RemedyTarget,
)
from app.checks.registry import SPECS
from app.models import CheckDefinition, CheckRun, CheckStatus, CompanyPeriod, DataFile
from app.models.data_file import DataFileStatus
from app.pipeline.readiness import (
    BLOCKER_CHECK,
    BLOCKER_COVERAGE,
    BLOCKER_FILE,
    CHECK_CONCLUSION,
    CHECK_READY,
    CHECK_RUN_TO_KNOW,
    SLOT_NEEDS_BOOK,
    SLOT_NEEDS_COLUMN_REVIEW,
    SLOT_NO_FILE,
    SLOT_NOT_PARSED,
    SLOT_PARSE_ERROR,
    SLOT_READY,
    SLOT_STALE,
    SLOT_STATES,
    period_readiness,
)
from app.pipeline.run_checks import run_checks
from tests.conftest import add_decl, add_norm, add_nvl, add_sp

# --- Dựng bản ghi file ---------------------------------------------------------


def add_file(
    session,
    company_id: int,
    *,
    slot: str,
    year: int = 2024,
    status: str = DataFileStatus.OK,
    book: str | None = None,
    needs_review: bool = False,
    message: str | None = None,
    name: str | None = None,
) -> DataFile:
    """Một dòng registry `data_files` — không đụng đĩa, không chạy hàng đợi."""
    filename = name or f"{slot}.xlsx"
    detail = None
    if needs_review:
        detail = json.dumps(
            {
                "review": "needs_review",
                "columns": [
                    {
                        "field": "material_code",
                        "label": "Mã NVL",
                        "evidence": "position-only",
                        "review": "needs_review",
                    }
                ],
            },
            ensure_ascii=False,
        )
    row = DataFile(
        company_id=company_id,
        period_year=year,
        slot=slot,
        original_filename=filename,
        stored_path=f"DN/{year}/{slot}/{filename}",
        size_bytes=1024,
        book=book,
        parse_status=status,
        parse_message=message,
        parse_detail=detail,
    )
    session.add(row)
    return row


def slot_state(readiness, slot: str) -> str:
    return next(s.state for s in readiness.slots if s.slot == slot)


# --- Bảy trạng thái của một (loại tài liệu, kỳ) --------------------------------


def test_the_seven_states_are_exactly_these():
    assert SLOT_STATES == (
        SLOT_NO_FILE,
        SLOT_NOT_PARSED,
        SLOT_PARSE_ERROR,
        SLOT_NEEDS_COLUMN_REVIEW,
        SLOT_NEEDS_BOOK,
        SLOT_READY,
        SLOT_STALE,
    )


def test_state_one_no_file_record_at_all(session, company):
    r = period_readiness(session, company.id, 2024)
    assert slot_state(r, "m15") == SLOT_NO_FILE


def test_state_two_a_registered_file_never_read_says_press_ingest(session, company):
    """Ca đúng của cái bẫy: file đã có, chỉ chưa nạp — KHÔNG phải "tải thêm file"."""
    add_file(session, company.id, slot="m15", status=DataFileStatus.PENDING)
    session.commit()

    r = period_readiness(session, company.id, 2024)
    assert slot_state(r, "m15") == SLOT_NOT_PARSED


def test_state_three_a_file_that_failed_to_parse(session, company):
    add_file(
        session, company.id, slot="m15", status=DataFileStatus.ERROR,
        message="Nạp được 0 dòng — kiểm tra lại cấu trúc file.",
    )
    session.commit()

    r = period_readiness(session, company.id, 2024)
    assert slot_state(r, "m15") == SLOT_PARSE_ERROR


def test_state_four_analyzed_with_a_column_still_to_confirm(session, company):
    """Lượt nạp dừng ở cổng xác nhận cột: file đã đăng ký, đã đọc, ghi 0 dòng."""
    add_file(
        session, company.id, slot="m15", status=DataFileStatus.ANALYZED,
        needs_review=True,
    )
    session.commit()

    r = period_readiness(session, company.id, 2024)
    assert slot_state(r, "m15") == SLOT_NEEDS_COLUMN_REVIEW


def test_state_five_a_settlement_file_without_a_book(session, company):
    """Gán sổ là tất-cả-hoặc-không: file này có nhãn sổ, file kia chưa."""
    add_file(session, company.id, slot="m15", status=DataFileStatus.PENDING, book="EPE")
    add_file(session, company.id, slot="m16", status=DataFileStatus.PENDING)
    session.commit()

    r = period_readiness(session, company.id, 2024)
    assert slot_state(r, "m16") == SLOT_NEEDS_BOOK


def test_state_six_rows_present_and_every_file_read(session, company):
    add_file(session, company.id, slot="m15", status=DataFileStatus.OK)
    add_nvl(session, company.id, material_code="A", imported=10, closing=10)
    session.commit()

    r = period_readiness(session, company.id, 2024)
    assert slot_state(r, "m15") == SLOT_READY


def test_state_seven_rows_left_behind_by_a_deleted_file(session, company):
    """Xoá file KHÔNG xoá dòng — đo theo dòng một mình thì vẫn báo "đủ"."""
    add_nvl(session, company.id, material_code="A", imported=10, closing=10)
    session.commit()

    r = period_readiness(session, company.id, 2024)
    assert slot_state(r, "m15") == SLOT_STALE


def test_states_four_and_five_are_told_apart_by_columns_and_book(session, company):
    """Cùng `analyzed`/`pending` — phân biệt bằng cột vướng và tình trạng sổ."""
    add_file(
        session, company.id, slot="m15", status=DataFileStatus.ANALYZED,
        book="EPE", needs_review=True,
    )
    add_file(session, company.id, slot="m16", status=DataFileStatus.ANALYZED)
    session.commit()

    r = period_readiness(session, company.id, 2024)
    # Cột vướng thắng: spec mục 3 trạng thái 5 là "không vướng cột, nhưng chưa gán sổ".
    assert slot_state(r, "m15") == SLOT_NEEDS_COLUMN_REVIEW
    assert slot_state(r, "m16") == SLOT_NEEDS_COLUMN_REVIEW


def test_a_new_file_uploaded_after_the_last_ingest_makes_the_rows_stale(session, company):
    add_file(session, company.id, slot="m15", status=DataFileStatus.OK)
    add_file(
        session, company.id, slot="m15", status=DataFileStatus.PENDING, name="them.xlsx",
    )
    add_nvl(session, company.id, material_code="A", imported=10, closing=10)
    session.commit()

    r = period_readiness(session, company.id, 2024)
    assert slot_state(r, "m15") == SLOT_STALE


# --- Dấu hiệu cũ là trục riêng, không gộp vào phép đếm --------------------------


def test_deleting_a_file_keeps_the_count_and_only_flips_the_stale_axis(session, company):
    """Sau khi xoá file, "đủ dữ liệu" VẪN ĐÚNG — việc cần làm là nạp lại."""
    f = add_file(session, company.id, slot="m15", status=DataFileStatus.OK)
    add_nvl(session, company.id, material_code="A", imported=10, closing=10)
    session.commit()

    before = period_readiness(session, company.id, 2024)
    assert before.stale is False

    session.delete(f)
    session.commit()
    after = period_readiness(session, company.id, 2024)

    assert after.sufficient_count == before.sufficient_count
    assert after.total_count == before.total_count
    assert after.stale is True


def test_the_stale_axis_never_appears_as_a_remedy_class(session, company):
    add_nvl(session, company.id, material_code="A", imported=10, closing=10)
    session.commit()

    r = period_readiness(session, company.id, 2024)
    assert r.stale is True
    assert all(
        b.remedy in (None, REMEDY_NEED_FILE_THIS_PERIOD,
                     REMEDY_NEED_OTHER_PERIOD_OR_CONFIRMATION)
        for b in r.blockers
    )


# --- Mẫu số: không rút, kể cả mã không dự đoán được ----------------------------


def test_the_registry_and_the_dispatch_table_declare_the_same_codes():
    """Mẫu số dựng từ cùng tập mã `run_checks` chạy — hai bảng phải khớp."""
    assert set(SPECS) == set(ALL_CHECKS)


def test_the_denominator_is_every_applicable_check(session, company):
    r = period_readiness(session, company.id, 2024)
    assert r.total_count == len(ALL_CHECKS)
    assert {c.code for c in r.checks} == set(ALL_CHECKS)


def test_a_published_dynamic_check_stays_in_the_denominator_as_run_to_know(session, company):
    session.add(CheckDefinition(
        code="X.1", kind="sql", title="Mở rộng", description="", spec={},
        sql_snippet="SELECT 1", status=CheckStatus.PUBLISHED,
    ))
    session.commit()

    r = period_readiness(session, company.id, 2024)
    predicted = {c.code: c for c in r.checks}
    assert r.total_count == len(ALL_CHECKS) + 1
    assert predicted["X.1"].status == CHECK_RUN_TO_KNOW
    assert predicted["X.1"].remedy is None


def test_an_unpublished_dynamic_check_is_not_in_the_denominator(session, company):
    session.add(CheckDefinition(
        code="X.9", kind="sql", title="Nháp", description="", spec={},
        sql_snippet="SELECT 1", status=CheckStatus.DRAFT,
    ))
    session.commit()

    r = period_readiness(session, company.id, 2024)
    assert "X.9" not in {c.code for c in r.checks}


def test_class_three_counts_as_data_sufficient(session, company):
    """"Chưa từng khai định mức" là kết luận về DN — không phải lỗ hổng dữ liệu."""
    add_norm(session, company.id, product_code="TP", material_code="X", norm_qty=2.0,
             year=2024)
    add_sp(session, company.id, product_code="TP", intake=100, year=2024)
    add_nvl(session, company.id, material_code="X", production_out=100, year=2024)
    add_sp(session, company.id, product_code="MOI", intake=50, year=2025)
    add_nvl(session, company.id, material_code="X", production_out=50, year=2025)
    add_norm(session, company.id, product_code="TP", material_code="X", norm_qty=2.0,
             year=2025)
    session.commit()

    r = period_readiness(session, company.id, 2025)
    c43 = next(c for c in r.checks if c.code == "C4.3")
    assert c43.remedy == REMEDY_NOTHING_TO_LOAD
    assert c43.status == CHECK_CONCLUSION
    assert c43.data_sufficient is True
    assert "C4.3" not in {code for b in r.blockers for code in b.check_codes}


# --- Ba cổng mà `requires` không diễn đạt được ---------------------------------


def test_the_or_gate_of_c3_3_is_predicted(session, company):
    """C3.3 khai cần m15; vế đối chiếu là "BCCT HOẶC M16" — `requires` chịu."""
    add_nvl(session, company.id, material_code="A", unit="KG", imported=1, closing=1)
    session.commit()

    r = period_readiness(session, company.id, 2024)
    c33 = next(c for c in r.checks if c.code == "C3.3")
    assert c33.data_sufficient is False
    assert c33.remedy == REMEDY_NEED_FILE_THIS_PERIOD
    assert c33.target == RemedyTarget(TARGET_DOCUMENT, "bcct")


def test_the_or_gate_of_c3_3_clears_when_either_side_is_present(session, company):
    add_nvl(session, company.id, material_code="A", unit="KG", imported=1, closing=1)
    add_norm(session, company.id, product_code="TP", material_code="A", norm_qty=1.0,
             material_unit="KG")
    session.commit()

    r = period_readiness(session, company.id, 2024)
    c33 = next(c for c in r.checks if c.code == "C3.3")
    assert c33.status == CHECK_READY


def test_the_previous_period_gate_of_c6_1_is_predicted(session, company):
    add_nvl(session, company.id, material_code="A", opening=100, closing=100, year=2024)
    session.commit()

    r = period_readiness(session, company.id, 2024)
    c61 = next(c for c in r.checks if c.code == "C6.1")
    assert c61.remedy == REMEDY_NEED_OTHER_PERIOD_OR_CONFIRMATION
    assert c61.target == RemedyTarget(TARGET_PERIOD, 2023)


def test_the_norm_gate_boundary_branch_is_predicted(session, company):
    add_norm(session, company.id, product_code="TP", material_code="X", norm_qty=2.0)
    add_sp(session, company.id, product_code="TP", intake=100)
    add_nvl(session, company.id, material_code="X", production_out=100)
    session.commit()

    r = period_readiness(session, company.id, 2024)
    c43 = next(c for c in r.checks if c.code == "C4.3")
    assert c43.remedy == REMEDY_NEED_OTHER_PERIOD_OR_CONFIRMATION
    assert c43.target == RemedyTarget("company-field", "first_bcqt_year")


def test_the_norm_gate_coverage_branch_points_at_the_earliest_empty_period(session, company):
    """Còn kỳ trước chưa có dòng định mức thì cách gỡ là nạp Mẫu 16 của kỳ đó."""
    company.first_bcqt_year = 2024
    add_norm(session, company.id, product_code="TP", material_code="X", norm_qty=2.0,
             year=2024)
    add_sp(session, company.id, product_code="TP", intake=100, year=2024)
    add_nvl(session, company.id, material_code="X", production_out=100, year=2024)
    # Kỳ 2026: 2025 nằm trong khoảng dữ liệu mà chưa có dòng định mức nào.
    add_norm(session, company.id, product_code="TP", material_code="X", norm_qty=2.0,
             year=2026)
    add_sp(session, company.id, product_code="MOI", intake=10, year=2026)
    add_nvl(session, company.id, material_code="X", production_out=10, year=2026)
    session.commit()

    r = period_readiness(session, company.id, 2026)
    c43 = next(c for c in r.checks if c.code == "C4.3")
    assert c43.remedy == REMEDY_NEED_OTHER_PERIOD_OR_CONFIRMATION
    assert c43.target == RemedyTarget(TARGET_PERIOD, 2025)


# --- Danh sách vướng mắc --------------------------------------------------------


def test_a_file_level_blocker_is_a_row_without_a_remedy_class(session, company):
    """Không thêm lớp thứ tư: vướng mắc mức file hiện thành dòng, không mang lớp."""
    add_file(session, company.id, slot="m15", status=DataFileStatus.PENDING)
    session.commit()

    r = period_readiness(session, company.id, 2024)
    file_blockers = [b for b in r.blockers if b.kind == BLOCKER_FILE]
    assert file_blockers
    assert all(b.remedy is None for b in file_blockers)


def test_a_check_blocked_by_a_file_level_problem_points_at_that_blocker(session, company):
    """Không nhắc lại "nạp thêm file kỳ này" cho file cán bộ vừa tải lên."""
    add_file(session, company.id, slot="m15", status=DataFileStatus.PENDING)
    session.commit()

    r = period_readiness(session, company.id, 2024)
    blocker = next(b for b in r.blockers if b.kind == BLOCKER_FILE and b.slot == "m15")
    assert "C2.1" in blocker.check_codes
    # Và KHÔNG có dòng lớp 1 riêng đòi tải thêm file Mẫu 15.
    assert not [
        b for b in r.blockers
        if b.kind == BLOCKER_CHECK
        and b.target == RemedyTarget(TARGET_DOCUMENT, "m15")
    ]


def test_a_missing_document_with_no_file_record_stays_a_class_one_blocker(session, company):
    add_nvl(session, company.id, material_code="A", imported=10, closing=10)
    session.commit()

    r = period_readiness(session, company.id, 2024)
    blocker = next(
        b for b in r.blockers
        if b.kind == BLOCKER_CHECK and b.target == RemedyTarget(TARGET_DOCUMENT, "bcct")
    )
    assert blocker.remedy == REMEDY_NEED_FILE_THIS_PERIOD
    assert "C1.1" in blocker.check_codes


def test_a_file_read_with_no_row_landing_in_the_period_does_not_ask_for_another_file(
    session, company
):
    """Mọi dòng rơi ngoài cửa sổ kỳ: file đã đọc xong, đừng bảo cán bộ tải thêm."""
    from datetime import date

    session.add(CompanyPeriod(
        company_id=company.id, period_year=2024,
        period_from=date(2024, 1, 1), period_to=date(2024, 12, 31),
    ))
    add_file(session, company.id, slot="bcct", status=DataFileStatus.OK)
    add_decl(session, company.id, declaration_no="1", customs_code="E31", item_code="A",
             quantity=10, year=2024, declaration_date=date(2023, 3, 5))
    session.commit()

    r = period_readiness(session, company.id, 2024)
    assert slot_state(r, "bcct") == SLOT_NOT_PARSED
    blocker = next(b for b in r.blockers if b.kind == BLOCKER_FILE and b.slot == "bcct")
    assert "chưa nạp lần nào" not in blocker.message
    assert "C1.1" in blocker.check_codes
    assert not [
        b for b in r.blockers
        if b.kind == BLOCKER_CHECK and b.target == RemedyTarget(TARGET_DOCUMENT, "bcct")
    ]


def test_declaration_gaps_out_of_window_rows_and_overlaps_become_blocker_items(
    session, company
):
    """Ba khối cảnh báo riêng trở thành mục trong danh sách vướng mắc."""
    from datetime import date

    session.add(CompanyPeriod(
        company_id=company.id, period_year=2024,
        period_from=date(2024, 1, 1), period_to=date(2024, 12, 31),
    ))
    session.add(CompanyPeriod(
        company_id=company.id, period_year=2025,
        period_from=date(2024, 7, 1), period_to=date(2025, 6, 30),
    ))
    add_decl(session, company.id, declaration_no="1", customs_code="E31", item_code="A",
             quantity=10, year=2024, declaration_date=date(2024, 3, 5))
    add_decl(session, company.id, declaration_no="2", customs_code="E31", item_code="A",
             quantity=10, year=2024, declaration_date=date(2023, 3, 5))
    session.commit()

    r = period_readiness(session, company.id, 2024)
    coverage = [b for b in r.blockers if b.kind == BLOCKER_COVERAGE]
    keys = {b.key for b in coverage}
    assert any(k.startswith("coverage:gap") for k in keys)
    assert "coverage:out-of-window" in keys
    assert "coverage:overlap" in keys
    assert all(b.remedy is None for b in coverage)


# --- Ràng buộc phiên DB ---------------------------------------------------------


def test_the_function_never_opens_a_session_of_its_own(session, company, monkeypatch):
    """Mở phiên bên trong là đọc trúng DB dev của máy (spec — seam 2)."""
    import app.database as dbmod
    import app.pipeline.readiness as readiness_mod

    assert not hasattr(readiness_mod, "SessionLocal")

    def _explode(*args, **kwargs):
        raise AssertionError("period_readiness đã tự mở phiên DB")

    monkeypatch.setattr(dbmod, "SessionLocal", _explode)
    add_nvl(session, company.id, material_code="A", imported=10, closing=10)
    session.commit()
    period_readiness(session, company.id, 2024)


def test_the_prediction_does_not_read_the_stored_run(session, company):
    """Màn dữ liệu tính trực tiếp từ DB, không cần lần chạy nào (ADR #24 mục 2)."""
    add_nvl(session, company.id, material_code="A", imported=10, closing=10)
    session.commit()

    before = period_readiness(session, company.id, 2024)
    run_checks(company.code, 2024, session=session)
    after = period_readiness(session, company.id, 2024)

    assert [(c.code, c.status, c.remedy) for c in before.checks] == [
        (c.code, c.status, c.remedy) for c in after.checks
    ]


# --- Test giá trị cao nhất: dự đoán PHẢI bằng trạng thái đã lưu ------------------


def _scenario_missing_sources(session, company) -> int:
    """Chỉ có tờ khai — cổng thiếu nguồn ở bộ điều phối (lớp 1)."""
    add_decl(session, company.id, declaration_no="1", customs_code="E31", item_code="A",
             quantity=100, year=2025)
    return 2025


def _scenario_or_gate(session, company) -> int:
    """Có Mẫu 15, không có tờ khai lẫn Mẫu 16 — cổng HOẶC của C3.3."""
    add_nvl(session, company.id, material_code="A", unit="KG", imported=10, closing=10,
            year=2025)
    return 2025


def _scenario_previous_period(session, company) -> int:
    """Có Mẫu 15 kỳ này, chưa có kỳ trước — cổng liên kỳ của C6.1."""
    add_nvl(session, company.id, material_code="A", unit="KG", opening=5, imported=10,
            closing=15, year=2025)
    add_norm(session, company.id, product_code="TP", material_code="A", norm_qty=1.0,
             material_unit="KG", year=2025)
    return 2025


def _scenario_norm_boundary(session, company) -> int:
    """Kỳ sớm nhất, chưa xác nhận năm đầu nộp BCQT — nhánh kỳ biên của cổng ĐM."""
    add_nvl(session, company.id, material_code="X", production_out=100, closing=0,
            year=2024)
    add_sp(session, company.id, product_code="TP", intake=100, closing=100, year=2024)
    add_norm(session, company.id, product_code="TP", material_code="X", norm_qty=2.0,
             year=2024)
    return 2024


def _scenario_norm_coverage_class_three(session, company) -> int:
    """Hết kỳ trống để nạp — nhánh độ phủ ra lớp 3 (kết luận về DN)."""
    company.first_bcqt_year = 2024
    add_nvl(session, company.id, material_code="X", production_out=100, closing=0,
            year=2024)
    add_sp(session, company.id, product_code="TP", intake=100, closing=100, year=2024)
    add_norm(session, company.id, product_code="TP", material_code="X", norm_qty=2.0,
             year=2024)
    add_nvl(session, company.id, material_code="X", production_out=50, closing=0,
            year=2025)
    add_sp(session, company.id, product_code="MOI", intake=50, closing=50, year=2025)
    add_norm(session, company.id, product_code="TP", material_code="X", norm_qty=2.0,
             year=2025)
    return 2025


def _scenario_norm_coverage_class_two(session, company) -> int:
    """Còn kỳ trước chưa có dòng định mức — nhánh độ phủ ra lớp 2."""
    company.first_bcqt_year = 2024
    add_nvl(session, company.id, material_code="X", production_out=100, closing=0,
            year=2024)
    add_sp(session, company.id, product_code="TP", intake=100, closing=100, year=2024)
    add_norm(session, company.id, product_code="TP", material_code="X", norm_qty=2.0,
             year=2024)
    add_nvl(session, company.id, material_code="X", production_out=50, closing=0,
            year=2026)
    add_sp(session, company.id, product_code="MOI", intake=50, closing=50, year=2026)
    add_norm(session, company.id, product_code="TP", material_code="X", norm_qty=2.0,
             year=2026)
    return 2026


def _scenario_everything_present(session, company) -> int:
    """Đủ bốn nguồn, có kỳ trước, định mức phủ hết — không cổng nào chặn."""
    company.first_bcqt_year = 2024
    for year in (2024, 2025):
        add_nvl(session, company.id, material_code="X", unit="KG", opening=0,
                imported=100, production_out=100, closing=0, year=year)
        add_sp(session, company.id, product_code="TP", intake=50, export_qty=50,
               closing=0, year=year)
        add_norm(session, company.id, product_code="TP", material_code="X",
                 norm_qty=2.0, material_unit="KG", year=year)
        add_decl(session, company.id, declaration_no=f"NK{year}", customs_code="E31",
                 item_code="X", quantity=100, unit="KG", year=year)
    return 2025


_SCENARIOS = {
    "thiếu nguồn": _scenario_missing_sources,
    "cổng HOẶC C3.3": _scenario_or_gate,
    "cổng kỳ trước C6.1": _scenario_previous_period,
    "cổng ĐM kỳ biên": _scenario_norm_boundary,
    "cổng ĐM lớp 3": _scenario_norm_coverage_class_three,
    "cổng ĐM lớp 2": _scenario_norm_coverage_class_two,
    "đủ dữ liệu": _scenario_everything_present,
}


def _run_and_compare(session, company, build) -> tuple[dict, dict]:
    year = build(session, company)
    session.commit()

    run_checks(company.code, year, session=session)
    stored = {
        r.check_code: (r.status, r.remedy, r.status_reason)
        for r in session.scalars(
            select(CheckRun).where(
                CheckRun.company_id == company.id, CheckRun.period_year == year
            )
        ).all()
    }
    predicted = {
        c.code: c
        for c in period_readiness(session, company.id, year).checks
    }
    return predicted, stored


def test_the_predicted_class_equals_the_class_the_run_persists(session, company):
    """Bảng điều khiển tính TRƯỚC khi chạy; lớp đã lưu sinh LÚC chạy — phải bằng nhau.

    Lệch thì hoặc dự đoán sai, hoặc bảng điều khiển phải nói rõ nó không dự đoán
    được mã đó ("biết khi chạy"), chứ không được im lặng cho qua.
    """
    from app.models import Company

    seen: set[tuple[str, str]] = set()
    for i, (name, build) in enumerate(_SCENARIOS.items()):
        # Mỗi kịch bản một DN riêng để dữ liệu kỳ trước của kịch bản này không lọt
        # sang kịch bản kia.
        dn = Company(code=f"DN_KB_{i}", tax_id=None, name=name)
        session.add(dn)
        session.commit()

        predicted, stored = _run_and_compare(session, dn, build)

        assert set(predicted) >= set(stored), name
        for code, (status, remedy, reason) in stored.items():
            got = predicted[code]
            if got.status == CHECK_RUN_TO_KNOW:
                continue
            assert got.remedy == remedy, f"{name} · {code}"
            # Lớp 3 vẫn là `not_evaluable` ở bảng lần chạy nhưng tính là ĐỦ dữ liệu ở
            # màn dữ liệu — so ở mức "có chạy được không", không so `data_sufficient`.
            assert (got.status != CHECK_READY) == (status == "not_evaluable"), (
                f"{name} · {code}"
            )
            assert got.reason == reason, f"{name} · {code}"
            if remedy is not None:
                seen.add((code, remedy))

    # Bộ kịch bản phải thực sự chạm cả ba cổng và cả ba lớp — không thì phép so trên
    # xanh vì chưa ca nào lệch được.
    assert ("C3.3", REMEDY_NEED_FILE_THIS_PERIOD) in seen
    assert ("C6.1", REMEDY_NEED_OTHER_PERIOD_OR_CONFIRMATION) in seen
    assert ("C4.3", REMEDY_NEED_OTHER_PERIOD_OR_CONFIRMATION) in seen
    assert ("C4.3", REMEDY_NOTHING_TO_LOAD) in seen
    assert {remedy for _, remedy in seen} == {
        REMEDY_NEED_FILE_THIS_PERIOD,
        REMEDY_NEED_OTHER_PERIOD_OR_CONFIRMATION,
        REMEDY_NOTHING_TO_LOAD,
    }


def test_the_dynamic_check_is_the_only_thing_the_panel_declines_to_predict(session, company):
    """Mã không dự đoán được vẫn nằm trong mẫu số, gắn "biết khi chạy"."""
    session.add(CheckDefinition(
        code="X.1", kind="sql", title="Mở rộng", description="", spec={},
        sql_snippet=(
            "SELECT 'critical' AS severity, material_code AS subject_key, "
            "'x' AS title, '' AS detail FROM nvl_balances "
            "WHERE company_id = :company_id AND period_year = :period_year"
        ),
        subject_table="nvl_balances", subject_col="material_code", scope="nvl",
        status=CheckStatus.PUBLISHED,
    ))
    add_nvl(session, company.id, material_code="A", imported=10, closing=10, year=2024)
    session.commit()
    run_checks(company.code, 2024, session=session)

    r = period_readiness(session, company.id, 2024)
    undecided = [c.code for c in r.checks if c.status == CHECK_RUN_TO_KNOW]
    assert undecided == ["X.1"]
