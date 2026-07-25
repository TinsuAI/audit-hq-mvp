"""2SỔ-5 (#22) — selector chọn sổ ở màn review WS1.

Selector chỉ ở file settlement (m15/m15a/m16); tờ khai không có. Default "1 sổ
(dùng chung)"=NULL; datalist gợi ý sổ đã có; normalize trim/upper. Set → ghi
data_files.book; confirm/re-ingest gom balances theo sổ. Xem ADR #19 Revision — upload.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy.pool import StaticPool

import app.database as dbmod
from app.books import normalize_book
from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import Company, DataFile, DataFileStatus, NvlBalance
from app.settings import settings

# Header Mẫu 15 chuẩn nhưng cột xuất SX (col 8) nhãn không khớp từ khoá → cột dùng
# riêng lẻ chỉ balance-checked → needs_review → cổng review bật (parse_detail có
# form_signature để confirm). Giống test_review_screen.
_M15_HEADER = [
    "STT", "Mã NVL", "Tên NVL", "Đơn vị tính", "Tồn đầu kỳ", "Nhập trong kỳ",
    "Tái xuất", "Chuyển mục đích sử dụng", "Cột 8", "Xuất khác", "Tồn cuối kỳ",
]


def _m15_bytes(codes: list[str]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "BCQT_NVL"
    for _ in range(8):
        ws.append([None] * len(_M15_HEADER))
    ws.append(_M15_HEADER)
    for i, code in enumerate(codes):
        ws.append([i + 1, code, "Tên", "KG", 10, 100, 0, 0, 80, 0, 30])
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
        db.add(Company(code="DN_SEL", name="Sel", tax_id="0901051747"))
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


def _upload_m15(client, codes: list[str], code="DN_SEL"):
    r = client.post(
        f"/companies/{code}/upload",
        data={"year": "2024"},
        files={"m15": ("Mau15_NVL.xlsx", _m15_bytes(codes),
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        follow_redirects=False,
    )
    assert r.status_code == 303


# ─────────────────────── normalize_book ───────────────────────

def test_normalize_book():
    assert normalize_book("epe") == "EPE"
    assert normalize_book("  gc ") == "GC"
    assert normalize_book("") is None
    assert normalize_book("   ") is None
    assert normalize_book(None) is None


# ─────────────────────── selector render ───────────────────────

def test_review_shows_book_selector_for_m15(tmp_path):
    new_engine, prev_root = _setup(tmp_path)
    try:
        client = TestClient(app)
        _login(client)
        _upload_m15(client, ["MAT0", "MAT1", "MAT2"])

        with dbmod.SessionLocal() as db:
            c = db.query(Company).filter_by(code="DN_SEL").first()
            fid = db.query(DataFile).filter_by(company_id=c.id, slot="m15").first().id

        html = client.get(f"/companies/DN_SEL/documents/file/{fid}/review").text
        assert 'name="book"' in html
        assert "Sổ quyết toán" in html
        assert "1 sổ (dùng chung)" in html          # default/placeholder
        assert 'value="EPE"' in html                 # datalist gợi ý EPE/GC
        assert 'value="GC"' in html
    finally:
        _teardown(new_engine, prev_root)


def test_review_no_selector_for_bcct(tmp_path):
    new_engine, prev_root = _setup(tmp_path)
    try:
        client = TestClient(app)
        _login(client)
        with dbmod.SessionLocal() as db:
            c = db.query(Company).filter_by(code="DN_SEL").first()
            detail = {
                "form_signature": "sig_bcct",
                "column_map": {"declaration_no": 1},
                "columns": [{"field": "declaration_no", "label": "Số TK",
                             "evidence": "header-matched", "review": "verified"}],
            }
            row = DataFile(
                company_id=c.id, period_year=2024, slot="bcct",
                original_filename="BCCT.xlsx", stored_path="DN_SEL/2024/HANG_CHI_TIET/BCCT.xlsx",
                parse_status=DataFileStatus.OK, parse_layout="labeled",
                parse_detail=json.dumps(detail, ensure_ascii=False),
            )
            db.add(row)
            db.commit()
            fid = row.id

        html = client.get(f"/companies/DN_SEL/documents/file/{fid}/review").text
        assert 'name="book"' not in html            # tờ khai: KHÔNG selector sổ
    finally:
        _teardown(new_engine, prev_root)


# ─────────────────────── confirm writes book + tags balance ───────────────────────

def test_confirm_writes_book_and_tags_balance(tmp_path):
    new_engine, prev_root = _setup(tmp_path)
    try:
        client = TestClient(app)
        _login(client)
        _upload_m15(client, ["MAT0", "MAT1", "MAT2"])

        with dbmod.SessionLocal() as db:
            c = db.query(Company).filter_by(code="DN_SEL").first()
            cid = c.id
            row = db.query(DataFile).filter_by(company_id=c.id, slot="m15").first()
            fid = row.id
            base_map = row.parse_detail_obj["column_map"]

        data = {f"col_{field}": str(idx) for field, idx in base_map.items()}
        data["book"] = "epe "                        # normalize → EPE
        r = client.post(
            f"/companies/DN_SEL/documents/file/{fid}/review",
            data=data, follow_redirects=False,
        )
        assert r.status_code == 303

        with dbmod.SessionLocal() as db:
            c = db.query(Company).filter_by(code="DN_SEL").first()
            row = db.query(DataFile).filter_by(company_id=c.id, slot="m15").first()
            assert row.book == "EPE"                 # ghi + normalize
            books = {b.book for b in db.query(NvlBalance).filter_by(company_id=cid, period_year=2024)}
            assert books == {"EPE"}                   # balances gắn book EPE
    finally:
        _teardown(new_engine, prev_root)


# ─────────────────────── E2E: gắn 2 sổ qua trình duyệt → branch A ───────────────────────

def test_two_books_tagged_via_browser_show_in_branch_a(tmp_path):
    """Đặt 2 file M15 trên đĩa → analyze → confirm mỗi file một sổ (EPE/GC) qua endpoint
    review → trang DN hiện strip hai sổ (branch A)."""
    from app.pipeline.data_files import sync_data_files

    new_engine, prev_root = _setup(tmp_path)
    try:
        client = TestClient(app)
        _login(client)

        bcqt = tmp_path / "DN_SEL" / "2024" / "BCQT"
        bcqt.mkdir(parents=True, exist_ok=True)
        (bcqt / "NVL_EPE_2024.xlsx").write_bytes(_m15_bytes(["EPE1", "EPE2", "EPE3"]))
        (bcqt / "NVL_GC_2024.xlsx").write_bytes(_m15_bytes(["GC1", "GC2"]))

        with dbmod.SessionLocal() as db:
            c = db.query(Company).filter_by(code="DN_SEL").first()
            sync_data_files(db, c)

        # Analyze + commit + set parse_detail (form_signature) cho cả 2 file m15.
        client.post("/companies/DN_SEL/documents/ingest", data={"year": "2024"},
                    follow_redirects=False)

        with dbmod.SessionLocal() as db:
            c = db.query(Company).filter_by(code="DN_SEL").first()
            rows = db.query(DataFile).filter_by(company_id=c.id, slot="m15").order_by(
                DataFile.original_filename).all()
            epe_file, gc_file = rows[0], rows[1]     # NVL_EPE_* trước NVL_GC_*
            base_map = epe_file.parse_detail_obj.get("column_map", {})
            epe_fid, gc_fid = epe_file.id, gc_file.id

        assert base_map, "cần parse_detail có column_map để confirm"
        payload = {f"col_{f}": str(i) for f, i in base_map.items()}
        client.post(f"/companies/DN_SEL/documents/file/{epe_fid}/review",
                    data={**payload, "book": "EPE"}, follow_redirects=False)
        client.post(f"/companies/DN_SEL/documents/file/{gc_fid}/review",
                    data={**payload, "book": "GC"}, follow_redirects=False)

        with dbmod.SessionLocal() as db:
            c = db.query(Company).filter_by(code="DN_SEL").first()
            books = {b.book for b in db.query(NvlBalance).filter_by(
                company_id=c.id, period_year=2024)}
            assert books == {"EPE", "GC"}            # cả 2 sổ gắn đúng

        html = client.get("/companies/DN_SEL?year=2024").text
        assert "Sổ EPE (chế xuất)" in html           # branch A strip hiện 2 sổ
        assert "Sổ GC (gia công)" in html
    finally:
        _teardown(new_engine, prev_root)
