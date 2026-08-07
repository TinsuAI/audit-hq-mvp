"""T7 (#87) — dòng kỳ mở ra: tóm tắt theo LOẠI tài liệu + danh sách FILE THẬT.

Hai sự thật đo được quyết định hình dạng, và cả hai đều là test ở đây:

- **Số dòng thuộc về loại tài liệu, không thuộc file.** `record_parse_result` ghi
  tổng dòng của cả kỳ lên MỌI file cùng loại — docstring của chính nó nói vậy.
  PILOT_006 kỳ 2025 có hai file BCCT cùng mang 270.505 trong khi cả kỳ có đúng
  270.505 dòng tờ khai; in số đó cạnh từng file làm kỳ đọc thành 541.010.
- **Một workbook phục vụ được ba biểu.** PILOT_006 đăng ký một file 5,8MB cho cả
  Mẫu 15 (10.560 dòng), Mẫu 15a (501) và Mẫu 16 (113.561) — registry đánh khoá
  theo (đường dẫn, loại) nên đó là ba dòng cùng `stored_path`, phải hiện MỘT lần
  với ba nhãn. PILOT_002 dùng ba file rời; cả hai hình dạng đều thật.

Khẳng định ở mức DỮ LIỆU: trên thứ hàm dựng trả về và thứ route đưa vào ngữ cảnh
template. Đúng một test dò markup — AC "cảnh báo phải là chữ đọc được, không phải
biểu tượng chỉ có nội dung trong thuộc tính hover" chỉ chứng minh được ở markup.
"""

from __future__ import annotations

import re

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import Company, DataFile
from app.models.data_file import SLOT_ORDER, DataFileStatus
from app.pipeline.data_screen import build_data_screen
from app.pipeline.readiness import (
    SLOT_NEEDS_COLUMN_REVIEW,
    SLOT_NO_FILE,
    SLOT_PARSE_ERROR,
    SLOT_READY,
)
from tests.conftest import AppDb, add_decl
from tests.test_readiness import add_file

WORKBOOK = "DN/2025/BCQT/quyet_toan_gop.xlsx"


def _row(screen, year: int):
    return next(p for p in screen.periods if p.year == year)


def _doc_type(row, slot: str):
    return next(d for d in row.doc_types if d.slot == slot)


def _file(row, name: str):
    return next(f for f in row.files if f.name == name)


# --- Sự thật 1: số dòng thuộc về LOẠI, không thuộc file -------------------------


def test_two_files_of_one_type_do_not_double_the_period_count(session, company):
    """PILOT_006 kỳ 2025: hai file BCCT cùng mang tổng dòng của cả kỳ."""
    add_file(session, company.id, slot="bcct", year=2025, name="bcct_nhap.xlsx",
             path="DN/2025/HANG_CHI_TIET/bcct_nhap.xlsx", rows=270505, size=20_600_000)
    add_file(session, company.id, slot="bcct", year=2025, name="bcct_xuat.xlsx",
             path="DN/2025/HANG_CHI_TIET/bcct_xuat.xlsx", rows=270505, size=71_300_000)
    session.commit()

    row = _row(build_data_screen(session, company), 2025)

    assert _doc_type(row, "bcct").row_count == 270505
    assert _doc_type(row, "bcct").file_count == 2
    assert len(row.files) == 2


def test_no_file_line_carries_a_row_count(session, company):
    """Con số của loại KHÔNG được lặp lại ở dòng file — đó là chỗ nó cộng gấp đôi."""
    add_file(session, company.id, slot="bcct", year=2025, name="a.xlsx",
             path="DN/2025/HANG_CHI_TIET/a.xlsx", rows=270505)
    add_file(session, company.id, slot="bcct", year=2025, name="b.xlsx",
             path="DN/2025/HANG_CHI_TIET/b.xlsx", rows=270505)
    session.commit()

    row = _row(build_data_screen(session, company), 2025)
    for entry in row.files:
        assert not hasattr(entry, "row_count")
        assert not hasattr(entry, "rows")


def test_a_type_never_parsed_reports_unknown_not_zero(session, company):
    add_file(session, company.id, slot="m15", year=2025, status=DataFileStatus.PENDING)
    session.commit()

    row = _row(build_data_screen(session, company), 2025)
    assert _doc_type(row, "m15").row_count is None


def test_a_count_read_but_not_committed_is_not_a_count_the_period_holds(session, company):
    """Lượt nạp dừng ở cổng xác nhận cột vẫn ghi số dòng ĐỌC ĐƯỢC lên bản ghi file.

    `record_parse_result` ghi `row_count` kể cả ở lượt dry-run (`committed=False`),
    nên loại này mang 10.560 trong khi kỳ chưa nhận dòng nào. Hai sự thật phải đi
    cùng nhau, nếu không con số mâu thuẫn với chính câu vướng mắc bên dưới.
    """
    add_file(session, company.id, slot="m15", year=2025, status=DataFileStatus.ANALYZED,
             needs_review=True, rows=10560)
    session.commit()

    summary = _doc_type(_row(build_data_screen(session, company), 2025), "m15")
    assert summary.row_count == 10560
    assert summary.has_rows is False
    assert summary.state == SLOT_NEEDS_COLUMN_REVIEW


def test_the_summary_lists_every_document_type_in_display_order(session, company):
    add_file(session, company.id, slot="m15", year=2025)
    session.commit()

    row = _row(build_data_screen(session, company), 2025)
    assert tuple(d.slot for d in row.doc_types) == SLOT_ORDER
    assert _doc_type(row, "bcct").state == SLOT_NO_FILE
    assert _doc_type(row, "bcct").file_count == 0
    assert _doc_type(row, "bcct").row_count is None


def test_the_summary_state_is_the_readiness_state_not_a_second_reading(session, company):
    add_decl(session, company.id, declaration_no="1", customs_code="E31", item_code="A",
             quantity=10, year=2025)
    add_file(session, company.id, slot="bcct", year=2025, rows=1)
    add_file(session, company.id, slot="m15", year=2025, status=DataFileStatus.ERROR)
    session.commit()

    row = _row(build_data_screen(session, company), 2025)
    assert _doc_type(row, "bcct").state == SLOT_READY
    assert _doc_type(row, "bcct").has_rows is True
    assert _doc_type(row, "m15").state == SLOT_PARSE_ERROR


# --- Sự thật 2: một workbook phục vụ nhiều loại = MỘT dòng file -----------------


def test_one_workbook_serving_three_types_is_a_single_file_line(session, company):
    """PILOT_006: một file 5,8MB đăng ký cho Mẫu 15 · 15a · 16."""
    for slot, rows in (("m15", 10560), ("m15a", 501), ("m16", 113561)):
        add_file(session, company.id, slot=slot, year=2025, path=WORKBOOK, rows=rows,
                 size=5_800_000)
    session.commit()

    row = _row(build_data_screen(session, company), 2025)

    assert len(row.files) == 1
    entry = row.files[0]
    assert entry.name == "quyet_toan_gop.xlsx"
    assert entry.slots == ("m15", "m15a", "m16")
    assert len(entry.slot_labels) == 3
    assert entry.size_bytes == 5_800_000
    # Ba biểu, ba con số riêng — chúng ở tóm tắt, không ở dòng file.
    assert _doc_type(row, "m15").row_count == 10560
    assert _doc_type(row, "m15a").row_count == 501
    assert _doc_type(row, "m16").row_count == 113561


def test_the_single_line_keeps_every_registration_id_of_that_workbook(session, company):
    """Xoá một file thật phải gỡ được cả ba đăng ký của nó."""
    ids = []
    for slot in ("m15", "m15a", "m16"):
        f = add_file(session, company.id, slot=slot, year=2025, path=WORKBOOK)
        session.flush()
        ids.append(f.id)
    session.commit()

    entry = _row(build_data_screen(session, company), 2025).files[0]
    assert set(entry.file_ids) == set(ids)
    assert entry.file_id == min(ids)


def test_three_separate_files_stay_three_lines(session, company):
    """PILOT_002 dùng ba file rời — hình dạng này cũng thật."""
    for slot in ("m15", "m15a", "m16"):
        add_file(session, company.id, slot=slot, year=2025)
    session.commit()

    row = _row(build_data_screen(session, company), 2025)
    assert len(row.files) == 3
    assert all(len(f.slots) == 1 for f in row.files)


def test_file_lines_are_ordered_by_document_type_then_name(session, company):
    add_file(session, company.id, slot="bcct", year=2025, name="z_bcct.xlsx",
             path="DN/2025/HANG_CHI_TIET/z_bcct.xlsx")
    add_file(session, company.id, slot="bcct", year=2025, name="a_bcct.xlsx",
             path="DN/2025/HANG_CHI_TIET/a_bcct.xlsx")
    add_file(session, company.id, slot="m15", year=2025, name="m15.xlsx")
    session.commit()

    row = _row(build_data_screen(session, company), 2025)
    assert [f.name for f in row.files] == ["m15.xlsx", "a_bcct.xlsx", "z_bcct.xlsx"]


# --- Dòng file chỉ hiện thứ có HỆ QUẢ -------------------------------------------


def test_a_file_with_nothing_wrong_shows_name_size_and_types_only(session, company):
    add_file(session, company.id, slot="m15", year=2025, rows=120, size=4096)
    session.commit()

    entry = _row(build_data_screen(session, company), 2025).files[0]
    assert entry.name == "m15.xlsx"
    assert entry.size_bytes == 4096
    assert entry.slots == ("m15",)
    assert entry.needs_column_review is False
    assert entry.unreadable is False
    assert entry.notes == ()
    assert entry.plain is True


def test_the_read_basis_does_not_ride_along_on_the_file_line(session, company):
    """Căn cứ đọc thuộc trang file (#92) — ADR #24 sửa ADR #18 ở đúng chỗ này."""
    add_file(session, company.id, slot="m15", year=2025)
    session.commit()

    entry = _row(build_data_screen(session, company), 2025).files[0]
    for absent in ("parse_detail", "columns", "evidence", "layout", "template_id",
                   "match_source", "form_signature"):
        assert not hasattr(entry, absent), f"{absent} thuộc trang file, không thuộc dòng này"


def test_a_file_that_will_not_read_says_so_in_readable_text(session, company):
    add_file(session, company.id, slot="m15", year=2025, status=DataFileStatus.ERROR,
             message="Nạp được 0 dòng — kiểm tra lại cấu trúc file.")
    session.commit()

    entry = _row(build_data_screen(session, company), 2025).files[0]
    assert entry.unreadable is True
    assert entry.plain is False
    assert "Nạp được 0 dòng — kiểm tra lại cấu trúc file." in entry.notes


def test_a_column_still_to_confirm_is_marked_on_the_file_that_holds_it(session, company):
    add_file(session, company.id, slot="m15", year=2025, status=DataFileStatus.ANALYZED,
             needs_review=True)
    add_file(session, company.id, slot="m16", year=2025, status=DataFileStatus.ANALYZED)
    session.commit()

    row = _row(build_data_screen(session, company), 2025)
    assert _file(row, "m15.xlsx").needs_column_review is True
    # Cổng dừng CẢ KỲ, nhưng cột vướng nằm ở file nào thì đánh dấu file đó.
    assert _file(row, "m16.xlsx").needs_column_review is False
    assert _doc_type(row, "m15").state == SLOT_NEEDS_COLUMN_REVIEW


def test_an_advisory_warning_reaches_the_file_line_as_text(session, company):
    """Cảnh báo tư vấn giữ nguyên vòng đời `ok` — nó chỉ hiện khi có hệ quả."""
    add_file(session, company.id, slot="bcct", year=2025, rows=10,
             message="Cột đơn giá đọc theo vị trí, không có tiêu đề khớp.")
    session.commit()

    entry = _row(build_data_screen(session, company), 2025).files[0]
    assert entry.unreadable is False
    assert entry.notes == ("Cột đơn giá đọc theo vị trí, không có tiêu đề khớp.",)


def test_one_warning_repeated_on_every_registration_is_said_once(session, company):
    """Thông điệp cũng bị đóng dấu theo loại — một workbook ba đăng ký, một câu."""
    for slot in ("m15", "m15a", "m16"):
        add_file(session, company.id, slot=slot, year=2025, path=WORKBOOK,
                 message="Trang tính chọn theo điểm, không theo tên.")
    session.commit()

    entry = _row(build_data_screen(session, company), 2025).files[0]
    assert entry.notes == ("Trang tính chọn theo điểm, không theo tên.",)


# --- Mở · tải · xoá trên mỗi dòng file ------------------------------------------


def test_every_file_line_carries_open_download_and_delete(session, company):
    f = add_file(session, company.id, slot="m15", year=2025)
    session.commit()

    entry = _row(build_data_screen(session, company), 2025).files[0]
    base = f"/companies/TEST_DN/documents/file/{f.id}"
    assert entry.open_url == f"{base}/preview"
    assert entry.download_url == f"{base}/download"
    assert entry.delete_url == f"{base}/delete"


# --- Route ----------------------------------------------------------------------


def _client(app_db: AppDb) -> TestClient:
    with app_db.SessionLocal() as db:
        db.add(Company(code="DN_T7", name="Kỳ mở rộng", tax_id="7"))
        db.commit()
    client = TestClient(app)
    client.post("/login", data={"user": "admin", "password": "admin"},
                follow_redirects=False)
    return client


def _register(app_db: AppDb, *, rel: str, slots, year=2025, **kwargs) -> list[int]:
    """Ghi file THẬT xuống thư mục dữ liệu thô + đăng ký nó cho từng loại.

    File phải có trên đĩa: `sync_data_files` chạy ở mỗi lượt vào màn dữ liệu và
    xoá khỏi registry mọi dòng mà file đã biến mất.
    """
    abs_path = app_db.raw_root / rel
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_bytes(b"x" * 32)
    ids = []
    with app_db.SessionLocal() as db:
        c = db.scalar(select(Company).where(Company.code == "DN_T7"))
        for slot in slots:
            row = DataFile(
                company_id=c.id, period_year=year, slot=slot,
                original_filename=abs_path.name, stored_path=rel,
                size_bytes=abs_path.stat().st_size, **kwargs,
            )
            db.add(row)
            db.flush()
            ids.append(row.id)
        db.commit()
    return ids


def test_the_route_puts_the_type_summary_and_the_file_list_in_the_context(app_db: AppDb):
    client = _client(app_db)
    _register(app_db, rel="DN_T7/2025/HANG_CHI_TIET/bcct_a.xlsx", slots=("bcct",),
              parse_status=DataFileStatus.OK, row_count=270505)
    _register(app_db, rel="DN_T7/2025/HANG_CHI_TIET/bcct_b.xlsx", slots=("bcct",),
              parse_status=DataFileStatus.OK, row_count=270505)

    r = client.get("/companies/DN_T7/documents")
    assert r.status_code == 200

    row = _row(r.context["screen"], 2025)
    assert _doc_type(row, "bcct").row_count == 270505
    assert [f.name for f in row.files] == ["bcct_a.xlsx", "bcct_b.xlsx"]
    assert all(f.open_url and f.download_url and f.delete_url for f in row.files)


def test_a_parse_warning_is_readable_text_not_only_a_hover_attribute(app_db: AppDb):
    """AC riêng của markup: gỡ hết thuộc tính hover thì câu cảnh báo phải còn."""
    warning = "Trang tính chọn theo điểm, không theo tên."
    client = _client(app_db)
    _register(app_db, rel="DN_T7/2025/HANG_CHI_TIET/bcct_a.xlsx", slots=("bcct",),
              parse_status=DataFileStatus.OK, row_count=10, parse_message=warning)

    html = client.get("/companies/DN_T7/documents").text
    visible = re.sub(r'(title|aria-label)="[^"]*"', "", html)
    assert warning in visible


def test_deleting_one_workbook_clears_every_type_registration_of_it(app_db: AppDb):
    """Một file thật ba đăng ký: xoá một dòng mà bỏ lại hai dòng mồ côi là sai."""
    client = _client(app_db)
    rel = "DN_T7/2025/BCQT/quyet_toan_gop.xlsx"
    ids = _register(app_db, rel=rel, slots=("m15", "m15a", "m16"),
                    parse_status=DataFileStatus.OK, row_count=5)

    r = client.post(f"/companies/DN_T7/documents/file/{ids[0]}/delete",
                    follow_redirects=False)
    assert r.status_code == 303

    with app_db.SessionLocal() as db:
        assert db.scalars(select(DataFile).where(DataFile.stored_path == rel)).all() == []
    assert not (app_db.raw_root / rel).exists()


def test_deleting_a_file_of_another_company_is_refused(app_db: AppDb):
    client = _client(app_db)
    ids = _register(app_db, rel="DN_T7/2025/BCQT/nvl_2025.xlsx", slots=("m15",),
                    parse_status=DataFileStatus.OK)
    with app_db.SessionLocal() as db:
        db.add(Company(code="DN_KHAC", name="Khác", tax_id="8"))
        db.commit()

    r = client.post(f"/companies/DN_KHAC/documents/file/{ids[0]}/delete",
                    follow_redirects=False)
    assert r.status_code == 404
    with app_db.SessionLocal() as db:
        assert db.get(DataFile, ids[0]) is not None
