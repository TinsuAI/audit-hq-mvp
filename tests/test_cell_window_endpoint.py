"""Điểm cuối JSON trả cửa sổ ô — tham số cửa sổ, số tổng, cờ công thức, lỗi định dạng.

Khẳng định ở mức DỮ LIỆU (JSON), không dò chuỗi tiếng Việt trong HTML: lưới sẽ
do vé giao diện dựng, còn hợp đồng dữ liệu ở đây phải đứng yên.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Company, DataFile
from app.settings import settings
from tests.excel_fixtures import write_biff_xls, write_spreadsheetml, write_xlsx

REL_DIR = "DN_PV/2025/HANG_CHI_TIET"


@pytest.fixture
def env(app_db, tmp_path, monkeypatch):
    """Kho đệm tạm + DN mẫu trên DB tạm dùng chung; trả về client đã đăng nhập."""
    from app.adapters import cell_window

    (tmp_path / REL_DIR).mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(settings, "preview_cache_path", tmp_path / "kho-dem", raising=False)
    cell_window.reset_build_locks()

    with app_db.SessionLocal() as db:
        db.add(Company(code="DN_PV", name="PV", tax_id="1"))
        db.add(Company(code="DN_KHAC", name="Khác", tax_id="2"))
        db.commit()

    client = TestClient(app)
    client.post("/login", data={"user": "admin", "password": "admin"}, follow_redirects=False)
    return client, tmp_path


def _add_file(name: str, company: str = "DN_PV") -> int:
    import app.database as dbmod

    rel = f"{company}/2025/HANG_CHI_TIET/{name}"
    with dbmod.SessionLocal() as db:
        c = db.query(Company).filter_by(code=company).one()
        abs_path = Path(settings.raw_data_path) / rel
        row = DataFile(
            company_id=c.id, period_year=2025, slot="bcct",
            original_filename=name, stored_path=rel,
            size_bytes=abs_path.stat().st_size, parse_status="ok", row_count=1,
        )
        db.add(row)
        db.commit()
        return row.id


def _url(fid: int, company: str = "DN_PV", **params) -> str:
    from urllib.parse import urlencode

    q = urlencode(params)
    return f"/companies/{company}/documents/file/{fid}/cells" + (f"?{q}" if q else "")


def _make(tmp_path, name, writer, *args, **kwargs):
    path = tmp_path / REL_DIR / name
    writer(path, *args, **kwargs)
    return _add_file(name)


def test_window_returns_the_asked_range_and_the_real_totals(env):
    client, tmp = env
    rows = [[f"r{r}c{c}" for c in range(50)] for r in range(300)]
    fid = _make(tmp, "big.xlsx", write_xlsx, rows)

    r = client.get(_url(fid, sheet=0, row=100, rows=3, col=45, cols=5))

    assert r.status_code == 200
    body = r.json()
    assert body["total_rows"] == 300
    assert body["total_cols"] == 50
    assert body["row_start"] == 100 and body["col_start"] == 45
    assert body["rows"][0] == [f"r100c{c}" for c in range(45, 50)]
    assert body["sheet_index"] == 0


def test_window_goes_past_the_old_100_row_40_column_caps(env):
    client, tmp = env
    rows = [[f"r{r}c{c}" for c in range(257)] for r in range(150)]
    fid = _make(tmp, "wide.xlsx", write_xlsx, rows)

    r = client.get(_url(fid, row=140, rows=10, col=250, cols=10))

    body = r.json()
    assert body["total_cols"] == 257
    assert body["total_rows"] == 150
    assert body["rows"][0][6] == "r140c256"


def test_formula_flag_off_shows_the_number_and_never_the_formula_text(env):
    client, tmp = env
    fid = _make(
        tmp, "ct.xlsx", write_xlsx,
        [["Mã", "Tiền"], ["A1", None]],
        formulas={(1, 1): ("=B1*100", 28563550970.35)},
    )

    off = client.get(_url(fid, formulas=0)).json()
    on = client.get(_url(fid, formulas=1)).json()

    assert off["rows"][1][1] == 28563550970.35
    assert "formulas" not in off or off["formulas"] is None
    assert "=B1*100" not in str(off["rows"])
    # Bật công tắc: công thức hiện ra, giá trị vẫn còn.
    assert on["rows"][1][1] == 28563550970.35
    assert on["formulas"][1] == {"1": "=B1*100"}
    assert on["formulas_supported"] is True


def test_old_xls_says_it_cannot_read_formulas_instead_of_showing_an_empty_grid(env):
    client, tmp = env
    fid = _make(tmp, "cu.xls", write_biff_xls, [["Mã", "SL"], ["A1", 3]])

    body = client.get(_url(fid, formulas=1)).json()

    assert body["formulas_supported"] is False
    assert body["formula_note"]
    assert body["rows"][0][0] == "Mã"  # lưới vẫn có dữ liệu
    assert body["total_rows"] == 2


def test_spreadsheetml_under_an_xls_extension_is_served_not_refused(env):
    client, tmp = env
    fid = _make(
        tmp, "ton_kho.xls", write_spreadsheetml,
        [["Mã", "Tồn"], ["A1", 7]],
        formulas={(1, 1): "=RC[-1]"},
    )

    body = client.get(_url(fid, formulas=1)).json()

    assert body["format"] == "spreadsheetml"
    assert body["rows"][1][1] == 7
    assert body["formulas"][1] == {"1": "=RC[-1]"}


def test_sheet_names_and_a_second_sheet_are_reachable(env):
    client, tmp = env
    fid = _make(
        tmp, "nhieu.xlsx", write_xlsx, [["a", 1]],
        sheet_name="Tổng hợp", extra_sheets={"Chi tiết": [["b", 2], ["c", 3]]},
    )

    body = client.get(_url(fid, sheet=1)).json()

    assert body["sheet_names"] == ["Tổng hợp", "Chi tiết"]
    assert body["sheet_name"] == "Chi tiết"
    assert body["total_rows"] == 2


def test_a_sheet_index_past_the_end_is_a_clean_error(env):
    client, tmp = env
    fid = _make(tmp, "mot.xlsx", write_xlsx, [["a", 1]])

    r = client.get(_url(fid, sheet=9))

    assert r.status_code == 404
    assert "9" in r.json()["detail"]


def test_unsupported_format_names_the_detected_format_not_the_extension(env):
    client, tmp = env
    path = tmp / REL_DIR / "gia.xlsx"
    path.write_bytes(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
    fid = _add_file("gia.xlsx")

    r = client.get(_url(fid))

    assert r.status_code == 415
    body = r.json()
    assert "PDF" in body["detail"]
    assert ".xlsx" not in body["detail"]
    assert body["format_supported"] is False


def test_another_companys_file_is_not_readable(env):
    client, tmp = env
    fid = _make(tmp, "a.xlsx", write_xlsx, [["a", 1]])

    assert client.get(_url(fid, company="DN_KHAC")).status_code == 404


def test_a_missing_file_on_disk_is_a_404(env):
    client, tmp = env
    fid = _make(tmp, "a.xlsx", write_xlsx, [["a", 1]])
    (tmp / REL_DIR / "a.xlsx").unlink()

    assert client.get(_url(fid)).status_code == 404
