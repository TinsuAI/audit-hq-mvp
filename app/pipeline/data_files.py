"""Đồng bộ registry `data_files` với filesystem + ghi trạng thái parse.

Trang quản lý tài liệu đọc trạng thái từ bảng `data_files` (bền vững) thay vì chỉ
suy từ dòng đã ingest. Hai việc chính:

- ``sync_data_files`` — quét thư mục ``raw_root/<CODE>/<năm>/{BCQT,DINH_MUC,HANG_CHI_TIET}``
  rồi upsert registry theo ``stored_path``; xoá dòng registry mà file đã không còn trên
  đĩa (reconcile xoá ngoài app). Reconcile được file demo có sẵn chưa nằm trong registry.
- ``record_parse_result`` — sau mỗi lần ingest, cập nhật ``parse_status`` / ``row_count`` /
  ``parse_message`` từ ``IngestStats`` (+ ``UploadDiagnosis`` nếu có).
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Company, DataFile, DataFileStatus
from app.models.data_file import SLOT_SUBDIR
from app.settings import settings

_EXCEL_EXT = {".xls", ".xlsx"}


def _classify_slot(subdir: str, filename: str) -> str | None:
    """Phân loại 1 file vào slot (m15/m15a/m16/bcct) theo thư mục + tên.

    Mirror logic ``app/pipeline/discover.py`` để registry khớp với cái thực sự
    được ingest. Trả None cho file không nhận diện được (mẫu cũ TT38 trong BCQT).
    """
    if subdir == "DINH_MUC":
        return "m16"
    if subdir == "HANG_CHI_TIET":
        return "bcct"
    if subdir == "BCQT":
        normalized = filename.lower().replace(" ", "_").replace(".", "_").replace("-", "_")
        if "nvl" in normalized or "npl" in normalized:
            return "m15"
        if "_sp" in normalized or normalized.startswith("sp_") or "spgsql" in normalized:
            return "m15a"
        return None
    return None


def _iter_company_files(raw_root: Path, code: str):
    """Yield (year:int, slot:str, abs_path:Path) cho mọi file Excel nhận diện được."""
    company_dir = raw_root / code
    if not company_dir.is_dir():
        return
    for year_dir in company_dir.iterdir():
        if not year_dir.is_dir() or not year_dir.name.isdigit():
            continue  # bỏ qua multi_year và thư mục không phải năm
        year = int(year_dir.name)
        for subdir in ("BCQT", "DINH_MUC", "HANG_CHI_TIET"):
            sub = year_dir / subdir
            if not sub.is_dir():
                continue
            for p in sorted(sub.iterdir()):
                if not p.is_file() or p.suffix.lower() not in _EXCEL_EXT:
                    continue
                slot = _classify_slot(subdir, p.name)
                if slot is None:
                    continue
                yield year, slot, p


def sync_data_files(session: Session, company: Company, raw_root: Path | None = None) -> None:
    """Upsert registry từ filesystem + prune dòng mà file đã biến mất.

    Commit ngay (thao tác độc lập). Giữ nguyên ``parse_status`` của dòng đã có
    (chỉ refresh size/tên) để không mất trạng thái parse từ lần ingest trước.
    """
    raw_root = Path(raw_root or settings.raw_data_path)

    existing = {
        row.stored_path: row
        for row in session.scalars(
            select(DataFile).where(DataFile.company_id == company.id)
        ).all()
    }
    seen: set[str] = set()

    for year, slot, abs_path in _iter_company_files(raw_root, company.code):
        try:
            rel = str(abs_path.relative_to(raw_root))
        except ValueError:
            rel = str(abs_path)
        seen.add(rel)
        size = abs_path.stat().st_size
        row = existing.get(rel)
        if row is None:
            session.add(DataFile(
                company_id=company.id,
                period_year=year,
                slot=slot,
                original_filename=abs_path.name,
                stored_path=rel,
                size_bytes=size,
                parse_status=DataFileStatus.PENDING,
            ))
        else:
            row.original_filename = abs_path.name
            row.size_bytes = size
            row.period_year = year
            row.slot = slot

    # Prune: file không còn trên đĩa → xoá khỏi registry.
    for rel, row in existing.items():
        if rel not in seen:
            session.delete(row)

    session.commit()


def _slot_status(
    slot: str, row_count: int, diag_errors: list, diag_warnings: list,
) -> tuple[str, str | None]:
    """Suy (parse_status, message) cho 1 slot từ row_count + diagnosis."""
    slot_errors = [d for d in diag_errors if d.slot == slot]
    if slot_errors:
        return DataFileStatus.ERROR, slot_errors[0].detail
    slot_warnings = [d for d in diag_warnings if d.slot == slot]
    if slot_warnings:
        return DataFileStatus.WARNING, slot_warnings[0].detail
    if row_count <= 0:
        return DataFileStatus.WARNING, "Nạp được 0 dòng — kiểm tra lại cấu trúc file."
    return DataFileStatus.OK, None


def record_parse_result(
    session: Session,
    company: Company,
    year: int,
    stats,
    diagnosis=None,
) -> None:
    """Cập nhật parse_status / row_count / message cho file của (DN, năm) sau ingest.

    ``stats`` là ``IngestStats``; ``diagnosis`` là ``UploadDiagnosis`` (tuỳ chọn).
    Áp trạng thái theo slot cho mọi DataFile của slot đó (BCCT có thể nhiều file →
    cùng tổng số dòng của slot).
    """
    row_counts = {
        "m15": getattr(stats, "m15_rows", 0),
        "m15a": getattr(stats, "m15a_rows", 0),
        "m16": getattr(stats, "m16_rows", 0),
        "bcct": getattr(stats, "bcct_rows", 0),
    }
    diag_errors = diagnosis.errors if diagnosis else []
    diag_warnings = diagnosis.warnings if diagnosis else []

    rows = session.scalars(
        select(DataFile).where(
            DataFile.company_id == company.id,
            DataFile.period_year == year,
        )
    ).all()
    for row in rows:
        rc = row_counts.get(row.slot, 0)
        status, message = _slot_status(row.slot, rc, diag_errors, diag_warnings)
        row.parse_status = status
        row.parse_message = message
        row.row_count = rc
    session.commit()


def files_by_year_slot(session: Session, company: Company) -> dict[int, dict[str, list[DataFile]]]:
    """Gom DataFile của 1 DN thành {year: {slot: [DataFile, ...]}} cho template."""
    rows = session.scalars(
        select(DataFile)
        .where(DataFile.company_id == company.id)
        .order_by(DataFile.period_year.desc(), DataFile.slot, DataFile.original_filename)
    ).all()
    out: dict[int, dict[str, list[DataFile]]] = defaultdict(lambda: defaultdict(list))
    for r in rows:
        out[r.period_year][r.slot].append(r)
    return out


__all__ = [
    "SLOT_SUBDIR",
    "files_by_year_slot",
    "record_parse_result",
    "sync_data_files",
]
