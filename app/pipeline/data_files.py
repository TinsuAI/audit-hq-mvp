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

import json
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.evidence import (
    FIELD_LABEL_VI,
    NEEDS_REVIEW,
    OFFICER_CONFIRMED,
    SOURCE_LABEL_VI,
    VERIFIED,
)
from app.adapters.templates import MATCH_OFFICER
from app.checks.registry import checks_reading, review_state
from app.models import Company, DataFile, DataFileStatus
from app.models.data_file import SLOT_SUBDIR
from app.pipeline.discover import content_slots
from app.pipeline.saved_map import resolve_officer_confirmed
from app.settings import settings

_EXCEL_EXT = {".xls", ".xlsx"}

# Thứ tự hiển thị cột ở badge truy nguồn mỗi slot.
_EVIDENCE_ORDER: dict[str, tuple[str, ...]] = {
    "m15": ("material_code", "opening_qty", "import_qty", "reexport_qty", "repurpose_qty",
            "production_out_qty", "other_out_qty", "closing_qty"),
    "m15a": ("product_code", "opening_qty", "intake_qty", "repurpose_qty", "export_qty",
             "other_out_qty", "closing_qty"),
    "m16": ("material_code", "norm_qty"),
    "bcct": ("declaration_no", "declaration_date", "customs_code", "item_code",
             "hs_code", "quantity", "unit", "unit_price", "value_total",
             "company_tax_id", "company_name"),
}


def _evidence_columns(slot: str, evidence: dict[str, str]) -> list[dict]:
    """Dựng danh sách cột {field, nhãn, nguồn, trạng thái review} cho badge + lưu."""
    order = _EVIDENCE_ORDER.get(slot) or tuple(evidence)
    cols: list[dict] = []
    for field in order:
        src = evidence.get(field)
        if src is None:
            continue
        cols.append({
            "field": field,
            "label": FIELD_LABEL_VI.get(field, field),
            "evidence": src,
            "evidence_label": SOURCE_LABEL_VI.get(src, src),
            "review": review_state(slot, field, src),
        })
    return cols


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


def _excel_files(d: Path) -> list[Path]:
    if not d.is_dir():
        return []
    return sorted(p for p in d.iterdir() if p.is_file() and p.suffix.lower() in _EXCEL_EXT)


def _iter_company_files(raw_root: Path, code: str):
    """Yield (year, slot, abs_path) cho mọi file Excel nhận diện được.

    Lặp lại ĐÚNG thuật toán của `discover`: tên file trước, dò nội dung CHỈ cho slot
    mà tên không lấp được. Registry lệch với discover thì trang tài liệu báo
    "chưa có file" trong khi dữ liệu của chính file đó đã nạp — và dò nội dung cho
    mọi file thì mỗi lần vào trang phải mở lại từng workbook.
    """
    company_dir = raw_root / code
    if not company_dir.is_dir():
        return
    for year_dir in sorted(company_dir.iterdir()):
        if not year_dir.is_dir() or not year_dir.name.isdigit():
            continue  # bỏ qua multi_year và thư mục không phải năm
        year = int(year_dir.name)
        bcqt = _excel_files(year_dir / "BCQT")
        dinh_muc = _excel_files(year_dir / "DINH_MUC")
        for p in dinh_muc:
            yield year, "m16", p
        for p in _excel_files(year_dir / "HANG_CHI_TIET"):
            yield year, "bcct", p

        named: dict[str, list[Path]] = {"m15": [], "m15a": []}
        for p in bcqt:
            slot = _classify_slot("BCQT", p.name)
            if slot in named:
                named[slot].append(p)
                yield year, slot, p

        unfilled = [s for s in ("m15", "m15a") if not named[s]]
        if not dinh_muc:
            unfilled.append("m16")
        if not unfilled:
            continue
        for p in bcqt:
            for slot in content_slots(p, year):
                if slot in unfilled:
                    yield year, slot, p


def sync_data_files(session: Session, company: Company, raw_root: Path | None = None) -> None:
    """Upsert registry từ filesystem + prune dòng mà file đã biến mất.

    Commit ngay (thao tác độc lập). Giữ nguyên ``parse_status`` của dòng đã có
    (chỉ refresh size/tên) để không mất trạng thái parse từ lần ingest trước.
    """
    raw_root = Path(raw_root or settings.raw_data_path)

    existing = {
        (row.stored_path, row.slot): row
        for row in session.scalars(
            select(DataFile).where(DataFile.company_id == company.id)
        ).all()
    }
    seen: set[tuple[str, str]] = set()

    for year, slot, abs_path in _iter_company_files(raw_root, company.code):
        try:
            rel = str(abs_path.relative_to(raw_root))
        except ValueError:
            rel = str(abs_path)
        seen.add((rel, slot))
        size = abs_path.stat().st_size
        row = existing.get((rel, slot))
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
    for key, row in existing.items():
        if key not in seen:
            session.delete(row)

    session.commit()


def _slot_status(
    slot: str, row_count: int, diag_errors: list, diag_warnings: list,
    committed: bool = True,
) -> tuple[str, str | None]:
    """Suy (parse_status lifecycle, message) cho 1 slot từ row_count + diagnosis.

    Lifecycle (ADR #18): dry-run parse xong → `analyzed`; commit dòng → `parsed`
    (``OK``); đọc/nạp hỏng → `error`. WARNING không còn là status — cảnh báo cột
    nằm ở trục review (`parse_detail.review`). Diag warning giữ lại làm message tư
    vấn (không đổi lifecycle); file 0 dòng coi như `error` vì chưa dùng được.
    """
    slot_errors = [d for d in diag_errors if d.slot == slot]
    if slot_errors:
        return DataFileStatus.ERROR, slot_errors[0].detail
    if row_count <= 0:
        return DataFileStatus.ERROR, "Nạp được 0 dòng — kiểm tra lại cấu trúc file."
    ok_status = DataFileStatus.OK if committed else DataFileStatus.ANALYZED
    slot_warnings = [d for d in diag_warnings if d.slot == slot]
    if slot_warnings:
        return ok_status, slot_warnings[0].detail  # advisory: giữ message, giữ lifecycle
    return ok_status, None


def record_parse_result(
    session: Session,
    company: Company,
    year: int,
    stats,
    diagnosis=None,
    committed: bool = True,
) -> None:
    """Cập nhật parse_status / row_count / message cho file của (DN, năm) sau ingest.

    ``stats`` là ``IngestStats``; ``diagnosis`` là ``UploadDiagnosis`` (tuỳ chọn).
    Áp trạng thái theo slot cho mọi DataFile của slot đó (BCCT có thể nhiều file →
    cùng tổng số dòng của slot).

    ``committed`` = False khi ghi kết quả dry-run parse (ADR #18): lifecycle dừng ở
    `analyzed` (chưa commit dòng), cổng review đọc `parse_detail.review` từ đây rồi
    quyết định tự advance hay dừng. Bằng chứng cột + review vẫn tính như thường.
    """
    row_counts = {
        "m15": getattr(stats, "m15_rows", 0),
        "m15a": getattr(stats, "m15a_rows", 0),
        "m16": getattr(stats, "m16_rows", 0),
        "bcct": getattr(stats, "bcct_rows", 0),
    }
    provenance = getattr(stats, "provenance", None) or {}
    sheets = getattr(stats, "sheets", None) or {}
    diag_errors = diagnosis.errors if diagnosis else []
    diag_warnings = diagnosis.warnings if diagnosis else []
    # File nằm trong HANG_CHI_TIET nhưng không phải báo cáo chi tiết tờ khai đã bị bỏ
    # qua lúc nạp — không được hiển thị "ok" kèm số dòng của các file khác.
    skipped = set(getattr(stats, "bcct_skipped", None) or ())

    rows = session.scalars(
        select(DataFile).where(
            DataFile.company_id == company.id,
            DataFile.period_year == year,
        )
    ).all()
    for row in rows:
        if row.slot == "bcct" and row.original_filename in skipped:
            row.parse_status = DataFileStatus.ERROR
            row.parse_message = (
                "Không phải báo cáo chi tiết tờ khai (thiếu số tờ khai / ngày ĐK) — "
                "đã bỏ qua khi nạp, không đóng góp dòng nào."
            )
            row.row_count = 0
            continue
        rc = row_counts.get(row.slot, 0)
        status, message = _slot_status(row.slot, rc, diag_errors, diag_warnings, committed)
        row.parse_status = status
        row.parse_message = message
        row.row_count = rc
        prov = provenance.get(row.slot)
        prov_evidence = getattr(prov, "evidence", None) if prov is not None else None
        prov_layout = getattr(prov, "layout", "standard") if prov is not None else "standard"
        # Map đã lưu cho (DN, slot, vân tay form) khớp → các cột resolve
        # `officer-confirmed` → `verified`, cổng review tự advance (WS1-3, ADR #18).
        if prov_evidence:
            form_sig = (getattr(prov, "detail", None) or {}).get("form_signature")
            prov_evidence = resolve_officer_confirmed(
                session, company.id, row.slot, form_sig, prov_evidence,
            )
        # Ghi provenance cho MỌI file có bằng chứng cột (kể cả bố cục chuẩn) — badge
        # truy nguồn hiện nguồn + trạng thái review từng cột (WS1, ADR #18).
        has_prov = prov is not None and (prov_layout != "standard" or prov_evidence)
        detail = dict(prov.detail) if has_prov else {}
        if has_prov and prov_evidence:
            columns = _evidence_columns(row.slot, prov_evidence)
            detail["columns"] = columns
            detail["review"] = (
                NEEDS_REVIEW if any(c["review"] == NEEDS_REVIEW for c in columns)
                else VERIFIED
            )
        # Trang tính đã đọc — theo TỪNG FILE. Không có nó thì màn review vẽ lưới ô của
        # trang đầu workbook trong khi parser đọc trang khác (BCCT 006: `Tổng hợp` vs
        # `Chi tiết`), cán bộ xác nhận chỉ số cột trên đúng cái lưới sai đó.
        sheet = sheets.get(f"{row.slot}:{Path(row.stored_path).name}")
        if sheet:
            detail["sheet"] = sheet
        if detail:
            row.parse_layout = prov_layout if has_prov else None
            row.parse_detail = json.dumps(detail, ensure_ascii=False)
            # Họ biểu + cách chọn cột lên CỘT riêng (ADR #23 T3) — trang tài liệu lọc
            # và đếm theo hai giá trị này, không parse JSON để đọc.
            row.template_id = detail.get("template_id")
            row.match_source = (
                MATCH_OFFICER
                if any(src == OFFICER_CONFIRMED for src in (prov_evidence or {}).values())
                else detail.get("match_source")
            )
        else:
            row.parse_layout = None
            row.parse_detail = None
            row.template_id = None
            row.match_source = None
    session.commit()


# --- Cổng review vòng đời file (ADR #18) -----------------------------------


@dataclass(frozen=True)
class ReviewGateColumn:
    """Một cột `needs_review` + các check đọc nó (cho banner cổng review)."""

    slot: str
    field: str
    label: str
    checks: tuple[str, ...]
    file_id: int = 0  # DataFile.id — link banner tới màn review của file này


@dataclass(frozen=True)
class ReviewGate:
    """Tập cột `needs_review` của (DN, năm) + check bị ảnh hưởng — dữ liệu banner."""

    columns: tuple[ReviewGateColumn, ...] = ()

    @property
    def check_codes(self) -> list[str]:
        """Mã check bị ảnh hưởng (gộp trùng, sắp xếp) — banner nêu 'ảnh hưởng: …'."""
        seen: set[str] = set()
        for col in self.columns:
            seen.update(col.checks)
        return sorted(seen)


def review_gate_for_files(files: Iterable[DataFile]) -> ReviewGate | None:
    """Dựng cổng review từ các DataFile: gom cột `needs_review` + check đọc chúng.

    Đọc `parse_detail.review` mỗi file (trục review, ĐỘC LẬP lifecycle) — file có
    thể `parsed` mà vẫn `needs_review`. Trả None khi không cột nào cần xác nhận.
    """
    columns: list[ReviewGateColumn] = []
    for f in files:
        detail = f.parse_detail_obj
        if detail.get("review") != NEEDS_REVIEW:
            continue
        for c in detail.get("columns", ()):
            if c.get("review") != NEEDS_REVIEW:
                continue
            field_name = c.get("field", "")
            columns.append(ReviewGateColumn(
                slot=f.slot,
                field=field_name,
                label=c.get("label", field_name),
                checks=tuple(checks_reading(f.slot, field_name)),
                file_id=f.id,
            ))
    if not columns:
        return None
    return ReviewGate(columns=tuple(columns))


def year_review_gate(session: Session, company: Company, year: int) -> ReviewGate | None:
    """Cổng review cho (DN, năm) đọc thẳng từ registry — dùng ở luồng upload."""
    rows = session.scalars(
        select(DataFile).where(
            DataFile.company_id == company.id,
            DataFile.period_year == year,
        )
    ).all()
    return review_gate_for_files(rows)


def should_stop_for_review(gate: ReviewGate | None, has_saved_map: bool = False) -> bool:
    """Quyết định `analyzed→parsed`: DỪNG chờ cán bộ (True) hay TỰ advance (False).

    Đây là điểm quyết định duy nhất của cổng review (ADR #18): mọi cột `verified`
    (``gate is None``) → tự advance, đường whitelist/demo chảy suốt không thêm click.
    WS1-3 (#6) truyền ``has_saved_map=True`` khi có map đã lưu theo (DN, vân tay form)
    khớp file — coi như `verified` → tự advance dù bằng chứng thô là `needs_review`.
    """
    if gate is None:
        return False
    if has_saved_map:
        return False
    return True


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
    "ReviewGate",
    "ReviewGateColumn",
    "files_by_year_slot",
    "record_parse_result",
    "review_gate_for_files",
    "should_stop_for_review",
    "sync_data_files",
    "year_review_gate",
]
