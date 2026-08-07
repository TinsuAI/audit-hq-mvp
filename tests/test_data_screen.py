"""T6 (#86) — màn dữ liệu: một doanh nghiệp, mọi kỳ là dòng.

Test ở mức DỮ LIỆU: khẳng định trên thứ route đưa vào ngữ cảnh template, không dò
chuỗi tiếng Việt trong HTML. Một test dò chữ vẫn xanh sau khi màn hình đã đổi hết ý
nghĩa, nên nó thôi kiểm thứ nó khai là đang kiểm.

Ranh giới của vé: khung màn + dòng kỳ + phép đếm + danh sách vướng mắc. Phần mở
rộng dòng kỳ (số dòng theo loại, danh sách file thật) là #87 — test của nó nằm ở
`tests/test_period_files.py`; ô thả file là #88; phản hồi nạp tại chỗ là #89.
"""

from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.checks import ALL_CHECKS
from app.checks.not_evaluable import (
    REMEDY_NEED_FILE_THIS_PERIOD,
    REMEDY_NEED_OTHER_PERIOD_OR_CONFIRMATION,
    REMEDY_NOTHING_TO_LOAD,
)
from app.main import app
from app.models import (
    CheckDefinition,
    CheckStatus,
    Company,
    CompanyPeriod,
    CompanyYearScore,
    Finding,
)
from app.models.data_file import DataFileStatus
from app.pipeline.data_screen import (
    ACTION_CONFIRM_COMPANY_FIELD,
    ACTION_EDIT_WINDOW,
    ACTION_INGEST,
    ACTION_OPEN_FILE,
    ACTION_OPEN_FINDINGS,
    ACTION_OPEN_PERIOD,
    ACTION_UPLOAD,
    BLOCKER_CONCLUSION,
    GROUP_ORDER,
    build_data_screen,
)
from app.pipeline.file_page import file_page_url
from app.pipeline.readiness import BLOCKER_CHECK, BLOCKER_COVERAGE, BLOCKER_FILE, period_readiness
from tests.conftest import AppDb, add_decl, add_norm, add_nvl, add_sp
from tests.test_readiness import add_file


def _row(screen, year: int):
    return next(p for p in screen.periods if p.year == year)


def _items(row):
    return [item for group in row.groups for item in group.items]


def _counted_codes(row) -> set[str]:
    return {
        code
        for group in row.groups
        if group.counted
        for item in group.items
        for code in item.check_codes
    }


# --- Vật chứa: một DN, các kỳ là dòng, mới nhất trước ---------------------------


def test_every_period_is_a_row_newest_first(session, company):
    add_nvl(session, company.id, material_code="A", imported=1, closing=1, year=2023)
    add_nvl(session, company.id, material_code="A", imported=1, closing=1, year=2025)
    session.add(CompanyPeriod(company_id=company.id, period_year=2024))
    session.commit()

    screen = build_data_screen(session, company)
    assert [p.year for p in screen.periods] == [2025, 2024, 2023]


def test_a_company_with_nothing_yet_invites_adding_a_period(session, company):
    screen = build_data_screen(session, company)

    assert screen.periods == ()
    assert screen.invite is True
    assert screen.add_years, "phải gợi ý được kỳ để thêm, nếu không cán bộ mới bế tắc"


def test_adding_a_year_renders_it_as_an_empty_row(session, company):
    screen = build_data_screen(session, company, add=2026)

    assert [p.year for p in screen.periods] == [2026]
    assert screen.invite is False
    assert _row(screen, 2026).has_files is False


def test_a_year_outside_the_accepted_range_is_not_added(session, company):
    assert build_data_screen(session, company, add=1990).periods == ()


# --- "Đủ dữ liệu cho N/M kiểm tra" lấy từ #85, không tính lại -------------------


def test_the_count_is_the_readiness_count_not_a_second_computation(session, company):
    add_nvl(session, company.id, material_code="A", imported=10, closing=10, year=2024)
    session.commit()

    expected = period_readiness(session, company.id, 2024)
    row = _row(build_data_screen(session, company), 2024)

    assert row.sufficient_count == expected.sufficient_count
    assert row.total_count == expected.total_count
    assert row.total_count == len(ALL_CHECKS)


def test_a_check_that_cannot_be_predicted_stays_in_the_denominator(session, company):
    """Mẫu số không co lại: rút mã khó đoán là cách làm doanh nghiệp trông sạch hơn."""
    session.add(CheckDefinition(
        code="X.1", kind="sql", title="Mở rộng", description="", spec={},
        sql_snippet="SELECT 1", status=CheckStatus.PUBLISHED,
    ))
    add_nvl(session, company.id, material_code="A", imported=10, closing=10, year=2024)
    session.commit()

    row = _row(build_data_screen(session, company), 2024)
    assert row.total_count == len(ALL_CHECKS) + 1
    assert "X.1" in row.run_to_know_codes


def test_filling_every_source_clears_the_missing_document_blockers(session, company):
    add_nvl(session, company.id, material_code="A", imported=10, closing=10, year=2024)
    session.commit()
    partial = _row(build_data_screen(session, company), 2024)
    assert partial.ready is False
    assert [
        i for i in partial.group(REMEDY_NEED_FILE_THIS_PERIOD).items
        if i.kind == BLOCKER_CHECK
    ]

    add_sp(session, company.id, product_code="TP", intake=10, year=2024)
    add_norm(session, company.id, product_code="TP", material_code="A", norm_qty=1.0,
             year=2024)
    add_decl(session, company.id, declaration_no="1", customs_code="E31", item_code="A",
             quantity=10, year=2024)
    session.commit()

    row = _row(build_data_screen(session, company), 2024)
    assert row.sufficient_count > partial.sufficient_count
    assert not [
        i for i in row.group(REMEDY_NEED_FILE_THIS_PERIOD).items
        if i.kind == BLOCKER_CHECK
    ]


# --- Ba nhóm cách gỡ, mỗi mục kèm hành động đúng chỗ ----------------------------


def test_there_are_exactly_three_remedy_groups(session, company):
    add_nvl(session, company.id, material_code="A", imported=10, closing=10, year=2024)
    session.commit()

    row = _row(build_data_screen(session, company), 2024)
    assert tuple(g.remedy for g in row.groups) == GROUP_ORDER
    assert len(GROUP_ORDER) == 3


def test_class_one_items_carry_an_upload_action_for_this_period(session, company):
    add_nvl(session, company.id, material_code="A", imported=10, closing=10, year=2024)
    session.commit()

    row = _row(build_data_screen(session, company), 2024)
    group = row.group(REMEDY_NEED_FILE_THIS_PERIOD)
    assert group.counted is True

    item = next(i for i in group.items if i.slot == "bcct")
    assert item.kind == BLOCKER_CHECK
    assert item.action.kind == ACTION_UPLOAD
    assert item.action.slot == "bcct"
    assert item.action.url == "/companies/TEST_DN/documents/upload"
    assert item.action.year == 2024
    assert "C1.1" in item.check_codes


def test_class_two_period_target_opens_exactly_that_period(session, company):
    """Cách gỡ trỏ tới KỲ KHÁC — nút phải mở đúng kỳ đó, không phải kỳ đang xem."""
    add_nvl(session, company.id, material_code="A", opening=100, closing=100, year=2024)
    session.commit()

    row = _row(build_data_screen(session, company), 2024)
    group = row.group(REMEDY_NEED_OTHER_PERIOD_OR_CONFIRMATION)
    item = next(i for i in group.items if "C6.1" in i.check_codes)

    assert item.action.kind == ACTION_OPEN_PERIOD
    assert item.action.year == 2023
    # 2023 chưa có dòng nào nên chưa là dòng kỳ — đường dẫn phải tự thêm nó vào.
    assert item.action.url == "/companies/TEST_DN/documents?add=2023#ky-2023"


def test_class_two_period_target_that_already_has_a_row_just_anchors_to_it(session, company):
    add_nvl(session, company.id, material_code="A", opening=100, closing=100, year=2024)
    # 2023 đã là một dòng kỳ (có cửa sổ đã lưu) nhưng chưa có dòng Mẫu 15 nào.
    session.add(CompanyPeriod(company_id=company.id, period_year=2023))
    session.commit()

    row = _row(build_data_screen(session, company), 2024)
    item = next(
        i for i in row.group(REMEDY_NEED_OTHER_PERIOD_OR_CONFIRMATION).items
        if "C6.1" in i.check_codes
    )
    assert item.action.url == "#ky-2023"


def test_class_two_company_field_target_points_at_the_company_fields_block(session, company):
    """`first_bcqt_year` rỗng chặn kỳ sớm nhất — chỗ xác nhận phải ở ngay màn này."""
    add_norm(session, company.id, product_code="TP", material_code="X", norm_qty=2.0,
             year=2024)
    add_sp(session, company.id, product_code="TP", intake=100, year=2024)
    add_nvl(session, company.id, material_code="X", production_out=100, year=2024)
    session.commit()

    screen = build_data_screen(session, company)
    item = next(
        i for i in _row(screen, 2024).group(REMEDY_NEED_OTHER_PERIOD_OR_CONFIRMATION).items
        if "C4.3" in i.check_codes
    )
    assert item.action.kind == ACTION_CONFIRM_COMPANY_FIELD
    assert item.action.url == f"#{screen.fields.anchor}"
    assert screen.fields.missing_first_bcqt_year is True


def test_class_three_is_not_counted_and_links_to_the_findings_screen(session, company):
    """"Chưa từng khai định mức" là phát hiện về DN — đừng để cán bộ đi tìm file."""
    add_norm(session, company.id, product_code="TP", material_code="X", norm_qty=2.0,
             year=2024)
    add_sp(session, company.id, product_code="TP", intake=100, year=2024)
    add_nvl(session, company.id, material_code="X", production_out=100, year=2024)
    add_sp(session, company.id, product_code="MOI", intake=50, year=2025)
    add_nvl(session, company.id, material_code="X", production_out=50, year=2025)
    add_norm(session, company.id, product_code="TP", material_code="X", norm_qty=2.0,
             year=2025)
    session.commit()

    row = _row(build_data_screen(session, company), 2025)
    group = row.group(REMEDY_NOTHING_TO_LOAD)

    assert group.counted is False
    item = next(i for i in group.items if "C4.3" in i.check_codes)
    assert item.kind == BLOCKER_CONCLUSION
    assert item.action.kind == ACTION_OPEN_FINDINGS
    assert item.action.url == "/companies/TEST_DN?year=2025"
    assert "C4.3" not in _counted_codes(row)


# --- Vướng mắc mức file: không thêm lớp thứ tư, nhưng nói đúng động từ ----------


def test_a_registered_file_never_read_asks_to_ingest_not_to_upload(session, company):
    """Bẫy chính: bảo cán bộ tải lên thứ họ vừa tải."""
    add_file(session, company.id, slot="m15", status=DataFileStatus.PENDING)
    session.commit()

    row = _row(build_data_screen(session, company), 2024)
    item = next(i for i in _items(row) if i.kind == BLOCKER_FILE and i.slot == "m15")

    assert item.action.kind == ACTION_INGEST
    assert item.action.url == "/companies/TEST_DN/documents/ingest"
    assert item.action.year == 2024
    # Nằm trong nhóm 1 (việc gỡ ở chính kỳ này) nhưng KHÔNG mang lớp cách gỡ riêng.
    assert row.group(REMEDY_NEED_FILE_THIS_PERIOD).items.count(item) == 1
    assert item.remedy is None


def test_a_file_that_will_not_read_points_at_that_file(session, company):
    """Lối vào chọn trang tính phải còn — không có nó thì file bế tắc."""
    f = add_file(session, company.id, slot="m15", status=DataFileStatus.ERROR,
                 message="Nạp được 0 dòng.")
    session.commit()

    row = _row(build_data_screen(session, company), 2024)
    item = next(i for i in _items(row) if i.kind == BLOCKER_FILE and i.slot == "m15")

    assert item.action.kind == ACTION_OPEN_FILE
    assert item.action.url == file_page_url("TEST_DN", f.id)


def test_a_column_still_to_confirm_points_at_the_file_that_holds_it(session, company):
    f = add_file(session, company.id, slot="m15", status=DataFileStatus.ANALYZED,
                 needs_review=True)
    session.commit()

    row = _row(build_data_screen(session, company), 2024)
    item = next(i for i in _items(row) if i.kind == BLOCKER_FILE and i.slot == "m15")

    assert item.action.kind == ACTION_OPEN_FILE
    assert item.action.url == file_page_url("TEST_DN", f.id)


def test_a_settlement_file_without_a_book_points_at_that_file(session, company):
    add_file(session, company.id, slot="m15", status=DataFileStatus.PENDING, book="EPE")
    f = add_file(session, company.id, slot="m16", status=DataFileStatus.PENDING)
    session.commit()

    row = _row(build_data_screen(session, company), 2024)
    item = next(i for i in _items(row) if i.kind == BLOCKER_FILE and i.slot == "m16")

    assert item.action.kind == ACTION_OPEN_FILE
    assert item.action.url == file_page_url("TEST_DN", f.id)


def test_no_group_outside_the_three_remedy_classes_is_created(session, company):
    add_file(session, company.id, slot="m15", status=DataFileStatus.ERROR)
    session.commit()

    row = _row(build_data_screen(session, company), 2024)
    assert tuple(g.remedy for g in row.groups) == GROUP_ORDER


# --- Ba khối cảnh báo cũ nay là mục trong danh sách vướng mắc -------------------


def test_the_three_old_warning_blocks_arrive_inside_the_blocker_list(session, company):
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
    add_decl(session, company.id, declaration_no="2", customs_code="E31", item_code="B",
             quantity=10, year=2024, declaration_date=date(2023, 3, 5))
    session.commit()

    row = _row(build_data_screen(session, company), 2024)
    keys = {i.key for i in _items(row)}

    assert "coverage:overlap" in keys
    assert any(k.startswith("coverage:gap:") for k in keys)
    assert "coverage:out-of-window" in keys
    assert all(
        i.kind == BLOCKER_COVERAGE
        for i in _items(row)
        if i.key.startswith("coverage:")
    )


def test_an_overlapping_window_is_fixed_by_editing_the_window(session, company):
    session.add(CompanyPeriod(
        company_id=company.id, period_year=2024,
        period_from=date(2024, 1, 1), period_to=date(2024, 12, 31),
    ))
    session.add(CompanyPeriod(
        company_id=company.id, period_year=2025,
        period_from=date(2024, 7, 1), period_to=date(2025, 6, 30),
    ))
    session.commit()

    row = _row(build_data_screen(session, company), 2024)
    item = next(i for i in _items(row) if i.key == "coverage:overlap")
    assert item.action.kind == ACTION_EDIT_WINDOW


def test_a_missing_declaration_range_is_fixed_by_uploading_here(session, company):
    session.add(CompanyPeriod(
        company_id=company.id, period_year=2025,
        period_from=date(2025, 1, 1), period_to=date(2025, 12, 31),
    ))
    add_decl(session, company.id, declaration_no="1", customs_code="E31", item_code="A",
             quantity=10, year=2025, declaration_date=date(2025, 4, 5))
    session.commit()

    row = _row(build_data_screen(session, company), 2025)
    item = next(i for i in _items(row) if i.key.startswith("coverage:gap:"))
    assert item.action.kind == ACTION_UPLOAD
    assert item.action.slot == "bcct"


# --- Cửa sổ kỳ: hiện CHỈ KHI khác năm dương lịch, sửa được tại chỗ --------------


def test_the_window_shows_only_when_it_is_not_the_calendar_year(session, company):
    add_nvl(session, company.id, material_code="A", imported=1, closing=1, year=2024)
    add_nvl(session, company.id, material_code="A", imported=1, closing=1, year=2025)
    session.add(CompanyPeriod(
        company_id=company.id, period_year=2025,
        period_from=date(2025, 4, 1), period_to=date(2026, 3, 31), is_manual=True,
    ))
    session.commit()

    screen = build_data_screen(session, company)
    assert _row(screen, 2024).window_custom is False

    r25 = _row(screen, 2025)
    assert r25.window_custom is True
    assert (r25.window_from, r25.window_to) == (date(2025, 4, 1), date(2026, 3, 31))
    assert r25.window_manual is True
    assert r25.window_url == "/companies/TEST_DN/documents/period"


def test_the_window_shown_is_the_one_the_checks_read(session, company):
    """Niên độ DN khác dương lịch: màn hình và kiểm tra phải cùng một cửa sổ."""
    from app.checks.scope import effective_window

    company.fiscal_start_month = 4
    add_nvl(session, company.id, material_code="A", imported=1, closing=1, year=2025)
    session.commit()

    row = _row(build_data_screen(session, company), 2025)
    assert (row.window_from, row.window_to) == effective_window(session, company.id, 2025)
    assert row.window_custom is True


# --- Dấu hiệu cũ là trục riêng --------------------------------------------------


def test_stale_rows_are_a_separate_axis_from_the_count(session, company):
    """Xoá file xong "đủ dữ liệu" vẫn đúng — việc cần làm là nạp lại, không phải tải."""
    add_nvl(session, company.id, material_code="A", imported=10, closing=10, year=2024)
    session.commit()

    row = _row(build_data_screen(session, company), 2024)
    assert row.stale is True
    assert row.sufficient_count == period_readiness(
        session, company.id, 2024
    ).sufficient_count


# --- Đường sang màn phát hiện ---------------------------------------------------


def test_every_period_row_links_into_the_findings_screen_for_its_own_year(session, company):
    add_nvl(session, company.id, material_code="A", imported=1, closing=1, year=2024)
    session.commit()

    row = _row(build_data_screen(session, company), 2024)
    assert row.findings_url == "/companies/TEST_DN?year=2024"
    assert row.checks_run is False


def test_checks_run_flips_once_the_period_has_a_score(session, company):
    add_nvl(session, company.id, material_code="A", imported=1, closing=1, year=2024)
    session.add(CompanyYearScore(company_id=company.id, period_year=2024, score=120,
                                 tier="cao"))
    session.commit()

    row = _row(build_data_screen(session, company), 2024)
    assert row.checks_run is True
    assert row.score == 120


def test_a_year_with_findings_but_no_score_row_does_not_carry_a_score(session, company):
    """`tier_css_for(None)` nổ — dòng kỳ phải nói rõ chưa có điểm thay vì dựng nhãn."""
    session.add(Finding(
        company_id=company.id, period_year=2024, check_code="C1.2", severity="critical",
        subject_type="material_code", subject_key="A", title="x",
    ))
    session.commit()

    row = _row(build_data_screen(session, company), 2024)
    assert row.checks_run is True
    assert row.score is None


# --- Thuộc tính mức doanh nghiệp -------------------------------------------------


def test_company_level_fields_sit_on_this_screen(session, company):
    company.first_bcqt_year = 2019
    company.fiscal_start_month = 4
    company.audit_decision_date = date(2026, 3, 2)
    session.commit()

    fields = build_data_screen(session, company).fields
    assert fields.first_bcqt_year == 2019
    assert fields.fiscal_start_month == 4
    assert fields.audit_decision_date == date(2026, 3, 2)
    assert fields.missing_first_bcqt_year is False
    assert fields.url == "/companies/TEST_DN/documents/company"


# --- Route ----------------------------------------------------------------------


def _client(app_db: AppDb, **company_kwargs) -> TestClient:
    with app_db.SessionLocal() as db:
        db.add(Company(code="DN_T6", name="Màn dữ liệu", tax_id="1", **company_kwargs))
        db.commit()
    client = TestClient(app)
    client.post("/login", data={"user": "admin", "password": "admin"},
                follow_redirects=False)
    return client


def _company(app_db: AppDb, db) -> Company:
    return db.scalar(select(Company).where(Company.code == "DN_T6"))


def test_the_screen_renders_for_a_company_with_nothing_yet(app_db: AppDb):
    client = _client(app_db)
    r = client.get("/companies/DN_T6/documents")
    assert r.status_code == 200


def test_the_screen_renders_for_a_year_with_findings_but_no_score_row(app_db: AppDb):
    client = _client(app_db)
    with app_db.SessionLocal() as db:
        c = _company(app_db, db)
        db.add(Finding(
            company_id=c.id, period_year=2025, check_code="C1.2", severity="critical",
            subject_type="material_code", subject_key="A", title="x",
        ))
        db.commit()

    assert client.get("/companies/DN_T6/documents").status_code == 200


def test_confirming_the_first_bcqt_year_in_place_leaves_the_name_alone(app_db: AppDb):
    """Chỗ sửa nằm trong luồng nạp, nhưng KHÔNG được mượn form sửa DN đầy đủ: form
    đó lấy tên rỗng làm tên mới và ghi đè tên doanh nghiệp."""
    client = _client(app_db)
    with app_db.SessionLocal() as db:
        before = _company(app_db, db).name

    r = client.post(
        "/companies/DN_T6/documents/company",
        data={"first_bcqt_year": "2019", "fiscal_start_month": "4",
              "audit_decision_date": "2026-03-02"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"].startswith("/companies/DN_T6/documents")

    with app_db.SessionLocal() as db:
        c = _company(app_db, db)
        assert c.first_bcqt_year == 2019
        assert c.fiscal_start_month == 4
        assert c.audit_decision_date == date(2026, 3, 2)
        assert c.name == before


def test_clearing_the_first_bcqt_year_means_unknown_not_zero(app_db: AppDb):
    client = _client(app_db, first_bcqt_year=2019)
    client.post(
        "/companies/DN_T6/documents/company",
        data={"first_bcqt_year": "", "fiscal_start_month": "1"},
        follow_redirects=False,
    )
    with app_db.SessionLocal() as db:
        assert _company(app_db, db).first_bcqt_year is None


def test_an_out_of_range_first_bcqt_year_is_rejected_without_overwriting(app_db: AppDb):
    client = _client(app_db, first_bcqt_year=2019)
    r = client.post(
        "/companies/DN_T6/documents/company",
        data={"first_bcqt_year": "1899", "fiscal_start_month": "1"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "error" in r.headers["location"]
    with app_db.SessionLocal() as db:
        assert _company(app_db, db).first_bcqt_year == 2019


def test_an_invalid_decision_date_is_rejected_without_overwriting(app_db: AppDb):
    client = _client(app_db, audit_decision_date=date(2026, 3, 2))
    r = client.post(
        "/companies/DN_T6/documents/company",
        data={"first_bcqt_year": "", "fiscal_start_month": "1",
              "audit_decision_date": "02/03/2026"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "error" in r.headers["location"]
    with app_db.SessionLocal() as db:
        assert _company(app_db, db).audit_decision_date == date(2026, 3, 2)


def test_editing_company_fields_does_not_move_the_data_version(app_db: AppDb):
    """Niên độ và ngày quyết định là VIEW của kỳ đã lưu — không nạp lại gì."""
    client = _client(app_db)
    with app_db.SessionLocal() as db:
        c = _company(app_db, db)
        db.add(CompanyPeriod(company_id=c.id, period_year=2025, data_version=3))
        db.commit()

    client.post(
        "/companies/DN_T6/documents/company",
        data={"first_bcqt_year": "2019", "fiscal_start_month": "4"},
        follow_redirects=False,
    )
    with app_db.SessionLocal() as db:
        c = _company(app_db, db)
        row = db.scalar(
            select(CompanyPeriod).where(
                CompanyPeriod.company_id == c.id, CompanyPeriod.period_year == 2025
            )
        )
        assert row.data_version == 3
