"""Cổng trường vắng ở mức TRƯỜNG (#113, spec #116 story 14-16).

Sau lát 2 cán bộ ghi được "trường này không có trong file", nhưng check vẫn chạy trên
cột không tồn tại và trả 0 phát hiện — mà 0 phát hiện đọc như "sạch". Đúng lớp lỗi
`sources.py` đã diệt ở mức NGUỒN, còn nguyên ở mức TRƯỜNG.
"""

from __future__ import annotations

import json

from app.checks.not_evaluable import REMEDY_NEED_FILE_THIS_PERIOD, STATUS_NOT_EVALUABLE
from app.checks.registry import CHECK_COLUMNS, checks_reading
from app.checks.sources import (
    absent_fields_reason,
    blocking_absent_fields,
    classify_absent_fields,
)


def test_gate_uses_the_same_function_as_the_screen_warning():
    """Story 28: cảnh báo trên màn gán và hành vi lúc chạy suy từ MỘT nguồn.

    Nếu cổng tự dựng ánh xạ trường→check riêng thì hai bên trôi khỏi nhau, và cán bộ
    được cảnh báo một đằng còn hệ thống làm một nẻo.
    """
    absent = {"m15": {"material_code"}}
    blocked = {
        code for code in CHECK_COLUMNS
        if blocking_absent_fields(code, absent)
    }
    assert blocked == set(checks_reading("m15", "material_code"))


def test_a_field_no_check_reads_blocks_nothing():
    """Tiêu chí nghiệm thu: trường vắng mà KHÔNG check nào đọc → không đổi gì."""
    # `material_name` không có mục nào trong CHECK_COLUMNS.
    assert checks_reading("m15", "material_name") == []
    absent = {"m15": {"material_name"}}
    assert all(not blocking_absent_fields(code, absent) for code in CHECK_COLUMNS)


def test_blocked_set_is_exactly_checks_reading_no_more_no_less():
    """Cùng một (DN, kỳ), xác nhận vắng MỘT trường → đúng tập `checks_reading()`."""
    for slot, field in [("m16", "note"), ("bcct", "hs_code"), ("m15a", "product_code")]:
        expected = set(checks_reading(slot, field))
        blocked = {
            code for code in CHECK_COLUMNS
            if blocking_absent_fields(code, {slot: {field}})
        }
        assert blocked == expected, f"{slot}.{field}: {blocked} != {expected}"


def test_reason_names_the_exact_field_and_form():
    pairs = blocking_absent_fields("C4.1", {"m16": {"note"}})
    assert pairs == (("m16", "note"),)
    reason = absent_fields_reason(pairs)
    assert "Ghi chú" in reason          # nhãn tiếng Việt của trường
    assert "Mẫu 16" in reason           # nói rõ biểu nào để cán bộ mở đúng file
    remedy, target = classify_absent_fields(pairs)
    assert remedy == REMEDY_NEED_FILE_THIS_PERIOD
    assert target.value == "m16"


def test_note_absent_blocks_c4_1_because_it_scopes_the_check():
    """`m16.note` nuôi `is_domestic_origin`, thứ TRỪ nguyên liệu trong nước khỏi phạm
    vi C4.1. Vắng nó thì phạm vi sai mà không phát hiện nào lộ ra (#111 đã khai)."""
    assert "C4.1" in checks_reading("m16", "note")
    assert blocking_absent_fields("C4.1", {"m16": {"note"}})


# --- Khai bù bcct ------------------------------------------------------------


def test_bcct_now_has_entries_so_the_gate_can_speak_for_it():
    """Trước #113 registry có ĐÚNG 0 mục bcct → cổng câm cho biểu tờ khai."""
    codes = sorted({
        code for code, uses in CHECK_COLUMNS.items()
        if any(slot == "bcct" for slot, _, _ in uses)
    })
    assert codes == ["C1.1", "C1.2", "C1.3", "C1.4", "C1.6", "C3.1", "C3.2", "C3.3"]


def test_checks_that_do_not_read_declarations_are_not_declared():
    """C1.7 và C5.1 chỉ đọc `NvlBalance` — đo bằng đồ thị gọi, không theo danh sách vé.

    Khai bừa vào đây là dựng một cổng `not_evaluable` GIẢ: check vẫn kết luận được mà
    hệ thống bảo chưa đánh giá được.
    """
    for code in ("C1.7", "C5.1"):
        assert not any(slot == "bcct" for slot, _, _ in CHECK_COLUMNS.get(code, ()))


def test_declaration_date_gates_every_bcct_check():
    """`scope.py` dựng cửa sổ kỳ bằng `declaration_date`; thiếu nó thì KHÔNG dòng tờ
    khai nào vào phạm vi và mọi check bcct trả 0 phát hiện, đọc như "sạch"."""
    blocked = {
        code for code in CHECK_COLUMNS
        if blocking_absent_fields(code, {"bcct": {"declaration_date"}})
    }
    assert blocked == {"C1.1", "C1.2", "C1.3", "C1.4", "C1.6", "C3.1", "C3.2", "C3.3"}


def test_value_total_is_deliberately_not_declared():
    """C1.1 đọc `value_total` qua `valuation.py` để GẮN SỐ TIỀN vào phát hiện, nhưng
    thiếu nó thì C1.1 vẫn phát hiện đúng chênh lệch. Khai vào đây là cổng giả."""
    assert checks_reading("bcct", "value_total") == []


# --- Đi trọn đường: parse_detail → cổng → check_runs -------------------------


def test_absent_field_in_parse_detail_turns_the_check_not_evaluable(app_db):
    """Seed thẳng `parse_detail` (seam 3 theo spec #116), rồi chạy check thật."""
    from app.checks.sources import absent_fields_for_period
    from app.models import Company, DataFile, DataFileStatus

    db = app_db.SessionLocal()
    company = Company(code="DN_T113", name="T113")
    db.add(company)
    db.commit()

    db.add(DataFile(
        company_id=company.id, period_year=2025, slot="m16",
        original_filename="dm.xlsx", stored_path="DN_T113/2025/DINH_MUC/dm.xlsx",
        size_bytes=1, parse_status=DataFileStatus.OK,
        parse_detail=json.dumps({
            "form_signature": "sig", "column_map": {"material_code": 4},
            "absent_fields": ["note"],
        }),
    ))
    db.commit()

    absent = absent_fields_for_period(db, company.id, 2025)
    assert absent == {"m16": {"note"}}
    assert blocking_absent_fields("C4.1", absent) == (("m16", "note"),)
    # Trạng thái đi qua đúng đường `NotEvaluable` sẵn có, không nhánh thứ hai.
    remedy, _ = classify_absent_fields(blocking_absent_fields("C4.1", absent))
    assert remedy == REMEDY_NEED_FILE_THIS_PERIOD
    assert STATUS_NOT_EVALUABLE == "not_evaluable"


def test_a_period_with_no_absent_statement_gates_nothing(app_db):
    from app.checks.sources import absent_fields_for_period
    from app.models import Company, DataFile, DataFileStatus

    db = app_db.SessionLocal()
    company = Company(code="DN_T113B", name="T113B")
    db.add(company)
    db.commit()
    db.add(DataFile(
        company_id=company.id, period_year=2025, slot="m16",
        original_filename="dm.xlsx", stored_path="DN_T113B/2025/DINH_MUC/dm.xlsx",
        size_bytes=1, parse_status=DataFileStatus.OK,
        parse_detail=json.dumps({"form_signature": "sig", "column_map": {"note": 8}}),
    ))
    db.commit()

    assert absent_fields_for_period(db, company.id, 2025) == {}


# --- Đi qua `run_checks` thật -------------------------------------------------


def _seed_absent(session, company_id: int, slot: str, fields: list[str]) -> None:
    """Đóng dấu trường vắng vào `parse_detail` của một file thuộc (DN, kỳ 2025)."""
    from app.models import DataFile, DataFileStatus

    session.add(DataFile(
        company_id=company_id, period_year=2025, slot=slot,
        original_filename=f"{slot}.xlsx", stored_path=f"X/2025/{slot}.xlsx",
        size_bytes=1, parse_status=DataFileStatus.OK,
        parse_detail=json.dumps({
            "form_signature": "sig", "column_map": {}, "absent_fields": fields,
        }),
    ))


def test_run_checks_marks_exactly_the_checks_reading_the_absent_field(session, company):
    """Tiêu chí nghiệm thu chính: đúng tập `checks_reading()` chuyển `not_evaluable`,
    không hơn không kém — và các check khác giữ nguyên trạng thái."""
    from sqlalchemy import select as _select

    from app.models import CheckRun, Norm
    from app.pipeline.run_checks import run_checks
    from tests.conftest import add_decl, add_nvl, add_sp

    add_nvl(session, company.id, material_code="A", imported=100, closing=100, year=2025)
    add_sp(session, company.id, product_code="P", export_qty=10, closing=0, year=2025)
    session.add(Norm(company_id=company.id, period_year=2025, product_code="P",
                     material_code="A", norm_qty=1.0))
    add_decl(session, company.id, declaration_no="1", customs_code="E31",
             item_code="A", quantity=100, year=2025)
    # Cán bộ xác nhận tờ khai kỳ này KHÔNG có cột mã HS.
    _seed_absent(session, company.id, "bcct", ["hs_code"])
    session.commit()

    run_checks(company.code, 2025, session=session)
    runs = {
        r.check_code: r for r in
        session.scalars(_select(CheckRun).where(CheckRun.company_id == company.id)).all()
    }

    expected = set(checks_reading("bcct", "hs_code"))
    assert expected == {"C3.2"}
    blocked = {
        code for code, r in runs.items()
        if r.status == "not_evaluable" and "không có cột" in (r.status_reason or "")
    }
    assert blocked == expected

    # Nêu ĐÚNG trường nào, và mang lớp cách gỡ "nạp file của chính kỳ này".
    assert "Mã HS" in runs["C3.2"].status_reason
    assert runs["C3.2"].remedy == REMEDY_NEED_FILE_THIS_PERIOD
    assert runs["C3.2"].finding_count == 0
    # Check đọc tờ khai nhưng KHÔNG đọc mã HS vẫn chạy bình thường.
    assert runs["C3.1"].status == "ok"
    assert runs["C2.1"].status == "ok"


def test_absent_field_no_check_reads_changes_no_status(session, company):
    from sqlalchemy import select as _select

    from app.models import CheckRun
    from app.pipeline.run_checks import run_checks
    from tests.conftest import add_nvl

    add_nvl(session, company.id, material_code="A", imported=100, closing=100, year=2025)
    _seed_absent(session, company.id, "m15", ["material_name"])
    session.commit()

    run_checks(company.code, 2025, session=session)
    runs = session.scalars(
        _select(CheckRun).where(CheckRun.company_id == company.id)
    ).all()
    assert all("không có cột" not in (r.status_reason or "") for r in runs)
