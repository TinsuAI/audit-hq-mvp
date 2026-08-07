"""Tests HTTP — cổng review ở trang Tài liệu + tự advance khi upload file `verified`.

- Banner cổng review liệt kê cột `needs_review` + check bị ảnh hưởng (cảnh báo, không chặn).
- Upload file mọi cột `verified` (bố cục chuẩn khớp tiêu đề) tự advance `analyzed→parsed`
  KHÔNG thêm thao tác — đường whitelist/demo chảy suốt.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy.pool import StaticPool

import app.database as dbmod
from app.adapters.evidence import HEADER_MATCHED, NEEDS_REVIEW, POSITION_ONLY
from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import Company, DataFile, DataFileStatus, NvlBalance
from app.pipeline.data_files import _evidence_columns
from app.pipeline.data_screen import ACTION_OPEN_FILE, build_data_screen
from app.pipeline.file_page import file_page_url
from app.pipeline.readiness import BLOCKER_FILE
from app.settings import settings
from tests.helpers import drain_jobs, last_job_result, upload_and_ingest

# Header bố cục chuẩn Mẫu 15 (cột đúng vị trí BALANCE_EXPECT: mã=1, tồn đầu=4,
# nhập=5, xuất SX=8, tồn cuối=10) → mọi cột khớp tiêu đề → verified.
_M15_HEADER = [
    "STT", "Mã NVL", "Tên NVL", "Đơn vị tính", "Tồn đầu kỳ", "Nhập trong kỳ",
    "Tái xuất", "Chuyển mục đích sử dụng", "Xuất sản xuất", "Xuất khác", "Tồn cuối kỳ",
]


def _clean_m15_bytes() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "BCQT_NVL"
    for _ in range(8):
        ws.append([None] * len(_M15_HEADER))
    ws.append(_M15_HEADER)
    # Cân đối: 10 + 100 - 0 - 0 - 80 - 0 = 30 (khớp đẳng thức M15).
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
    # ingest() commit qua tên `SessionLocal` bind lúc import — swap để commit vào
    # engine test, nếu không dòng nạp rơi vào engine gốc và không kiểm được.
    ingmod.SessionLocal = new_session
    Base.metadata.create_all(new_engine)
    with new_session() as db:
        seed_default_admin(db, "admin", "admin")
        db.add(Company(code="DN_GATE", name="Gate", tax_id="1"))
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


def test_a_column_still_to_confirm_becomes_a_blocker_pointing_at_that_file(tmp_path):
    """Từ #86 màn dữ liệu không in danh sách cột nữa — nó nêu vướng mắc và mở đúng
    trang file, nơi cột `needs_review` và các kiểm tra đọc cột đó vẫn được liệt kê
    (`tests/test_data_files/test_review_screen.py`). Khẳng định ở mức dữ liệu."""
    new_engine, prev_root = _setup(tmp_path)
    try:
        # File thật trên đĩa để sync_data_files không prune (chỉ .stat, không mở).
        rel = "DN_GATE/2024/BCQT/M15_NVL_2024.xlsx"
        abs_path = tmp_path / rel
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_bytes(b"x")

        ev = dict.fromkeys(
            ["material_code", "opening_qty", "import_qty", "reexport_qty",
             "repurpose_qty", "other_out_qty", "closing_qty"], HEADER_MATCHED,
        )
        ev["production_out_qty"] = POSITION_ONLY  # cột riêng lẻ, chỉ vị trí → needs_review
        cols = _evidence_columns("m15", ev)
        with dbmod.SessionLocal() as db:
            c = db.query(Company).filter_by(code="DN_GATE").first()
            db.add(DataFile(
                company_id=c.id, period_year=2024, slot="m15",
                original_filename="M15_NVL_2024.xlsx", stored_path=rel,
                size_bytes=1, parse_status=DataFileStatus.ANALYZED, row_count=3,
                parse_layout="standard",
                parse_detail=json.dumps({"columns": cols, "review": NEEDS_REVIEW},
                                        ensure_ascii=False),
            ))
            db.commit()

        with dbmod.SessionLocal() as db:
            c = db.query(Company).filter_by(code="DN_GATE").first()
            file_id = db.query(DataFile).filter_by(company_id=c.id, slot="m15").first().id
            row = next(
                p for p in build_data_screen(db, c).periods if p.year == 2024
            )
            item = next(
                i
                for g in row.groups
                for i in g.items
                if i.kind == BLOCKER_FILE and i.slot == "m15"
            )

        # Cổng dừng lượt nạp và ghi 0 dòng, nên vướng mắc phải dẫn tới trang file —
        # bảo cán bộ "tải lên" ở đây là bảo họ tải lại thứ vừa tải.
        assert item.action.kind == ACTION_OPEN_FILE
        assert item.action.url == file_page_url("DN_GATE", file_id)
    finally:
        _teardown(new_engine, prev_root)


def test_verified_upload_auto_advances_to_parsed(tmp_path):
    new_engine, prev_root = _setup(tmp_path)
    try:
        client = TestClient(app)
        _login(client)
        r = upload_and_ingest(client, "DN_GATE", "Mau15_NVL.xlsx", _clean_m15_bytes())
        assert r.status_code == 303
        assert r.headers["location"].endswith("/documents#ky-2024")
        drain_jobs()
        # Tự advance → job kết luận đã nạp, KHÔNG dừng chờ xác nhận.
        assert last_job_result("ingest")["status"] == "ok"

        with dbmod.SessionLocal() as db:
            c = db.query(Company).filter_by(code="DN_GATE").first()
            row = db.query(DataFile).filter_by(company_id=c.id, slot="m15").first()
            assert row.parse_status == DataFileStatus.OK  # parsed, không dừng ở analyzed
            assert row.parse_detail_obj.get("review") == "verified"
            # Dòng dữ liệu đã commit (không chỉ dry-run).
            assert db.query(NvlBalance).filter_by(company_id=c.id, period_year=2024).count() == 3
    finally:
        _teardown(new_engine, prev_root)
