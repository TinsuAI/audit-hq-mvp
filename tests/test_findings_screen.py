"""T (#97) — màn phát hiện đọc LỚP CÁCH GỠ ĐÃ LƯU của khối "Chưa đánh giá được".

Nửa sau của spec mục 2: "một phân loại, HAI NƠI ĐỌC". Màn dữ liệu tính lớp 1 và 2
trực tiếp từ DB; màn phát hiện đọc lớp đã lưu ở `check_runs.remedy`. Đích (kỳ nào ·
trường nào của DN · loại tài liệu nào) tính LẠI lúc hiển thị, không lưu — ADR #24
mục 2.

Test ở mức DỮ LIỆU: khẳng định trên thứ hàm dựng ngữ cảnh trả về, không dò chuỗi
tiếng Việt trong HTML. Một test dò chữ vẫn xanh sau khi màn hình đã đổi hết ý nghĩa.
"""

from __future__ import annotations

from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.checks.not_evaluable import (
    REMEDY_NEED_FILE_THIS_PERIOD,
    REMEDY_NEED_OTHER_PERIOD_OR_CONFIRMATION,
    REMEDY_NOTHING_TO_LOAD,
    STATUS_NOT_EVALUABLE,
    TARGET_COMPANY_FIELD,
    TARGET_DOCUMENT,
    TARGET_PERIOD,
    RemedyTarget,
    load_not_evaluable,
)
from app.main import app
from app.models import CheckRun, Company
from app.pipeline.findings_screen import (
    REMEDY_UNKNOWN,
    detail_check_for,
    not_evaluable_panel,
)
from tests.conftest import AppDb, add_norm, add_nvl, add_sp


def add_run(
    session,
    company_id: int,
    *,
    code: str,
    year: int = 2024,
    reason: str = "Thiếu đầu vào bắt buộc.",
    remedy: str | None = REMEDY_NEED_FILE_THIS_PERIOD,
    status: str = STATUS_NOT_EVALUABLE,
) -> CheckRun:
    row = CheckRun(
        company_id=company_id,
        period_year=year,
        check_code=code,
        ran_at=datetime(2026, 8, 7, 10, 0, 0),
        finding_count=0,
        status=status,
        status_reason=reason,
        remedy=remedy,
    )
    session.add(row)
    session.commit()
    return row


def _panel(session, company, year: int = 2024):
    return not_evaluable_panel(session, company, year)


def _items(groups):
    return [item for group in groups for item in group.items]


def _item(groups, code: str):
    return next(item for item in _items(groups) if item.code == code)


def _group_of(groups, code: str):
    return next(g for g in groups for item in g.items if item.code == code)


# --- `load_not_evaluable` trả CẢ lý do lẫn lớp ---------------------------------


def test_load_not_evaluable_carries_the_reason_and_the_stored_remedy_class(session, company):
    add_run(
        session, company.id, code="C4.3", reason="Chưa từng khai định mức.",
        remedy=REMEDY_NOTHING_TO_LOAD,
    )

    runs = load_not_evaluable(session, company.id, 2024)

    assert runs["C4.3"].reason == "Chưa từng khai định mức."
    assert runs["C4.3"].remedy == REMEDY_NOTHING_TO_LOAD


def test_load_not_evaluable_still_iterates_to_check_codes_for_scoring(session, company):
    """Điểm rủi ro chỉ cần TẬP MÃ — đổi kiểu giá trị không được phá hợp đồng đó."""
    add_run(session, company.id, code="C4.3")
    add_run(session, company.id, code="C6.1")

    assert set(load_not_evaluable(session, company.id, 2024)) == {"C4.3", "C6.1"}


def test_load_not_evaluable_keeps_a_row_written_before_the_migration(session, company):
    add_run(session, company.id, code="C4.3", remedy=None)

    runs = load_not_evaluable(session, company.id, 2024)

    assert runs["C4.3"].remedy is None
    assert runs["C4.3"].reason == "Thiếu đầu vào bắt buộc."


# --- Nhóm theo LỚP ĐÃ LƯU, không theo lớp tính lại -----------------------------


def test_the_panel_groups_by_the_stored_class_not_by_the_live_prediction(session, company):
    """Phép thử phân biệt: không có dòng Tầng 1 nào, nên lớp TÍNH LẠI của cả hai mã
    đều là lớp 1 (cổng thiếu nguồn). Lớp ĐÃ LƯU khác — nhóm phải theo lớp đã lưu.
    """
    add_run(session, company.id, code="C4.3", remedy=REMEDY_NOTHING_TO_LOAD)
    add_run(session, company.id, code="C6.1", remedy=REMEDY_NEED_OTHER_PERIOD_OR_CONFIRMATION)

    groups = _panel(session, company)

    assert _group_of(groups, "C4.3").remedy == REMEDY_NOTHING_TO_LOAD
    assert _group_of(groups, "C6.1").remedy == REMEDY_NEED_OTHER_PERIOD_OR_CONFIRMATION


def test_the_panel_is_grouped_not_one_flat_list(session, company):
    add_run(session, company.id, code="C1.1", remedy=REMEDY_NEED_FILE_THIS_PERIOD)
    add_run(session, company.id, code="C6.1", remedy=REMEDY_NEED_OTHER_PERIOD_OR_CONFIRMATION)
    add_run(session, company.id, code="C4.3", remedy=REMEDY_NOTHING_TO_LOAD)

    groups = _panel(session, company)

    assert [g.remedy for g in groups] == [
        REMEDY_NEED_FILE_THIS_PERIOD,
        REMEDY_NEED_OTHER_PERIOD_OR_CONFIRMATION,
        REMEDY_NOTHING_TO_LOAD,
    ]
    assert [len(g.items) for g in groups] == [1, 1, 1]


def test_only_non_empty_groups_appear(session, company):
    add_run(session, company.id, code="C1.1", remedy=REMEDY_NEED_FILE_THIS_PERIOD)

    assert [g.remedy for g in _panel(session, company)] == [REMEDY_NEED_FILE_THIS_PERIOD]


def test_no_not_evaluable_row_means_no_group(session, company):
    assert _panel(session, company) == ()


# --- Đích tính LẠI lúc hiển thị -------------------------------------------------


def test_a_class_two_item_points_at_the_period_its_recomputed_target_names(session, company):
    """C6.1 có M15 kỳ 2024 nhưng không có kỳ 2023 → đích tính lại là KỲ 2023."""
    add_nvl(session, company.id, material_code="NVL1", year=2024)
    add_run(session, company.id, code="C6.1", remedy=REMEDY_NEED_OTHER_PERIOD_OR_CONFIRMATION)

    item = _item(_panel(session, company), "C6.1")

    assert item.target == RemedyTarget(TARGET_PERIOD, 2023)
    assert item.url == f"/companies/{company.code}/documents?add=2023#ky-2023"


def test_a_class_two_item_pointing_at_a_company_field_opens_the_company_block(session, company):
    """C4.3 ở kỳ biên: đích là trường `first_bcqt_year`, không kỳ nào gỡ được."""
    add_nvl(session, company.id, material_code="NVL1", year=2024)
    add_sp(session, company.id, product_code="TP1", year=2024)
    add_norm(session, company.id, product_code="TP1", material_code="NVL1", norm_qty=1, year=2024)
    add_run(session, company.id, code="C4.3", remedy=REMEDY_NEED_OTHER_PERIOD_OR_CONFIRMATION)

    item = _item(_panel(session, company), "C4.3")

    assert item.target == RemedyTarget(TARGET_COMPANY_FIELD, "first_bcqt_year")
    assert item.url == f"/companies/{company.code}/documents#thuoc-tinh-doanh-nghiep"


def test_a_class_one_item_points_at_the_data_screen_of_this_period(session, company):
    add_run(session, company.id, code="C1.1", remedy=REMEDY_NEED_FILE_THIS_PERIOD)

    item = _item(_panel(session, company), "C1.1")

    assert item.target == RemedyTarget(TARGET_DOCUMENT, "bcct")
    assert item.url == f"/companies/{company.code}/documents?add=2024#ky-2024"


def test_a_class_one_item_still_links_when_the_target_cannot_be_recomputed(session, company):
    """Dữ liệu đã lên sau lần chạy → lớp tính lại không còn đích. Vẫn phải có đường
    dẫn sang màn dữ liệu đúng kỳ, nếu không lớp 1 mất nút gỡ."""
    add_nvl(session, company.id, material_code="NVL1", year=2024)
    add_nvl(session, company.id, material_code="NVL1", year=2023)
    add_run(session, company.id, code="C6.1", remedy=REMEDY_NEED_FILE_THIS_PERIOD)

    item = _item(_panel(session, company), "C6.1")

    assert item.target is None
    assert item.url == f"/companies/{company.code}/documents?add=2024#ky-2024"


def test_recomputing_the_target_writes_nothing(session, company):
    """Spec mục 2 chốt CHỈ LƯU LỚP. Không cột nào giữ đích, và dựng màn không ghi."""
    assert not [c for c in CheckRun.__table__.columns.keys() if "target" in c]
    add_nvl(session, company.id, material_code="NVL1", year=2024)
    add_run(session, company.id, code="C6.1", remedy=REMEDY_NEED_OTHER_PERIOD_OR_CONFIRMATION)

    _panel(session, company)

    row = session.scalar(select(CheckRun).where(CheckRun.check_code == "C6.1"))
    assert (row.remedy, row.status_reason, row.status) == (
        REMEDY_NEED_OTHER_PERIOD_OR_CONFIRMATION,
        "Thiếu đầu vào bắt buộc.",
        STATUS_NOT_EVALUABLE,
    )


# --- Lớp 3 là KẾT LUẬN VỀ DOANH NGHIỆP -----------------------------------------


def test_a_class_three_item_is_marked_a_conclusion_not_a_data_gap(session, company):
    add_run(session, company.id, code="C4.3", remedy=REMEDY_NOTHING_TO_LOAD)

    groups = _panel(session, company)

    assert _item(groups, "C4.3").conclusion is True
    assert _group_of(groups, "C4.3").conclusion is True
    assert _group_of(groups, "C4.3").counted is False


def test_class_one_and_two_stay_data_gaps(session, company):
    add_run(session, company.id, code="C1.1", remedy=REMEDY_NEED_FILE_THIS_PERIOD)
    add_run(session, company.id, code="C6.1", remedy=REMEDY_NEED_OTHER_PERIOD_OR_CONFIRMATION)

    groups = _panel(session, company)

    assert [g.counted for g in groups] == [True, True]
    assert [item.conclusion for item in _items(groups)] == [False, False]


def test_a_class_three_item_points_at_the_check_that_lists_the_detail(session, company):
    """C4.3 không kết luận được vì độ phủ định mức; C4.9 liệt kê từng mã thiếu."""
    add_run(session, company.id, code="C4.3", remedy=REMEDY_NOTHING_TO_LOAD)

    item = _item(_panel(session, company), "C4.3")

    assert item.detail_code == "C4.9"
    assert item.url == f"/companies/{company.code}?year=2024&check=C4.9"


def test_a_class_three_item_without_a_detail_check_still_renders(session, company):
    add_run(session, company.id, code="C1.1", remedy=REMEDY_NOTHING_TO_LOAD)

    item = _item(_panel(session, company), "C1.1")

    assert detail_check_for("C1.1") is None
    assert item.detail_code is None
    assert item.url is None
    assert item.conclusion is True


# --- Bản ghi trước migration: remedy rỗng --------------------------------------


def test_a_row_without_a_stored_class_gets_its_own_group(session, company):
    """Không suy lớp cho nó: gán bừa một lớp là khẳng định thứ chưa từng đo được."""
    add_run(session, company.id, code="C4.3", remedy=None)

    groups = _panel(session, company)

    assert [g.remedy for g in groups] == [REMEDY_UNKNOWN]
    assert _item(groups, "C4.3").remedy is None
    assert _item(groups, "C4.3").url is None
    assert _item(groups, "C4.3").conclusion is False
    assert _group_of(groups, "C4.3").counted is False


def test_a_row_without_a_stored_class_keeps_its_reason(session, company):
    add_run(session, company.id, code="C4.3", remedy=None, reason="Chưa có Mẫu 16.")

    assert _item(_panel(session, company), "C4.3").reason == "Chưa có Mẫu 16."


def test_a_stored_class_outside_the_three_is_shown_not_dropped(session, company):
    """Rơi khỏi khối là kiểu hỏng nặng hơn hiển thị sai nhóm: điểm rủi ro vẫn loại mã
    đó, nên cán bộ mất luôn dấu vết vì sao một kiểm tra không có kết luận."""
    add_run(session, company.id, code="C4.3", remedy="lớp-lạ")

    groups = _panel(session, company)

    assert [g.remedy for g in groups] == [REMEDY_UNKNOWN]
    assert _item(groups, "C4.3").remedy is None
    assert _item(groups, "C4.3").url is None


def test_the_unknown_group_sorts_after_the_three_classes(session, company):
    add_run(session, company.id, code="C1.1", remedy=None)
    add_run(session, company.id, code="C4.3", remedy=REMEDY_NOTHING_TO_LOAD)
    add_run(session, company.id, code="C6.1", remedy=REMEDY_NEED_FILE_THIS_PERIOD)

    assert [g.remedy for g in _panel(session, company)] == [
        REMEDY_NEED_FILE_THIS_PERIOD,
        REMEDY_NOTHING_TO_LOAD,
        REMEDY_UNKNOWN,
    ]


# --- Tiêu đề kiểm tra ------------------------------------------------------------


def test_an_item_carries_the_check_title(session, company):
    add_run(session, company.id, code="C6.1", remedy=REMEDY_NEED_FILE_THIS_PERIOD)

    assert _item(_panel(session, company), "C6.1").title.startswith("Tồn đầu kỳ N")


def test_an_unknown_check_code_falls_back_to_the_code(session, company):
    add_run(session, company.id, code="X.9", remedy=REMEDY_NEED_FILE_THIS_PERIOD)

    assert _item(_panel(session, company), "X.9").title == "X.9"


# --- Màn phát hiện dựng được ------------------------------------------------------


def _client(app_db: AppDb, code: str = "DN_NE") -> TestClient:
    with app_db.SessionLocal() as db:
        db.add(Company(code=code, name="DN chưa đánh giá được", tax_id="1"))
        db.commit()
    client = TestClient(app)
    client.post("/login", data={"user": "admin", "password": "admin"}, follow_redirects=False)
    return client


def test_the_findings_screen_renders_a_row_written_before_the_migration(app_db: AppDb):
    client = _client(app_db)
    with app_db.SessionLocal() as db:
        company = db.scalar(select(Company).where(Company.code == "DN_NE"))
        add_nvl(db, company.id, material_code="NVL1", year=2024)
        add_run(db, company.id, code="C4.3", remedy=None)

    r = client.get("/companies/DN_NE?year=2024")

    assert r.status_code == 200


def test_the_findings_screen_carries_the_remedy_link_of_a_class_one_code(app_db: AppDb):
    client = _client(app_db)
    with app_db.SessionLocal() as db:
        company = db.scalar(select(Company).where(Company.code == "DN_NE"))
        add_nvl(db, company.id, material_code="NVL1", year=2024)
        add_run(db, company.id, code="C1.1", remedy=REMEDY_NEED_FILE_THIS_PERIOD)

    r = client.get("/companies/DN_NE?year=2024")

    assert r.status_code == 200
    assert "/companies/DN_NE/documents?add=2024#ky-2024" in r.text


def test_the_findings_screen_carries_the_detail_check_link_of_a_class_three_code(app_db: AppDb):
    client = _client(app_db)
    with app_db.SessionLocal() as db:
        company = db.scalar(select(Company).where(Company.code == "DN_NE"))
        add_nvl(db, company.id, material_code="NVL1", year=2024)
        add_run(db, company.id, code="C4.3", remedy=REMEDY_NOTHING_TO_LOAD)

    r = client.get("/companies/DN_NE?year=2024")

    assert r.status_code == 200
    assert "/companies/DN_NE?year=2024&amp;check=C4.9" in r.text
