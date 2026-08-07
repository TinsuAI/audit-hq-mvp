"""Ô thả file của một kỳ (#88): gợi ý loại có căn cứ · gán sổ · khoá nút nạp.

Thay trang tải lên bốn ô và ô chọn năm của nó. Mỗi kỳ MỘT ô thả nhận mọi file; hệ
thống gợi ý loại và nêu căn cứ; cán bộ sửa TRƯỚC khi nạp — nên lượt thả file KHÔNG
xếp việc nạp, khác hẳn form cũ (xếp việc rồi chuyển thẳng sang trang công việc).

Hai tầng chặn gán sổ, test cả hai:
- sớm — nút nạp khoá và handler từ chối xếp việc, để cán bộ không phải chờ;
- muộn — `IngestPlanError` trong kế hoạch nạp, giữ nguyên cho đường dòng lệnh và
  mọi đường khác.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import select

from app.main import app
from app.models import Company, DataFile, Job, NvlBalance
from app.pipeline.file_intake import (
    BASIS_CONTENT,
    BASIS_NAME,
    BASIS_OFFICER,
    CONTENT_PROBE_MAX_BYTES,
    STAGING_SUBDIR,
)
from tests.conftest import AppDb
from tests.helpers import XLSX_MIME, m15_xlsx_bytes

_CODE = "DN_DROP"
_YEAR = 2024


def _xlsx_bytes(marker: str) -> bytes:
    wb = Workbook()
    wb.active["A1"] = marker
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _company(app_db: AppDb, code: str = _CODE) -> int:
    with app_db.SessionLocal() as db:
        c = Company(code=code, name="Thả file", tax_id="1")
        db.add(c)
        db.commit()
        return c.id


def _client() -> TestClient:
    c = TestClient(app)
    c.post("/login", data={"user": "admin", "password": "admin"}, follow_redirects=False)
    return c


def _drop(client: TestClient, files: list[tuple[str, tuple]], code: str = _CODE, year: int = _YEAR):
    return client.post(
        f"/companies/{code}/upload",
        data={"year": str(year)},
        files=files,
        follow_redirects=False,
    )


def _f(name: str, payload: bytes | None = None) -> tuple[str, tuple]:
    return ("files", (name, payload if payload is not None else _xlsx_bytes(name), XLSX_MIME))


def _rows(app_db: AppDb, code: str = _CODE) -> list[DataFile]:
    with app_db.SessionLocal() as db:
        c = db.scalar(select(Company).where(Company.code == code))
        return list(db.scalars(
            select(DataFile).where(DataFile.company_id == c.id).order_by(DataFile.id)
        ).all())


def _jobs(app_db: AppDb) -> list[Job]:
    with app_db.SessionLocal() as db:
        return list(db.scalars(select(Job)).all())


def _screen(app_db: AppDb, code: str = _CODE):
    from app.pipeline.data_screen import build_data_screen

    with app_db.SessionLocal() as db:
        company = db.scalar(select(Company).where(Company.code == code))
        return build_data_screen(db, company)


def _period(app_db: AppDb, year: int = _YEAR, code: str = _CODE):
    return next(p for p in _screen(app_db, code).periods if p.year == year)


# --- Ô thả nhận nhiều file --------------------------------------------------------


def test_one_drop_takes_several_files_of_different_types(app_db: AppDb):
    _company(app_db)
    r = _drop(_client(), [
        _f("NhapXuatTon_NVL_2024.xlsx"),
        _f("M15a_SP_2024.xlsx"),
        _f("BCDM_TT39_2024.xlsx"),
        _f("BaoCaoHangChiTiet_2024.xlsx"),
    ])
    assert r.status_code == 303
    assert {row.slot for row in _rows(app_db)} == {"m15", "m15a", "m16", "bcct"}


def test_the_drop_zone_input_takes_several_files(app_db: AppDb):
    """Không có `multiple` trên ô thả thì trình duyệt chỉ gửi 1 file — mọi sửa đổi
    phía máy chủ thành vô ích. Bất biến cũ của ô BCCT, khẳng định lại ở ô thả."""
    _company(app_db)
    html = _client().get(f"/companies/{_CODE}/documents?add={_YEAR}").text

    inputs = [
        line for line in html.splitlines()
        if 'name="files"' in line and 'type="file"' in line
    ]
    assert inputs, "màn dữ liệu phải có ô thả file"
    for line in inputs:
        assert "multiple" in line


def test_dropping_files_does_not_queue_the_ingest(app_db: AppDb):
    """Cán bộ sửa loại/sổ TRƯỚC khi nạp — thả file mà tự nạp là cướp mất bước đó."""
    _company(app_db)
    _drop(_client(), [_f("NhapXuatTon_NVL_2024.xlsx")])
    assert _jobs(app_db) == []


def test_the_drop_lands_back_on_the_data_screen_at_that_period(app_db: AppDb):
    _company(app_db)
    r = _drop(_client(), [_f("NhapXuatTon_NVL_2024.xlsx")])
    assert r.headers["location"] == f"/companies/{_CODE}/documents#ky-{_YEAR}"


# --- Căn cứ của gợi ý -------------------------------------------------------------


def test_a_name_match_is_recorded_as_a_guess_from_the_name(app_db: AppDb):
    _company(app_db)
    _drop(_client(), [_f("NhapXuatTon_NVL_2024.xlsx")])
    assert [r.slot_basis for r in _rows(app_db)] == [BASIS_NAME]


def test_a_file_the_name_does_not_resolve_is_opened_and_matched(app_db: AppDb):
    _company(app_db)
    _drop(_client(), [_f("BaoCao.xlsx", m15_xlsx_bytes())])
    rows = _rows(app_db)
    assert [(r.slot, r.slot_basis) for r in rows] == [("m15", BASIS_CONTENT)]


def test_a_large_unresolved_file_waits_for_the_officer_and_is_never_opened(
    app_db: AppDb, monkeypatch
):
    """File lớn tên không phân giải được đi thẳng vào danh sách tự chọn."""
    from app.pipeline import file_intake

    opened: list[Path] = []
    monkeypatch.setattr(
        file_intake, "content_slots", lambda p, y=None: opened.append(p) or ("m15",)
    )
    monkeypatch.setattr(file_intake, "CONTENT_PROBE_MAX_BYTES", 10)
    _company(app_db)

    _drop(_client(), [_f("BaoCao.xlsx", m15_xlsx_bytes())])

    assert opened == []
    assert _rows(app_db) == []
    staged = app_db.raw_root / _CODE / str(_YEAR) / STAGING_SUBDIR
    assert [p.name for p in staged.iterdir()] == ["BaoCao.xlsx"]


def test_a_file_waiting_for_a_type_shows_up_on_the_period_row(app_db: AppDb, monkeypatch):
    from app.pipeline import file_intake

    monkeypatch.setattr(file_intake, "content_slots", lambda p, y=None: ())
    _company(app_db)
    _drop(_client(), [_f("BaoCao.xlsx", m15_xlsx_bytes())])

    pending = _period(app_db).pending
    assert [p.name for p in pending] == ["BaoCao.xlsx"]


def test_the_threshold_is_the_measured_one(app_db: AppDb):
    """0,14–0,20 giây với biểu nhỏ, 96,93 giây với file 71,3MB — ngưỡng nằm giữa."""
    assert 1024 * 1024 <= CONTENT_PROBE_MAX_BYTES < 71 * 1024 * 1024


# --- Cán bộ sửa loại --------------------------------------------------------------


def test_the_officer_can_change_the_type_of_a_registered_file(app_db: AppDb):
    _company(app_db)
    client = _client()
    _drop(client, [_f("NhapXuatTon_NVL_2024.xlsx")])
    path = _rows(app_db)[0].stored_path

    r = client.post(
        f"/companies/{_CODE}/documents/file-type",
        data={"year": str(_YEAR), "path": path, "slot": "m16"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    rows = _rows(app_db)
    assert [(x.slot, x.slot_basis) for x in rows] == [("m16", BASIS_OFFICER)]
    assert rows[0].stored_path.startswith(f"{_CODE}/{_YEAR}/DINH_MUC/")
    assert not (app_db.raw_root / _CODE / str(_YEAR) / "BCQT").exists() or not list(
        (app_db.raw_root / _CODE / str(_YEAR) / "BCQT").glob("*.xlsx")
    )


def test_the_officer_choosing_a_type_brings_a_waiting_file_into_the_system(
    app_db: AppDb, monkeypatch
):
    from app.pipeline import file_intake

    monkeypatch.setattr(file_intake, "content_slots", lambda p, y=None: ())
    _company(app_db)
    client = _client()
    _drop(client, [_f("BaoCao.xlsx", m15_xlsx_bytes())])
    rel = f"{_CODE}/{_YEAR}/{STAGING_SUBDIR}/BaoCao.xlsx"

    client.post(
        f"/companies/{_CODE}/documents/file-type",
        data={"year": str(_YEAR), "path": rel, "slot": "m15"},
        follow_redirects=False,
    )

    assert [(r.slot, r.slot_basis) for r in _rows(app_db)] == [("m15", BASIS_OFFICER)]
    assert _period(app_db).pending == ()


def test_choosing_the_type_a_file_already_has_keeps_the_file(app_db: AppDb):
    """Xoá file cùng slot phải trừ chính file đang chuyển — nếu không thì nó tự xoá
    file rồi đi tìm để chuyển. Cũng không phải là một lượt THAY file."""
    from app.models import CompanyPeriod

    company_id = _company(app_db)
    client = _client()
    _drop(client, [_f("NhapXuatTon_NVL_2024.xlsx", m15_xlsx_bytes())])
    path = _rows(app_db)[0].stored_path

    r = client.post(
        f"/companies/{_CODE}/documents/file-type",
        data={"year": str(_YEAR), "path": path, "slot": "m15"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert (app_db.raw_root / path).is_file()
    assert [(x.slot, x.slot_basis) for x in _rows(app_db)] == [("m15", BASIS_OFFICER)]
    with app_db.SessionLocal() as db:
        row = db.scalar(select(CompanyPeriod).where(
            CompanyPeriod.company_id == company_id, CompanyPeriod.period_year == _YEAR
        ))
    assert row is None or (row.data_version or 0) == 0


def test_a_path_outside_the_period_folder_is_refused(app_db: AppDb):
    _company(app_db)
    client = _client()
    r = client.post(
        f"/companies/{_CODE}/documents/file-type",
        data={"year": str(_YEAR), "path": "../../etc/passwd", "slot": "m15"},
        follow_redirects=False,
    )
    assert r.status_code == 400


# --- Bất biến cũ giữ nguyên -------------------------------------------------------


def test_two_settlement_files_of_the_same_type_replace_each_other(app_db: AppDb):
    _company(app_db)
    client = _client()
    for name in ("NhapXuatTon_NVL_cu.xlsx", "NhapXuatTon_NVL_moi.xlsx"):
        _drop(client, [_f(name)])
    bcqt = app_db.raw_root / _CODE / str(_YEAR) / "BCQT"
    assert {p.name for p in bcqt.glob("*.xlsx")} == {f"M15_NVL_{_YEAR}.xlsx"}


def test_several_declaration_files_of_one_period_add_up_instead_of_replacing(app_db: AppDb):
    """Bộ dữ liệu một kỳ nằm ở nhiều file BCCT rời (F1/F2/F3 của 006). Xoá file cũ ở
    đây là buộc cán bộ gộp tay, và bản gộp tay đã mất 28,5 tỷ ở ô công thức."""
    _company(app_db)
    client = _client()
    _drop(client, [_f("BCCT_F1.xlsx"), _f("BCCT_F3.xlsx")])
    _drop(client, [_f("BCCT_F2.xlsx")])

    d = app_db.raw_root / _CODE / str(_YEAR) / "HANG_CHI_TIET"
    assert {p.name for p in d.glob("*.xlsx")} == {
        "BCCT_F1.xlsx", "BCCT_F3.xlsx", "BCCT_F2.xlsx",
    }
    assert len([r for r in _rows(app_db) if r.slot == "bcct"]) == 3


def test_dropping_the_same_declaration_name_twice_replaces_that_one_file(app_db: AppDb):
    """Thả lại đúng tên cũ = sửa file đó, không sinh bản thứ hai."""
    _company(app_db)
    client = _client()
    _drop(client, [_f("BCCT_F1.xlsx", _xlsx_bytes("cu"))])
    _drop(client, [_f("BCCT_F1.xlsx", _xlsx_bytes("moi"))])

    d = app_db.raw_root / _CODE / str(_YEAR) / "HANG_CHI_TIET"
    assert [p.name for p in d.glob("*.xlsx")] == ["BCCT_F1.xlsx"]
    assert (d / "BCCT_F1.xlsx").read_bytes() == _xlsx_bytes("moi")
    assert len([r for r in _rows(app_db) if r.slot == "bcct"]) == 1


def test_replacing_a_file_moves_the_data_version_but_adding_one_does_not(app_db: AppDb):
    from app.models import CompanyPeriod

    company_id = _company(app_db)
    client = _client()

    def version() -> int:
        with app_db.SessionLocal() as db:
            row = db.scalar(select(CompanyPeriod).where(
                CompanyPeriod.company_id == company_id, CompanyPeriod.period_year == _YEAR
            ))
            return (row.data_version or 0) if row else 0

    _drop(client, [_f("NhapXuatTon_NVL_2024.xlsx")])
    after_first = version()
    _drop(client, [_f("BCCT_F1.xlsx")])
    assert version() == after_first
    _drop(client, [_f("NhapXuatTon_NVL_2024.xlsx")])
    assert version() > after_first


# --- Địa chỉ cũ -------------------------------------------------------------------


def test_the_old_upload_address_now_leads_to_the_data_screen(app_db: AppDb):
    _company(app_db)
    r = _client().get(f"/companies/{_CODE}/upload?year=2024", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == f"/companies/{_CODE}/documents#ky-2024"


def test_the_old_upload_address_without_a_year_still_leads_somewhere_usable(app_db: AppDb):
    _company(app_db)
    r = _client().get(f"/companies/{_CODE}/upload", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == f"/companies/{_CODE}/documents"


# --- Gán sổ + khoá nút nạp --------------------------------------------------------


def _make_multi_book(app_db: AppDb, company_id: int) -> None:
    """DN đã có hai sổ ở một kỳ trước — kỳ mới vẫn là DN nhiều sổ."""
    with app_db.SessionLocal() as db:
        for book in ("EPE", "GC"):
            db.add(NvlBalance(
                company_id=company_id, period_year=_YEAR - 1, book=book,
                material_code=f"MAT_{book}",
            ))
        db.commit()


def test_a_single_book_company_gets_no_book_selector_and_no_lock(app_db: AppDb):
    _company(app_db)
    _drop(_client(), [_f("NhapXuatTon_NVL_2024.xlsx")])
    row = _period(app_db)
    assert row.multi_book is False
    assert row.ingest_locked is False


def test_a_multi_book_company_locks_the_ingest_until_every_settlement_file_is_tagged(
    app_db: AppDb,
):
    company_id = _company(app_db)
    _make_multi_book(app_db, company_id)
    _drop(_client(), [_f("NhapXuatTon_NVL_2024.xlsx"), _f("BCCT_F1.xlsx")])

    row = _period(app_db)
    assert row.multi_book is True
    assert row.book_options == ("EPE", "GC")
    assert row.ingest_locked is True
    assert f"M15_NVL_{_YEAR}.xlsx" in row.ingest_lock_message


def test_the_declaration_file_is_never_what_blocks_the_ingest(app_db: AppDb):
    """Tờ khai luôn toàn pháp nhân (book=NULL) — bắt gán sổ cho nó là bịa ràng buộc."""
    company_id = _company(app_db)
    _make_multi_book(app_db, company_id)
    _drop(_client(), [_f("BCCT_F1.xlsx")])
    assert _period(app_db).ingest_locked is False


def test_the_early_layer_refuses_to_queue_while_a_settlement_file_has_no_book(
    app_db: AppDb,
):
    company_id = _company(app_db)
    _make_multi_book(app_db, company_id)
    client = _client()
    _drop(client, [_f("NhapXuatTon_NVL_2024.xlsx")])

    r = client.post(
        f"/companies/{_CODE}/documents/ingest",
        data={"year": str(_YEAR)},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "/jobs/" not in r.headers["location"]
    assert _jobs(app_db) == []


def test_tagging_every_settlement_file_releases_the_ingest(app_db: AppDb):
    company_id = _company(app_db)
    _make_multi_book(app_db, company_id)
    client = _client()
    _drop(client, [_f("NhapXuatTon_NVL_2024.xlsx")])
    path = _rows(app_db)[0].stored_path

    r = client.post(
        f"/companies/{_CODE}/documents/file-book",
        data={"year": str(_YEAR), "path": path, "book": "EPE"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert [x.book for x in _rows(app_db)] == ["EPE"]

    row = _period(app_db)
    assert row.ingest_locked is False

    r = client.post(
        f"/companies/{_CODE}/documents/ingest",
        data={"year": str(_YEAR)},
        follow_redirects=False,
    )
    assert r.headers["location"].startswith("/jobs/")
    assert len(_jobs(app_db)) == 1


def test_the_book_of_a_file_already_in_the_system_can_still_be_changed(app_db: AppDb):
    """DN đã nạp bằng dòng lệnh trước đây vẫn gán lại sổ được qua web (#88)."""
    company_id = _company(app_db)
    _make_multi_book(app_db, company_id)
    client = _client()
    _drop(client, [_f("NhapXuatTon_NVL_2024.xlsx")])
    path = _rows(app_db)[0].stored_path

    for book in ("EPE", "GC"):
        client.post(
            f"/companies/{_CODE}/documents/file-book",
            data={"year": str(_YEAR), "path": path, "book": book},
            follow_redirects=False,
        )
    assert [x.book for x in _rows(app_db)] == ["GC"]


def test_the_period_row_carries_the_book_of_each_settlement_file(app_db: AppDb):
    company_id = _company(app_db)
    _make_multi_book(app_db, company_id)
    client = _client()
    _drop(client, [_f("NhapXuatTon_NVL_2024.xlsx")])
    path = _rows(app_db)[0].stored_path
    client.post(
        f"/companies/{_CODE}/documents/file-book",
        data={"year": str(_YEAR), "path": path, "book": "GC"},
        follow_redirects=False,
    )

    files = _period(app_db).files
    assert [(f.is_settlement, f.book) for f in files] == [(True, "GC")]


def test_the_late_layer_still_blocks_a_plan_that_would_merge_two_books(app_db: AppDb):
    """Tầng chặn muộn giữ nguyên: đường dòng lệnh không đi qua nút nạp của màn dữ liệu."""
    from app.pipeline.ingest import IngestPlanError, ingest

    company_id = _company(app_db)
    with app_db.SessionLocal() as db:
        for b in ("EPE", "GC"):
            db.add(NvlBalance(
                company_id=company_id, period_year=_YEAR, book=b, material_code=f"M_{b}",
            ))
        db.commit()
    _drop(_client(), [_f("NhapXuatTon_NVL_2024.xlsx", m15_xlsx_bytes())])

    with pytest.raises(IngestPlanError):
        ingest(_CODE, _YEAR, raw_root=app_db.raw_root)
