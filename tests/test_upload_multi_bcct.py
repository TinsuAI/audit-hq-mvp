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
from sqlalchemy.pool import StaticPool

import app.database as dbmod
from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import Company, DataFile
from app.settings import settings

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _xlsx_bytes(marker: str) -> bytes:
    wb = Workbook()
    wb.active["A1"] = marker
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _setup(tmp_path: Path):
    new_engine = dbmod.create_engine(
        "sqlite://", connect_args={"check_same_thread": False},
        poolclass=StaticPool, future=True,
    )
    new_session = dbmod.sessionmaker(bind=new_engine, autoflush=False, autocommit=False, future=True)
    dbmod.engine = new_engine
    dbmod.SessionLocal = new_session
    Base.metadata.create_all(new_engine)
    with new_session() as db:
        from app.auth_users import seed_default_admin
        seed_default_admin(db, "admin", "admin")
        db.add(Company(code="DN_MULTI", name="Multi", tax_id="1"))
        db.commit()
    prev_root = settings.raw_data_path
    settings.raw_data_path = str(tmp_path)
    return new_engine, prev_root


def _teardown(new_engine, prev_root):
    settings.raw_data_path = prev_root
    new_engine.dispose()
    dbmod.engine = engine
    dbmod.SessionLocal = SessionLocal


def _client(tmp_path: Path) -> TestClient:
    c = TestClient(app)
    c.post("/login", data={"user": "admin", "password": "admin"}, follow_redirects=False)
    return c


def _bcct_dir(tmp_path: Path) -> Path:
    return tmp_path / "DN_MULTI" / "2024" / "HANG_CHI_TIET"


def _names(tmp_path: Path) -> set[str]:
    d = _bcct_dir(tmp_path)
    return {p.name for p in d.glob("*.xlsx")} if d.exists() else set()


def test_two_bcct_files_in_one_submit_both_land_on_disk(tmp_path):
    new_engine, prev_root = _setup(tmp_path)
    try:
        client = _client(tmp_path)
        r = client.post(
            "/companies/DN_MULTI/upload",
            data={"year": "2024"},
            files=[
                ("bcct", ("BCCT_F1.xlsx", _xlsx_bytes("F1"), _XLSX)),
                ("bcct", ("BCCT_F3.xlsx", _xlsx_bytes("F3"), _XLSX)),
            ],
            follow_redirects=False,
        )
        assert r.status_code == 303
        assert _names(tmp_path) == {"BCCT_F1.xlsx", "BCCT_F3.xlsx"}
    finally:
        _teardown(new_engine, prev_root)


def test_a_second_submit_adds_a_bcct_file_instead_of_replacing(tmp_path):
    new_engine, prev_root = _setup(tmp_path)
    try:
        client = _client(tmp_path)
        for name in ("BCCT_F1.xlsx", "BCCT_F3.xlsx"):
            r = client.post(
                "/companies/DN_MULTI/upload",
                data={"year": "2024"},
                files=[("bcct", (name, _xlsx_bytes(name), _XLSX))],
                follow_redirects=False,
            )
            assert r.status_code == 303
        assert _names(tmp_path) == {"BCCT_F1.xlsx", "BCCT_F3.xlsx"}
    finally:
        _teardown(new_engine, prev_root)


def test_both_bcct_files_are_registered_as_documents(tmp_path):
    new_engine, prev_root = _setup(tmp_path)
    try:
        client = _client(tmp_path)
        client.post(
            "/companies/DN_MULTI/upload",
            data={"year": "2024"},
            files=[
                ("bcct", ("BCCT_F1.xlsx", _xlsx_bytes("F1"), _XLSX)),
                ("bcct", ("BCCT_F3.xlsx", _xlsx_bytes("F3"), _XLSX)),
            ],
            follow_redirects=False,
        )
        with dbmod.SessionLocal() as db:
            c = db.query(Company).filter_by(code="DN_MULTI").first()
            rows = db.query(DataFile).filter_by(company_id=c.id, slot="bcct").all()
            assert {r.original_filename for r in rows} == {"BCCT_F1.xlsx", "BCCT_F3.xlsx"}
    finally:
        _teardown(new_engine, prev_root)


def test_upload_form_lets_the_officer_pick_several_bcct_files(tmp_path):
    """Không có `multiple` trên ô BCCT thì trình duyệt chỉ gửi 1 file — sửa backend vô ích."""
    new_engine, prev_root = _setup(tmp_path)
    try:
        client = _client(tmp_path)
        html = client.get("/companies/DN_MULTI/upload?year=2024").text

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
    finally:
        _teardown(new_engine, prev_root)


def test_m15_still_replaces_the_previous_file(tmp_path):
    new_engine, prev_root = _setup(tmp_path)
    try:
        client = _client(tmp_path)
        for name in ("Mau15_cu.xlsx", "Mau15_moi.xlsx"):
            client.post(
                "/companies/DN_MULTI/upload",
                data={"year": "2024"},
                files=[("m15", (name, _xlsx_bytes(name), _XLSX))],
                follow_redirects=False,
            )
        bcqt = tmp_path / "DN_MULTI" / "2024" / "BCQT"
        assert {p.name for p in bcqt.glob("*.xlsx")} == {"M15_NVL_2024.xlsx"}
    finally:
        _teardown(new_engine, prev_root)


def test_uploading_the_same_bcct_name_twice_replaces_that_one_file(tmp_path):
    """Tải lại đúng tên cũ = sửa file đó, không sinh bản thứ hai."""
    new_engine, prev_root = _setup(tmp_path)
    try:
        client = _client(tmp_path)
        for marker in ("cu", "moi"):
            client.post(
                "/companies/DN_MULTI/upload",
                data={"year": "2024"},
                files=[("bcct", ("BCCT_F1.xlsx", _xlsx_bytes(marker), _XLSX))],
                follow_redirects=False,
            )
        assert _names(tmp_path) == {"BCCT_F1.xlsx"}
        wrote = (_bcct_dir(tmp_path) / "BCCT_F1.xlsx").read_bytes()
        assert wrote == _xlsx_bytes("moi")
    finally:
        _teardown(new_engine, prev_root)
