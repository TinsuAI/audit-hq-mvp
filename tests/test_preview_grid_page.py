"""Trang xem file dựng LƯỚI CUỘN — máy chủ không còn đọc ô, chỉ giao mốc cho lưới.

Ba hạn mức cũ (100 dòng · 40 cột · 25MB) chặn ở mức FILE nên 11/493 file không xem
được và 52/170 trang tính bị cắt cột. Trang mới chỉ gắn điểm neo + dữ liệu chú giải;
ô lấy qua điểm cuối cửa sổ, nên trang phải dựng được cả với file 26MB lẫn file mà
bộ đọc không mở nổi.

Khẳng định vào THUỘC TÍNH markup (chính nó là hợp đồng với lưới), cộng đúng hai
nhãn công tắc — câu chữ của hai nhãn đó là thứ người dùng đã duyệt.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models import Company, DataFile
from app.settings import settings
from tests.excel_fixtures import write_xlsx

REL_DIR = "DN_PV/2025/HANG_CHI_TIET"

TOGGLE_MAPPED = "Hiện cột hệ thống đang đọc"
TOGGLE_FORMULA = "Hiện công thức trong ô"


@pytest.fixture
def env(app_db, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "preview_cache_path", tmp_path / "kho-dem", raising=False)
    (tmp_path / REL_DIR).mkdir(parents=True, exist_ok=True)
    with app_db.SessionLocal() as db:
        db.add(Company(code="DN_PV", name="PV", tax_id="1"))
        db.commit()
    client = TestClient(app)
    client.post("/login", data={"user": "admin", "password": "admin"}, follow_redirects=False)
    return client, tmp_path


def _register(name: str, *, parse_detail: dict | None = None, sheet_override: str | None = None) -> int:
    import app.database as dbmod

    rel = f"{REL_DIR}/{name}"
    with dbmod.SessionLocal() as db:
        c = db.query(Company).filter_by(code="DN_PV").one()
        row = DataFile(
            company_id=c.id, period_year=2025, slot="m15",
            original_filename=name, stored_path=rel,
            size_bytes=(Path(settings.raw_data_path) / rel).stat().st_size,
            parse_status="parsed", row_count=1,
            sheet_override=sheet_override,
            parse_detail=json.dumps(parse_detail) if parse_detail else None,
        )
        db.add(row)
        db.commit()
        return row.id


def _mount(text: str) -> dict[str, str]:
    """Thuộc tính `data-*` của điểm neo lưới."""
    tag = re.search(r"<div[^>]*id=\"cell-grid\"[^>]*>", text)
    assert tag, "trang không có điểm neo lưới"
    return {
        m.group(1): html.unescape(m.group(3))
        for m in re.finditer(r"data-([a-z-]+)=([\"'])(.*?)\2", tag.group(0))
    }


def _preview(client, fid: int, **params) -> str:
    from urllib.parse import urlencode

    q = f"?{urlencode(params)}" if params else ""
    r = client.get(f"/companies/DN_PV/documents/file/{fid}/preview{q}")
    assert r.status_code == 200
    return r.text


def test_the_page_hands_the_grid_its_cell_window_endpoint_and_sheet(env):
    client, tmp = env
    write_xlsx(tmp / REL_DIR / "a.xlsx", [["Mã", 1]])
    fid = _register("a.xlsx")

    attrs = _mount(_preview(client, fid, sheet=2))

    assert attrs["cells-url"] == f"/companies/DN_PV/documents/file/{fid}/cells"
    assert attrs["sheet"] == "2"


def test_the_columns_the_parser_reads_come_with_the_page_for_the_first_toggle(env):
    client, tmp = env
    write_xlsx(tmp / REL_DIR / "b.xlsx", [["Mã", "Tên", "SL"]])
    fid = _register("b.xlsx", parse_detail={
        "sheet": "BCQT_NPL",
        "column_map": {"material_code": 0, "material_name": 2, "opening_qty": 7},
        "columns": [
            {"field": "material_code", "label": "Mã nguyên liệu", "review": "verified"},
            {"field": "material_name", "label": "Tên nguyên liệu", "review": "verified"},
            {"field": "opening_qty", "label": "Tồn đầu kỳ", "review": "needs_review"},
        ],
    })

    attrs = _mount(_preview(client, fid))
    mapped = json.loads(attrs["mapped-columns"])

    assert mapped["0"]["label"] == "Mã nguyên liệu"
    assert mapped["2"]["field"] == "material_name"
    # Nhãn hiện theo ngoại lệ, dựng từ `BasisColumn.labels` (#123): cột còn chờ xác nhận
    # mang một nhãn trục *việc còn lại*, cột không còn việc gì không mang nhãn nào. Cờ
    # `needs` cũ là bộ từ vựng riêng của lưới, nằm ngoài ba trục — xem
    # `tests/test_grid_accessible_shape.py` cho phép so hai đầu.
    assert [lb["axis"] for lb in mapped["7"]["labels"]] == ["work"]
    assert mapped["0"]["labels"] == []
    # Chú giải chỉ đúng trên trang tính parser đọc — lưới phải biết trang nào.
    assert attrs["parsed-sheet"] == "BCQT_NPL"


def test_a_sheet_the_officer_pinned_wins_over_the_sheet_the_parser_last_read(env):
    client, tmp = env
    write_xlsx(tmp / REL_DIR / "c.xlsx", [["Mã", 1]])
    fid = _register(
        "c.xlsx", sheet_override="Chi tiết",
        parse_detail={"sheet": "Tổng hợp", "column_map": {"material_code": 0}, "columns": []},
    )

    assert _mount(_preview(client, fid))["parsed-sheet"] == "Chi tiết"


def test_a_file_never_parsed_still_gets_a_grid_with_no_column_marks(env):
    client, tmp = env
    write_xlsx(tmp / REL_DIR / "d.xlsx", [["Mã", 1]])
    fid = _register("d.xlsx")

    attrs = _mount(_preview(client, fid))

    assert json.loads(attrs["mapped-columns"]) == {}
    assert attrs["parsed-sheet"] == ""


def test_both_toggles_carry_the_wording_the_officer_approved(env):
    client, tmp = env
    write_xlsx(tmp / REL_DIR / "e.xlsx", [["Mã", 1]])
    fid = _register("e.xlsx")

    text = _preview(client, fid)

    assert TOGGLE_MAPPED in text
    assert TOGGLE_FORMULA in text


def test_a_file_over_the_old_25mb_cap_still_gets_a_grid(env):
    client, tmp = env
    path = tmp / REL_DIR / "to.xlsx"
    write_xlsx(path, [["Mã", 1]])
    with path.open("r+b") as fh:  # thưa: chỉ cần `st_size` vượt hạn mức cũ
        fh.truncate(26 * 1024 * 1024)
    fid = _register("to.xlsx")

    text = _preview(client, fid)

    assert _mount(text)["cells-url"]
    assert "25MB" not in text


def test_the_page_does_not_open_the_file_so_a_broken_one_still_renders(env):
    client, tmp = env
    (tmp / REL_DIR / "hong.xlsx").write_bytes(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
    fid = _register("hong.xlsx")

    assert _mount(_preview(client, fid))["cells-url"]


def test_a_missing_file_on_disk_is_still_a_404(env):
    client, tmp = env
    write_xlsx(tmp / REL_DIR / "f.xlsx", [["Mã", 1]])
    fid = _register("f.xlsx")
    (tmp / REL_DIR / "f.xlsx").unlink()

    r = client.get(f"/companies/DN_PV/documents/file/{fid}/preview")

    assert r.status_code == 404
