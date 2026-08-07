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

    prev = (settings.raw_data_path, settings.preview_cache_path)
    settings.raw_data_path = str(tmp_path)
    # Kho đệm xem trước vào thư mục tạm, không vào `db-data/` của máy dev.
    settings.preview_cache_path = tmp_path / "kho-dem"
    return new_engine, prev, fid


def _teardown(new_engine, prev):
    settings.raw_data_path, settings.preview_cache_path = prev
    new_engine.dispose()
    import app.database as dbmod
    dbmod.engine = engine
    dbmod.SessionLocal = SessionLocal


def _login(client):
    client.post("/login", data={"user": "admin", "password": "admin"}, follow_redirects=False)


def test_preview_serves_the_raw_cells_through_the_cell_window(tmp_path):
    """Ô không còn dựng sẵn trong HTML — lưới lấy qua điểm cuối cửa sổ.

    Khẳng định cũ dò `SENTINEL_CELL` trong HTML chết cùng lúc trang đổi sang lưới,
    nên chuyển sang đúng chỗ dữ liệu bây giờ đi qua: trang giao địa chỉ, điểm cuối
    giao ô.
    """
    new_engine, prev, fid = _setup(tmp_path)
    try:
        client = TestClient(app)
        _login(client)
        page = client.get(f"/companies/DN_PV/documents/file/{fid}/preview")
        assert page.status_code == 200
        assert f'data-cells-url="/companies/DN_PV/documents/file/{fid}/cells"' in page.text

        cells = client.get(f"/companies/DN_PV/documents/file/{fid}/cells")

        assert cells.status_code == 200
        body = cells.json()
        assert body["rows"][0][0] == "SENTINEL_CELL"
        assert body["rows"][1][0] == "NVL-001"
        assert body["sheet_names"] == ["BCQT_NPL"]
    finally:
        _teardown(new_engine, prev)


def test_preview_404_wrong_file(tmp_path):
    new_engine, prev, fid = _setup(tmp_path)
    try:
        client = TestClient(app)
        _login(client)
        assert client.get("/companies/DN_PV/documents/file/99999/preview").status_code == 404
    finally:
        _teardown(new_engine, prev)
