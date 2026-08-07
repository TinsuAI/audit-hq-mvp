"""Form tải lên 4 ô: ô BCCT nhận NHIỀU file, cộng dồn thay vì thay thế.

Ca thật (006, 06/08): bộ dữ liệu một kỳ nằm ở nhiều file BCCT rời (F1/F2/F3).
Form chỉ nhận một file mỗi ô và `_save_upload` xoá mọi file cùng slot trước khi
ghi, nên tải file thứ hai là mất file thứ nhất. Cán bộ vì thế gộp tay bằng công
cụ ngoài, và bản gộp mất 28.563.550.970,35 đ ở 2.076 ô công thức
(`.ai/notes/2026-08-06-006-f1-f2-f3-vs-file-gop.md`).

Ba ô còn lại (m15/m15a/m16) giữ nguyên nghĩa 1 file/ô — mỗi biểu chỉ có một bản.
"""

from __future__ import annotations

import io
from pathlib import Path

from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.main import app
from app.models import Company, DataFile
from tests.conftest import AppDb
from tests.helpers import XLSX_MIME

_CODE = "DN_MULTI"


def _xlsx_bytes(marker: str) -> bytes:
    wb = Workbook()
    wb.active["A1"] = marker
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _client(app_db: AppDb) -> TestClient:
    with app_db.SessionLocal() as db:
        db.add(Company(code=_CODE, name="Multi", tax_id="1"))
        db.commit()
    c = TestClient(app)
    c.post("/login", data={"user": "admin", "password": "admin"}, follow_redirects=False)
    return c


def _bcct_dir(app_db: AppDb) -> Path:
    return app_db.raw_root / _CODE / "2024" / "HANG_CHI_TIET"


def _names(app_db: AppDb) -> set[str]:
    d = _bcct_dir(app_db)
    return {p.name for p in d.glob("*.xlsx")} if d.exists() else set()


def test_two_bcct_files_in_one_submit_both_land_on_disk(app_db: AppDb):
    client = _client(app_db)
    r = client.post(
        f"/companies/{_CODE}/upload",
        data={"year": "2024"},
        files=[
            ("bcct", ("BCCT_F1.xlsx", _xlsx_bytes("F1"), XLSX_MIME)),
            ("bcct", ("BCCT_F3.xlsx", _xlsx_bytes("F3"), XLSX_MIME)),
        ],
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert _names(app_db) == {"BCCT_F1.xlsx", "BCCT_F3.xlsx"}


def test_a_second_submit_adds_a_bcct_file_instead_of_replacing(app_db: AppDb):
    client = _client(app_db)
    for name in ("BCCT_F1.xlsx", "BCCT_F3.xlsx"):
        r = client.post(
            f"/companies/{_CODE}/upload",
            data={"year": "2024"},
            files=[("bcct", (name, _xlsx_bytes(name), XLSX_MIME))],
            follow_redirects=False,
        )
        assert r.status_code == 303
    assert _names(app_db) == {"BCCT_F1.xlsx", "BCCT_F3.xlsx"}


def test_both_bcct_files_are_registered_as_documents(app_db: AppDb):
    client = _client(app_db)
    client.post(
        f"/companies/{_CODE}/upload",
        data={"year": "2024"},
        files=[
            ("bcct", ("BCCT_F1.xlsx", _xlsx_bytes("F1"), XLSX_MIME)),
            ("bcct", ("BCCT_F3.xlsx", _xlsx_bytes("F3"), XLSX_MIME)),
        ],
        follow_redirects=False,
    )
    with app_db.SessionLocal() as db:
        c = db.query(Company).filter_by(code=_CODE).first()
        rows = db.query(DataFile).filter_by(company_id=c.id, slot="bcct").all()
        assert {r.original_filename for r in rows} == {"BCCT_F1.xlsx", "BCCT_F3.xlsx"}


def test_upload_form_lets_the_officer_pick_several_bcct_files(app_db: AppDb):
    """Không có `multiple` trên ô BCCT thì trình duyệt chỉ gửi 1 file — sửa backend vô ích."""
    client = _client(app_db)
    html = client.get(f"/companies/{_CODE}/upload?year=2024").text

    bcct_input = next(
        line for line in html.splitlines()
        if 'name="bcct"' in line and "type=\"file\"" in line
    )
    assert "multiple" in bcct_input
    for slot in ("m15", "m15a", "m16"):
        other = next(
            line for line in html.splitlines()
            if f'name="{slot}"' in line and "type=\"file\"" in line
        )
        assert "multiple" not in other


def test_m15_still_replaces_the_previous_file(app_db: AppDb):
    client = _client(app_db)
    for name in ("Mau15_cu.xlsx", "Mau15_moi.xlsx"):
        client.post(
            f"/companies/{_CODE}/upload",
            data={"year": "2024"},
            files=[("m15", (name, _xlsx_bytes(name), XLSX_MIME))],
            follow_redirects=False,
        )
    bcqt = app_db.raw_root / _CODE / "2024" / "BCQT"
    assert {p.name for p in bcqt.glob("*.xlsx")} == {"M15_NVL_2024.xlsx"}


def test_uploading_the_same_bcct_name_twice_replaces_that_one_file(app_db: AppDb):
    """Tải lại đúng tên cũ = sửa file đó, không sinh bản thứ hai."""
    client = _client(app_db)
    for marker in ("cu", "moi"):
        client.post(
            f"/companies/{_CODE}/upload",
            data={"year": "2024"},
            files=[("bcct", ("BCCT_F1.xlsx", _xlsx_bytes(marker), XLSX_MIME))],
            follow_redirects=False,
        )
    assert _names(app_db) == {"BCCT_F1.xlsx"}
    wrote = (_bcct_dir(app_db) / "BCCT_F1.xlsx").read_bytes()
    assert wrote == _xlsx_bytes("moi")
