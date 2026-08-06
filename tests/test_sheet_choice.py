"""Trang tính (sheet) được đọc: ghi lại, hiện ra, và cho cán bộ chọn lại.

Adapter tự chấm điểm chọn trang, nhưng trước đây không ghi lại đã chọn trang nào
và màn xác nhận cột luôn vẽ trang ĐẦU workbook. File BCCT của 006 có `Tổng hợp`
đứng trước `Chi tiết` đang được nạp, nên cán bộ xác nhận chỉ số cột trên một trang
khác hẳn trang được đọc. Test giữ ba điều: registry ghi trang đã đọc, lưới xem
trước là trang đó, và ô chọn trang ghim được lựa chọn của cán bộ cho lượt nạp sau.
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
from app.models import Company, DataFile, NvlBalance
from app.settings import settings
from tests.helpers import drain_jobs

_M15_HEADER = [
    "STT", "Mã NVL", "Tên NVL", "Đơn vị tính", "Tồn đầu kỳ", "Nhập trong kỳ",
    "Tái xuất", "Chuyển mục đích sử dụng", "Xuất sản xuất", "Xuất khác", "Tồn cuối kỳ",
]


def _sheet_rows(ws, codes: list[str]) -> None:
    for _ in range(8):
        ws.append([None] * len(_M15_HEADER))
    ws.append(_M15_HEADER)
    for i, code in enumerate(codes):
        ws.append([i + 1, code, "Tên", "KG", 10, 100, 0, 0, 80, 0, 30])


def _two_sheet_m15() -> bytes:
    """Workbook có HAI trang cùng bố cục Mẫu 15, mã hàng khác nhau.

    Trang `BCQT_NVL` (tên khớp mẫu) đứng SAU trang phụ, nên "trang đầu workbook"
    và "trang được đọc" là hai trang khác nhau — đúng tình huống của file 006.
    """
    wb = Workbook()
    ws_extra = wb.active
    ws_extra.title = "Phụ lục"
    ws_extra.append(["Trang phụ, không phải biểu Mẫu 15"])
    _sheet_rows(wb.create_sheet("BCQT_NVL"), ["MAT0", "MAT1", "MAT2"])
    _sheet_rows(wb.create_sheet("BCQT_NVL_KY_SAU"), ["ALT0"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _setup(tmp_path: Path):
    import app.pipeline.ingest as ingmod
    from app.auth_users import seed_default_admin

    new_engine = dbmod.create_engine(
        "sqlite://", connect_args={"check_same_thread": False},
        poolclass=StaticPool, future=True,
    )
    new_session = dbmod.sessionmaker(
        bind=new_engine, autoflush=False, autocommit=False, future=True
    )
    dbmod.engine = new_engine
    dbmod.SessionLocal = new_session
    ingmod.SessionLocal = new_session
    Base.metadata.create_all(new_engine)
    with new_session() as db:
        seed_default_admin(db, "admin", "admin")
        db.add(Company(code="DN_SHEET", name="Sheet", tax_id="1"))
        db.commit()
    prev_root = settings.raw_data_path
    settings.raw_data_path = str(tmp_path)
    return new_engine, prev_root


def _teardown(new_engine, prev_root):
    import app.pipeline.ingest as ingmod
    settings.raw_data_path = prev_root
    new_engine.dispose()
    dbmod.engine = engine
    dbmod.SessionLocal = SessionLocal
    ingmod.SessionLocal = SessionLocal


def _login(client):
    client.post("/login", data={"user": "admin", "password": "admin"}, follow_redirects=False)


def _upload(client):
    r = client.post(
        "/companies/DN_SHEET/upload",
        data={"year": "2024"},
        files={"m15": ("Mau15_NVL.xlsx", _two_sheet_m15(),
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        follow_redirects=False,
    )
    assert r.status_code == 303
    drain_jobs()


def _m15_row():
    with dbmod.SessionLocal() as db:
        c = db.query(Company).filter_by(code="DN_SHEET").first()
        row = db.query(DataFile).filter_by(company_id=c.id, slot="m15").first()
        return row.id, row.parse_detail_obj, row.sheet_override


def _codes() -> set[str]:
    with dbmod.SessionLocal() as db:
        c = db.query(Company).filter_by(code="DN_SHEET").first()
        return {
            b.material_code
            for b in db.query(NvlBalance).filter_by(company_id=c.id, period_year=2024)
        }


def test_registry_records_the_sheet_that_was_read(tmp_path):
    new_engine, prev_root = _setup(tmp_path)
    try:
        client = TestClient(app)
        _login(client)
        _upload(client)

        _fid, detail, override = _m15_row()
        assert detail["sheet"] == "BCQT_NVL"   # KHÔNG phải "Phụ lục" (trang đầu)
        assert override is None                # tự nhận diện, chưa ai ghim
        assert _codes() == {"MAT0", "MAT1", "MAT2"}
    finally:
        _teardown(new_engine, prev_root)


def test_review_screen_previews_the_parsed_sheet_and_offers_the_others(tmp_path):
    new_engine, prev_root = _setup(tmp_path)
    try:
        client = TestClient(app)
        _login(client)
        _upload(client)
        fid, _detail, _ = _m15_row()

        html = client.get(f"/companies/DN_SHEET/documents/file/{fid}/review").text
        assert 'name="sheet"' in html
        assert "Trang tính (sheet) được đọc" in html
        # Lưới xem trước là trang ĐƯỢC ĐỌC, và mọi trang đều chọn lại được.
        assert "trang tính <strong>BCQT_NVL</strong>" in html
        assert '<option value="Phụ lục"' in html
        assert '<option value="BCQT_NVL_KY_SAU"' in html
        assert "MAT0" in html                  # ô dữ liệu của trang được đọc
        assert "Trang phụ, không phải biểu Mẫu 15" not in html
    finally:
        _teardown(new_engine, prev_root)


def test_officer_can_pin_another_sheet_and_reingest_reads_it(tmp_path):
    new_engine, prev_root = _setup(tmp_path)
    try:
        client = TestClient(app)
        _login(client)
        _upload(client)
        fid, detail, _ = _m15_row()

        data = {f"col_{f}": str(i) for f, i in detail["column_map"].items()}
        data["sheet"] = "BCQT_NVL_KY_SAU"
        r = client.post(f"/companies/DN_SHEET/documents/file/{fid}/review",
                        data=data, follow_redirects=False)
        assert r.status_code == 303
        drain_jobs()

        _fid, detail_after, override = _m15_row()
        assert override == "BCQT_NVL_KY_SAU"          # ghim lại cho lượt nạp sau
        assert detail_after["sheet"] == "BCQT_NVL_KY_SAU"
        assert _codes() == {"ALT0"}                    # dòng đọc từ trang đã ghim
    finally:
        _teardown(new_engine, prev_root)


def test_confirming_without_touching_the_sheet_keeps_auto_detection(tmp_path):
    """Bấm xác nhận mà không đụng ô trang tính KHÔNG được lặng lẽ ghim trang."""
    new_engine, prev_root = _setup(tmp_path)
    try:
        client = TestClient(app)
        _login(client)
        _upload(client)
        fid, detail, _ = _m15_row()

        data = {f"col_{f}": str(i) for f, i in detail["column_map"].items()}
        data["sheet"] = ""                             # ô để trống = tự nhận diện
        client.post(f"/companies/DN_SHEET/documents/file/{fid}/review",
                    data=data, follow_redirects=False)
        drain_jobs()

        _fid, detail_after, override = _m15_row()
        assert override is None
        assert detail_after["sheet"] == "BCQT_NVL"
        assert _codes() == {"MAT0", "MAT1", "MAT2"}
    finally:
        _teardown(new_engine, prev_root)
