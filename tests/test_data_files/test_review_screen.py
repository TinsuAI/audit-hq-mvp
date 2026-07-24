"""Tests HTTP — màn review map cột (WS1-3b, ADR #18).

- GET render map cột đề xuất + badge evidence + ô sửa cột `needs_review` của file `analyzed`.
- POST xác nhận ghi map qua store #6, re-ingest (commit) → file advance `analyzed→parsed`,
  cột resolve `officer-confirmed` → `verified`, cổng review clear.
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
from app.models import Company, DataFile, DataFileStatus, NvlBalance
from app.pipeline.data_files import year_review_gate
from app.pipeline.saved_map import load_column_map
from app.settings import settings

# Header Mẫu 15 bố cục chuẩn NHƯNG cột xuất SX (col 8) dùng nhãn không khớp từ khoá
# → `production_out_qty` chỉ `balance-checked`; cột này dùng RIÊNG LẺ (C4.3/C5.1) nên
# `balance-checked` KHÔNG đủ → `needs_review` (đúng để bật cổng review).
_M15_HEADER = [
    "STT", "Mã NVL", "Tên NVL", "Đơn vị tính", "Tồn đầu kỳ", "Nhập trong kỳ",
    "Tái xuất", "Chuyển mục đích sử dụng", "Cột 8", "Xuất khác", "Tồn cuối kỳ",
]


def _needs_review_m15_bytes() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "BCQT_NVL"
    for _ in range(8):
        ws.append([None] * len(_M15_HEADER))
    ws.append(_M15_HEADER)
    # Cân đối: 10 + 100 - 0 - 0 - 80 - 0 = 30 → đẳng thức khớp (balance-checked).
    for i in range(3):
        ws.append([i + 1, f"MAT{i}", "Tên", "KG", 10, 100, 0, 0, 80, 0, 30])
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
    new_session = dbmod.sessionmaker(bind=new_engine, autoflush=False, autocommit=False, future=True)
    dbmod.engine = new_engine
    dbmod.SessionLocal = new_session
    ingmod.SessionLocal = new_session
    Base.metadata.create_all(new_engine)
    with new_session() as db:
        seed_default_admin(db, "admin", "admin")
        db.add(Company(code="DN_REV", name="Rev", tax_id="1"))
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


def _upload_needs_review(client) -> None:
    r = client.post(
        "/companies/DN_REV/upload",
        data={"year": "2024"},
        files={"m15": ("Mau15_NVL.xlsx", _needs_review_m15_bytes(),
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        follow_redirects=False,
    )
    assert r.status_code == 303
    # Dừng ở cổng review → redirect báo "cần xác nhận", KHÔNG tự nạp.
    assert "x%C3%A1c+nh%E1%BA%ADn" in r.headers["location"]


def test_review_get_renders_map_and_badges(tmp_path):
    new_engine, prev_root = _setup(tmp_path)
    try:
        client = TestClient(app)
        _login(client)
        _upload_needs_review(client)

        with dbmod.SessionLocal() as db:
            c = db.query(Company).filter_by(code="DN_REV").first()
            row = db.query(DataFile).filter_by(company_id=c.id, slot="m15").first()
            assert row.parse_status == DataFileStatus.ANALYZED  # dừng, chưa parsed
            fid = row.id

        html = client.get(f"/companies/DN_REV/documents/file/{fid}/review").text
        assert "Xuất sản xuất" in html          # nhãn field production_out_qty
        assert "Khớp đẳng thức" in html          # badge evidence balance-checked
        assert "Cần xác nhận" in html            # trạng thái review cột
        assert 'name="col_production_out_qty"' in html  # ô sửa cột needs_review
    finally:
        _teardown(new_engine, prev_root)


def test_review_confirm_saves_map_and_advances_to_parsed(tmp_path):
    new_engine, prev_root = _setup(tmp_path)
    try:
        client = TestClient(app)
        _login(client)
        _upload_needs_review(client)

        with dbmod.SessionLocal() as db:
            c = db.query(Company).filter_by(code="DN_REV").first()
            cid = c.id
            row = db.query(DataFile).filter_by(company_id=c.id, slot="m15").first()
            fid = row.id
            detail = row.parse_detail_obj
            form_sig = detail["form_signature"]
            base_map = detail["column_map"]
            # Trước xác nhận: cổng review còn bật.
            assert year_review_gate(db, c, 2024) is not None
            # Chưa commit dòng nào (dry-run).
            assert db.query(NvlBalance).filter_by(company_id=cid, period_year=2024).count() == 0

        data = {f"col_{field}": str(idx) for field, idx in base_map.items()}
        r = client.post(
            f"/companies/DN_REV/documents/file/{fid}/review",
            data=data, follow_redirects=False,
        )
        assert r.status_code == 303
        assert "/documents" in r.headers["location"]
        assert "msg=" in r.headers["location"]

        with dbmod.SessionLocal() as db:
            c = db.query(Company).filter_by(code="DN_REV").first()
            saved = load_column_map(db, c.id, "m15", form_sig)
            assert saved is not None
            assert saved.column_map_obj == base_map
            row = db.query(DataFile).filter_by(company_id=c.id, slot="m15").first()
            assert row.parse_status == DataFileStatus.OK  # advance analyzed→parsed
            assert row.parse_detail_obj["review"] == "verified"  # officer-confirmed
            # Cổng review đã clear + dòng dữ liệu đã commit.
            assert year_review_gate(db, c, 2024) is None
            assert db.query(NvlBalance).filter_by(company_id=c.id, period_year=2024).count() == 3
    finally:
        _teardown(new_engine, prev_root)
