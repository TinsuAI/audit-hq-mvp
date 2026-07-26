"""2SỔ-4 (#19) — ingest book-aware: đọc book per-file từ data_files, gom theo sổ.

Thay workaround "2 company → collapse" + guard cũ. Book per settlement file (cột
`data_files.book`, gán ở review WS1); tờ khai ghi MỘT lần (book=NULL). Không tag book
(CLI/script) → book=NULL → 002/006 không đổi. Xem ADR #19 Revision — UI + upload.
"""

from __future__ import annotations

import io
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from openpyxl import Workbook
from sqlalchemy import func, select
from sqlalchemy.pool import StaticPool

from app.models import Company, DataFile, DeclarationLine, NvlBalance

_M15_HEADER = [
    "STT", "Mã NVL", "Tên NVL", "Đơn vị tính", "Tồn đầu kỳ", "Nhập trong kỳ",
    "Tái xuất", "Chuyển mục đích sử dụng", "Xuất sản xuất", "Xuất khác", "Tồn cuối kỳ",
]


def _write_m15(path: Path, codes: list[str]) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "BCQT_NVL"
    for _ in range(8):
        ws.append([None] * len(_M15_HEADER))
    ws.append(_M15_HEADER)
    for i, code in enumerate(codes):
        ws.append([i + 1, code, "Tên", "KG", 10, 100, 0, 0, 80, 0, 30])
    path.parent.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    wb.save(buf)
    path.write_bytes(buf.getvalue())


def _write_bcct(path: Path, item_codes: list[str]) -> None:
    """BCCT tối thiểu: header row 9 (Số TK/Ngày ĐK/Mã loại hình/Mã hiệu PTVC), data từ row 10."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    width = 51
    for _ in range(8):
        ws.append([None] * width)
    header = [None] * width
    header[1], header[2], header[3], header[7] = "Số TK", "Ngày ĐK", "Mã loại hình", "Mã hiệu PTVC"
    ws.append(header)
    for code in item_codes:
        row = [None] * width
        row[1] = "1234567890"           # declaration_no (khớp ^\d{9,13}$)
        row[2] = date(2024, 6, 15)      # declaration_date (trong kỳ dương lịch 2024)
        row[3] = "E11"
        row[20] = code                  # item_code
        row[26] = 50                    # quantity
        row[27] = "PCE"                 # unit
        ws.append(row)
    path.parent.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    wb.save(buf)
    path.write_bytes(buf.getvalue())


def _fresh_db():
    import app.database as dbmod
    import app.pipeline.ingest as ingmod
    from app.database import Base

    new_engine = dbmod.create_engine(
        "sqlite://", connect_args={"check_same_thread": False},
        poolclass=StaticPool, future=True,
    )
    new_session = dbmod.sessionmaker(bind=new_engine, autoflush=False, autocommit=False, future=True)
    dbmod.engine = new_engine
    dbmod.SessionLocal = new_session
    ingmod.SessionLocal = new_session
    Base.metadata.create_all(new_engine)
    return new_engine, new_session


def _restore_db(new_engine):
    from app.database import SessionLocal, engine
    new_engine.dispose()
    import app.database as dbmod
    import app.pipeline.ingest as ingmod
    dbmod.engine = engine
    dbmod.SessionLocal = SessionLocal
    ingmod.SessionLocal = SessionLocal


# ─────────────────────── _plan_settlement_files fallback ───────────────────────

def test_plan_fallback_single_book_when_no_tags():
    """Không có data_files book → dùng file discover, book=NULL (hành vi CLI cũ)."""
    from app.pipeline.ingest import _plan_settlement_files

    new_engine, new_session = _fresh_db()
    try:
        with new_session() as db:
            c = Company(code="DN_CLI", name="X", tax_id="1")
            db.add(c)
            db.commit()
            cid = c.id
            m15_obj = SimpleNamespace(rows=[1, 2], source_file="x")
            plan = _plan_settlement_files(
                db, cid, 2024, {"m15": m15_obj, "m15a": None, "m16": None}, Path("/tmp")
            )
            assert plan == {"m15": [(m15_obj, None)], "m15a": [], "m16": []}
    finally:
        _restore_db(new_engine)


# ─────────────────────── multi-book integration ───────────────────────

def _seed_two_book_files(db, tmp_path, code="DN_MB"):
    """2 file M15 EPE/GC + 1 BCCT; đăng ký data_files với book tag."""
    from app.settings import settings

    base = tmp_path / code / "2024"
    _write_m15(base / "BCQT" / "NVL_EPE.xlsx", ["EPE1", "EPE2", "EPE3"])
    _write_m15(base / "BCQT" / "NVL_GC.xlsx", ["GC1", "GC2"])
    _write_bcct(base / "HANG_CHI_TIET" / "BCCT.xlsx", ["ITEMA", "ITEMB"])
    settings.raw_data_path = str(tmp_path)

    c = Company(code=code, name="Pháp nhân 2 sổ", tax_id="0901051747")
    db.add(c)
    db.flush()
    db.add_all([
        DataFile(company_id=c.id, period_year=2024, slot="m15", book="EPE",
                 original_filename="NVL_EPE.xlsx", stored_path=f"{code}/2024/BCQT/NVL_EPE.xlsx"),
        DataFile(company_id=c.id, period_year=2024, slot="m15", book="GC",
                 original_filename="NVL_GC.xlsx", stored_path=f"{code}/2024/BCQT/NVL_GC.xlsx"),
    ])
    db.commit()
    return c


def test_ingest_tags_book_per_file_and_declarations_once(tmp_path):
    from app.pipeline.ingest import ingest
    from app.settings import settings

    prev_root = settings.raw_data_path
    new_engine, new_session = _fresh_db()
    try:
        with new_session() as db:
            _seed_two_book_files(db, tmp_path, "DN_MB")

        ingest("DN_MB", 2024, raw_root=tmp_path)

        with new_session() as db:
            c = db.scalar(select(Company).where(Company.code == "DN_MB"))
            epe = {r.material_code for r in db.scalars(
                select(NvlBalance).where(NvlBalance.company_id == c.id, NvlBalance.book == "EPE"))}
            gc = {r.material_code for r in db.scalars(
                select(NvlBalance).where(NvlBalance.company_id == c.id, NvlBalance.book == "GC"))}
            assert epe == {"EPE1", "EPE2", "EPE3"}
            assert gc == {"GC1", "GC2"}
            # Không dòng NVL nào book=NULL (đều gắn sổ).
            assert db.scalar(select(func.count()).select_from(NvlBalance).where(
                NvlBalance.company_id == c.id, NvlBalance.book.is_(None))) == 0
            # Tờ khai ghi MỘT lần (book=NULL trên declaration; 2 dòng, KHÔNG nhân đôi
            # dù có 2 file settlement).
            decl = db.scalar(select(func.count()).select_from(DeclarationLine).where(
                DeclarationLine.company_id == c.id))
            assert decl == 2
    finally:
        settings.raw_data_path = prev_root
        _restore_db(new_engine)


def test_reingest_multi_book_preserves_both_books(tmp_path):
    """Guard retired: re-ingest pháp nhân nhiều sổ KHÔNG xoá mất sổ (full reprocess)."""
    from app.pipeline.ingest import ingest
    from app.settings import settings

    prev_root = settings.raw_data_path
    new_engine, new_session = _fresh_db()
    try:
        with new_session() as db:
            _seed_two_book_files(db, tmp_path, "DN_MB")

        ingest("DN_MB", 2024, raw_root=tmp_path)
        ingest("DN_MB", 2024, raw_root=tmp_path)   # re-ingest — không raise, không mất sổ

        with new_session() as db:
            c = db.scalar(select(Company).where(Company.code == "DN_MB"))
            books = set(db.scalars(select(NvlBalance.book).where(
                NvlBalance.company_id == c.id).distinct()))
            assert books == {"EPE", "GC"}           # cả 2 sổ còn nguyên
            # Idempotent: không nhân đôi.
            assert db.scalar(select(func.count()).select_from(NvlBalance).where(
                NvlBalance.company_id == c.id)) == 5
            assert db.scalar(select(func.count()).select_from(DeclarationLine).where(
                DeclarationLine.company_id == c.id)) == 2
    finally:
        settings.raw_data_path = prev_root
        _restore_db(new_engine)


def test_ingest_no_tags_is_book_null_and_idempotent(tmp_path):
    """Đường CLI (không data_files book) → book=NULL; re-ingest identical (002/006)."""
    from app.pipeline.ingest import ingest
    from app.settings import settings

    prev_root = settings.raw_data_path
    new_engine, new_session = _fresh_db()
    try:
        base = tmp_path / "DN_ONE" / "2024"
        _write_m15(base / "BCQT" / "NVL.xlsx", ["A", "B", "C"])
        settings.raw_data_path = str(tmp_path)

        ingest("DN_ONE", 2024, raw_root=tmp_path)
        with new_session() as db:
            c = db.scalar(select(Company).where(Company.code == "DN_ONE"))
            rows = db.scalars(select(NvlBalance).where(NvlBalance.company_id == c.id)).all()
            assert len(rows) == 3
            assert all(r.book is None for r in rows)     # single-book: book=NULL

        ingest("DN_ONE", 2024, raw_root=tmp_path)         # re-ingest identical
        with new_session() as db:
            c = db.scalar(select(Company).where(Company.code == "DN_ONE"))
            n = db.scalar(select(func.count()).select_from(NvlBalance).where(
                NvlBalance.company_id == c.id))
            assert n == 3
    finally:
        settings.raw_data_path = prev_root
        _restore_db(new_engine)


# ─────────────────── an toàn: không âm thầm gộp sổ / mất sổ ───────────────────


def test_reingest_refuses_to_merge_books_when_tags_were_pruned(tmp_path):
    """data_files bị prune mất tag book nhưng DB đã có 2 sổ → phải DỪNG, không nạp đè.

    Đây là kịch bản đang có thật trên máy local: company 9 có 0 dòng data_files, nên
    lượt ingest kế tiếp rơi vào nhánh không-tag và dựng lại 004 thành một sổ gộp.
    """
    import pytest

    from app.pipeline.ingest import IngestPlanError, ingest
    from app.settings import settings

    prev_root = settings.raw_data_path
    new_engine, new_session = _fresh_db()
    try:
        with new_session() as db:
            _seed_two_book_files(db, tmp_path, "DN_MB")
        ingest("DN_MB", 2024, raw_root=tmp_path)

        # Prune xoá mọi đăng ký (vd thư mục nguồn vắng mặt lúc sync).
        with new_session() as db:
            c = db.scalar(select(Company).where(Company.code == "DN_MB"))
            for r in db.scalars(select(DataFile).where(DataFile.company_id == c.id)):
                db.delete(r)
            db.commit()

        with pytest.raises(IngestPlanError, match="EPE"):
            ingest("DN_MB", 2024, raw_root=tmp_path)

        # Dữ liệu cũ còn NGUYÊN — dừng trước khi wipe.
        with new_session() as db:
            c = db.scalar(select(Company).where(Company.code == "DN_MB"))
            books = set(db.scalars(select(NvlBalance.book).where(
                NvlBalance.company_id == c.id).distinct()))
            assert books == {"EPE", "GC"}
            assert db.scalar(select(func.count()).select_from(NvlBalance).where(
                NvlBalance.company_id == c.id)) == 5
    finally:
        settings.raw_data_path = prev_root
        _restore_db(new_engine)


def test_reingest_refuses_when_a_registered_book_file_is_missing(tmp_path):
    """Thiếu file của một sổ → DỪNG, không được xoá sổ đó rồi im lặng nạp thiếu."""
    import pytest

    from app.pipeline.ingest import IngestPlanError, ingest
    from app.settings import settings

    prev_root = settings.raw_data_path
    new_engine, new_session = _fresh_db()
    try:
        with new_session() as db:
            _seed_two_book_files(db, tmp_path, "DN_MB")
        ingest("DN_MB", 2024, raw_root=tmp_path)

        (tmp_path / "DN_MB" / "2024" / "BCQT" / "NVL_GC.xlsx").unlink()

        with pytest.raises(IngestPlanError, match="NVL_GC"):
            ingest("DN_MB", 2024, raw_root=tmp_path)

        with new_session() as db:
            c = db.scalar(select(Company).where(Company.code == "DN_MB"))
            books = set(db.scalars(select(NvlBalance.book).where(
                NvlBalance.company_id == c.id).distinct()))
            assert books == {"EPE", "GC"}, "sổ GC bị xoá dù lượt nạp đã hỏng"
    finally:
        settings.raw_data_path = prev_root
        _restore_db(new_engine)
