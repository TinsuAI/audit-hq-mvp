"""Preview file Excel đã upload — đọc raw, scoping, sheet, 404."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy.pool import StaticPool

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import Company, DataFile
from app.settings import settings


def _setup(tmp_path: Path):
    import app.database as dbmod
    from app.auth_users import seed_default_admin

    new_engine = dbmod.create_engine(
        "sqlite://", connect_args={"check_same_thread": False},
        poolclass=StaticPool, future=True,
    )
    new_session = dbmod.sessionmaker(bind=new_engine, autoflush=False, autocommit=False, future=True)
    dbmod.engine = new_engine
    dbmod.SessionLocal = new_session
    Base.metadata.create_all(new_engine)

    # File Excel thật trong raw_data_path tạm.
    rel = "DN_PV/2024/BCQT/M15_NVL_2024.xlsx"
    abs_path = tmp_path / rel
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "BCQT_NPL"
    ws.append(["SENTINEL_CELL", "Cột B"])
    ws.append(["NVL-001", 42])
    wb.save(abs_path)

    with new_session() as db:
        seed_default_admin(db, "admin", "admin")
        c = Company(code="DN_PV", name="PV", tax_id="1")
        db.add(c)
        db.flush()
        db.add(DataFile(
            company_id=c.id, period_year=2024, slot="m15",
            original_filename="M15_NVL_2024.xlsx", stored_path=rel,
            size_bytes=abs_path.stat().st_size, parse_status="ok", row_count=1,
        ))
        db.commit()
        fid = db.query(DataFile).first().id

    prev_root = settings.raw_data_path
    settings.raw_data_path = str(tmp_path)
    return new_engine, prev_root, fid


def _teardown(new_engine, prev_root):
    settings.raw_data_path = prev_root
    new_engine.dispose()
    import app.database as dbmod
    dbmod.engine = engine
    dbmod.SessionLocal = SessionLocal


def _login(client):
    client.post("/login", data={"user": "admin", "password": "admin"}, follow_redirects=False)


def test_preview_renders_raw_cells(tmp_path):
    new_engine, prev_root, fid = _setup(tmp_path)
    try:
        client = TestClient(app)
        _login(client)
        r = client.get(f"/companies/DN_PV/documents/file/{fid}/preview")
        assert r.status_code == 200
        # Nội dung raw + nhãn cột Excel + tên sheet.
        assert "SENTINEL_CELL" in r.text
        assert "NVL-001" in r.text
        assert ">A</th>" in r.text  # nhãn cột Excel
    finally:
        _teardown(new_engine, prev_root)


def test_preview_404_wrong_file(tmp_path):
    new_engine, prev_root, fid = _setup(tmp_path)
    try:
        client = TestClient(app)
        _login(client)
        assert client.get("/companies/DN_PV/documents/file/99999/preview").status_code == 404
    finally:
        _teardown(new_engine, prev_root)
