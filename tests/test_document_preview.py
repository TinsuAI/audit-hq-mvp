"""Preview file Excel đã upload — đọc raw, scoping, sheet, 404."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from app.main import app
from app.models import Company, DataFile
from app.settings import settings

REL = "DN_PV/2024/BCQT/M15_NVL_2024.xlsx"


@pytest.fixture
def env(app_db, tmp_path, monkeypatch):
    """DN + một file Excel thật trong thư mục dữ liệu tạm; trả (client, file_id)."""
    # Kho đệm xem trước vào thư mục tạm, không vào `db-data/` của máy dev.
    monkeypatch.setattr(settings, "preview_cache_path", tmp_path / "kho-dem", raising=False)

    abs_path = app_db.raw_root / REL
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "BCQT_NPL"
    ws.append(["SENTINEL_CELL", "Cột B"])
    ws.append(["NVL-001", 42])
    wb.save(abs_path)

    with app_db.SessionLocal() as db:
        c = Company(code="DN_PV", name="PV", tax_id="1")
        db.add(c)
        db.flush()
        db.add(DataFile(
            company_id=c.id, period_year=2024, slot="m15",
            original_filename="M15_NVL_2024.xlsx", stored_path=REL,
            size_bytes=abs_path.stat().st_size, parse_status="ok", row_count=1,
        ))
        db.commit()
        fid = db.query(DataFile).first().id

    client = TestClient(app)
    client.post("/login", data={"user": "admin", "password": "admin"}, follow_redirects=False)
    return client, fid


def test_preview_serves_the_raw_cells_through_the_cell_window(env):
    """Ô không còn dựng sẵn trong HTML — lưới lấy qua điểm cuối cửa sổ.

    Khẳng định cũ dò `SENTINEL_CELL` trong HTML chết cùng lúc trang đổi sang lưới,
    nên chuyển sang đúng chỗ dữ liệu bây giờ đi qua: trang giao địa chỉ, điểm cuối
    giao ô.
    """
    client, fid = env
    page = client.get(f"/companies/DN_PV/documents/file/{fid}/preview")
    assert page.status_code == 200
    assert f'data-cells-url="/companies/DN_PV/documents/file/{fid}/cells"' in page.text

    cells = client.get(f"/companies/DN_PV/documents/file/{fid}/cells")

    assert cells.status_code == 200
    body = cells.json()
    assert body["rows"][0][0] == "SENTINEL_CELL"
    assert body["rows"][1][0] == "NVL-001"
    assert body["sheet_names"] == ["BCQT_NPL"]


def test_preview_404_wrong_file(env):
    client, _ = env
    assert client.get("/companies/DN_PV/documents/file/99999/preview").status_code == 404
