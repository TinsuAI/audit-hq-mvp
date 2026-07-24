"""Ingest BCQT data into SQLite for one company × year.

Usage:
    python -m app.pipeline.ingest --company HONG_AN --year 2024
    python -m app.pipeline.ingest --company HONG_AN --year 2024 --dry-run
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete, func, select

from app.adapters import parse_bcct, parse_m15, parse_m15a, parse_m16
from app.adapters.sheet_select import SheetNotFound
from app.database import SessionLocal
from app.models import (
    Company,
    CompanyPeriod,
    DeclarationLine,
    Norm,
    NvlBalance,
    SpBalance,
)
from app.pipeline.discover import DiscoveredFiles, discover
from app.pipeline.period import default_bounds, in_period, resolve_period_bounds
from app.settings import settings


@dataclass
class IngestStats:
    company_code: str
    period_year: int
    m15_rows: int = 0
    m15a_rows: int = 0
    m16_rows: int = 0
    bcct_rows: int = 0
    bcct_other_year: int = 0  # dòng BCCT bị loại vì ngày tờ khai ngoài cửa sổ kỳ
    bcct_skipped: list[str] | None = None  # file trong HANG_CHI_TIET không phải BCCT
    files: dict[str, str | None] | None = None
    # slot → ParseProvenance (cách đọc file: standard/extended/labeled + bằng chứng).
    provenance: dict | None = None


def _get_or_create_company(
    session, code: str, tax_id: str | None, name: str | None, address: str | None
) -> Company:
    stmt = select(Company).where(Company.code == code)
    company = session.scalar(stmt)
    if company is None:
        company = Company(code=code, tax_id=tax_id, name=name, address=address)
        session.add(company)
        session.flush()
    else:
        company.tax_id = company.tax_id or tax_id
        company.name = company.name or name
        company.address = company.address or address
    return company


def _guard_single_book(session, company_id: int, year: int, company_code: str) -> None:
    """Chặn re-ingest pháp nhân nhiều sổ (book): ingest xoá sạch Tier-1 của (company, year)
    rồi nạp từ MỘT thư mục — sẽ huỷ mất các sổ khác. Xem ADR #19.
    """
    n_books = session.scalar(
        select(func.count(func.distinct(NvlBalance.book))).where(
            NvlBalance.company_id == company_id,
            NvlBalance.period_year == year,
            NvlBalance.book.is_not(None),
        )
    ) or 0
    if n_books > 0:
        raise ValueError(
            f"Pháp nhân {company_code} ({year}) có {n_books} sổ quyết toán (book) — "
            "không hỗ trợ re-ingest qua đường này (sẽ xoá mất sổ). Xem ADR #19."
        )


def ingest(company_code: str, year: int, raw_root: Path | None = None, dry_run: bool = False) -> IngestStats:
    raw_root = raw_root or settings.raw_data_path
    files: DiscoveredFiles = discover(company_code, year, Path(raw_root))

    stats = IngestStats(
        company_code=company_code,
        period_year=year,
        files={
            "m15": str(files.m15) if files.m15 else None,
            "m15a": str(files.m15a) if files.m15a else None,
            "m16": str(files.m16) if files.m16 else None,
            "bcct": ", ".join(p.name for p in files.bcct) if files.bcct else None,
        },
    )

    # `year` để chọn sheet: hai sheet cùng bố cục khác kỳ chỉ phân biệt được bằng kỳ.
    m15 = parse_m15(files.m15, year=year) if files.m15 else None
    m15a = parse_m15a(files.m15a, year=year) if files.m15a else None
    m16 = parse_m16(files.m16, year=year) if files.m16 else None
    # DN có thể tách tờ khai NK / XK thành nhiều file — parse + gộp tất cả. Thư mục
    # HANG_CHI_TIET đôi khi lẫn báo cáo KHÁC (vd "Báo cáo hàng hoá xuất khẩu" gộp theo
    # mã hàng, không có số tờ khai). Bỏ QUA từng file như vậy thay vì hỏng cả kỳ —
    # `diagnose_upload` vẫn báo riêng từng file cho cán bộ.
    bcct_files = []
    bcct_skipped: list[str] = []
    for bp in files.bcct:
        try:
            bcct_files.append(parse_bcct(bp, year=year))
        except SheetNotFound:
            bcct_skipped.append(bp.name)
    stats.bcct_skipped = bcct_skipped

    stats.m15_rows = len(m15.rows) if m15 else 0
    stats.m15a_rows = len(m15a.rows) if m15a else 0
    stats.m16_rows = len(m16.rows) if m16 else 0
    stats.provenance = {
        "m15": m15.provenance if m15 else None,
        "m15a": m15a.provenance if m15a else None,
        "m16": m16.provenance if m16 else None,
    }
    # BCCT: giữ dòng có ngày tờ khai trong cửa sổ kỳ [period_from, period_to]
    # (năm tài chính ≠ dương lịch). Dòng ngoài cửa sổ đếm vào bcct_other_year.
    bcct_all = [r for b in bcct_files for r in b.rows]
    company_meta = next((x.header for x in (m15, m15a, m16) if x is not None), None)

    if dry_run:
        # Xem trước: cửa sổ suy tự động (bản sửa tay cần session, không xét ở dry-run).
        pf, pt = default_bounds(company_meta, year)
        stats.bcct_rows = sum(1 for r in bcct_all if in_period(r.declaration_date, pf, pt))
        stats.bcct_other_year = len(bcct_all) - stats.bcct_rows
        return stats

    bcct_tax = next((b.company_tax_id for b in bcct_files if b.company_tax_id), None)
    bcct_name = next((b.company_name for b in bcct_files if b.company_name), None)
    tax_id = (company_meta.tax_id if company_meta else None) or bcct_tax
    name = (company_meta.name if company_meta else None) or bcct_name
    address = company_meta.address if company_meta else None

    with SessionLocal() as session:
        company = _get_or_create_company(session, company_code, tax_id, name, address)

        # Cửa sổ kỳ (from,to): bản sửa tay > tiêu đề file > dương lịch; ghi company_periods.
        period_from, period_to = resolve_period_bounds(session, company.id, year, company_meta)

        # WS3: bump data_version TRONG transaction ingest (ràng buộc advisor a) — version
        # + dữ liệu commit nguyên tử. `resolve_period_bounds` đảm bảo dòng CompanyPeriod
        # tồn tại (tạo nếu chưa, kể cả nhánh is_manual trả về dòng đã có).
        period_row = session.scalar(
            select(CompanyPeriod).where(
                CompanyPeriod.company_id == company.id,
                CompanyPeriod.period_year == year,
            )
        )
        if period_row is not None:
            period_row.data_version = (period_row.data_version or 0) + 1
        stats.bcct_rows = sum(
            1 for r in bcct_all if in_period(r.declaration_date, period_from, period_to)
        )
        stats.bcct_other_year = len(bcct_all) - stats.bcct_rows

        # Guard (ADR #19): pháp nhân nhiều sổ không nạp lại qua đường này — sẽ xoá mất sổ.
        _guard_single_book(session, company.id, year, company_code)

        # Wipe previous data for this company × year so re-ingest is idempotent.
        for model in (NvlBalance, SpBalance, Norm, DeclarationLine):
            session.execute(
                delete(model).where(
                    (model.company_id == company.id) & (model.period_year == year)
                )
            )

        if m15:
            session.add_all(
                NvlBalance(
                    company_id=company.id,
                    period_year=year,
                    row_no=r.row_no,
                    material_code=r.material_code,
                    material_name=r.material_name,
                    unit=r.unit,
                    opening_qty=r.opening_qty,
                    import_qty=r.import_qty,
                    reexport_qty=r.reexport_qty,
                    repurpose_qty=r.repurpose_qty,
                    production_out_qty=r.production_out_qty,
                    other_out_qty=r.other_out_qty,
                    closing_qty=r.closing_qty,
                    source_file=m15.source_file,
                )
                for r in m15.rows
            )

        if m15a:
            session.add_all(
                SpBalance(
                    company_id=company.id,
                    period_year=year,
                    row_no=r.row_no,
                    product_code=r.product_code,
                    product_name=r.product_name,
                    unit=r.unit,
                    opening_qty=r.opening_qty,
                    intake_qty=r.intake_qty,
                    repurpose_qty=r.repurpose_qty,
                    export_qty=r.export_qty,
                    other_out_qty=r.other_out_qty,
                    closing_qty=r.closing_qty,
                    source_file=m15a.source_file,
                )
                for r in m15a.rows
            )

        if m16:
            session.add_all(
                Norm(
                    company_id=company.id,
                    period_year=year,
                    product_code=r.product_code,
                    product_name=r.product_name,
                    product_unit=r.product_unit,
                    material_code=r.material_code,
                    material_name=r.material_name,
                    material_unit=r.material_unit,
                    norm_qty=r.norm_qty,
                    note=r.note,
                    source_file=m16.source_file,
                )
                for r in m16.rows
            )

        # BCCT gán period_year = NHÃN kỳ (`year`), tách khỏi mốc giao dịch. Chỉ giữ
        # dòng có ngày trong cửa sổ kỳ [period_from, period_to] — file gộp nhiều kỳ
        # chỉ đóng góp phần đúng cửa sổ; phần ngoài do lần nạp kỳ đó xử lý. Dòng
        # thiếu ngày → quy về kỳ đang nạp (không suy được năm).
        for bcct in bcct_files:
            to_add = []
            for r in bcct.rows:
                if not in_period(r.declaration_date, period_from, period_to):
                    continue
                to_add.append(DeclarationLine(
                    company_id=company.id,
                    period_year=year,
                    declaration_no=r.declaration_no,
                    declaration_date=r.declaration_date,
                    customs_code=r.customs_code,
                    line_no=r.line_no,
                    item_code=r.item_code,
                    item_name=r.item_name,
                    hs_code=r.hs_code,
                    origin=r.origin,
                    quantity=r.quantity,
                    unit=r.unit,
                    unit_price=r.unit_price,
                    currency=r.currency,
                    value_foreign=r.value_foreign,
                    value_total=r.value_total,
                    tax_total=r.tax_total,
                    partner=r.partner,
                    invoice_no=r.invoice_no,
                    source_file=bcct.source_file,
                ))
            session.add_all(to_add)

        session.commit()

    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest BCQT data for one company × year.")
    parser.add_argument("--company", required=True, help="Mã DN (vd HONG_AN)")
    parser.add_argument("--year", type=int, required=True, help="Năm kỳ báo cáo (vd 2024)")
    parser.add_argument("--path", type=Path, default=None, help="Override raw data root")
    parser.add_argument("--dry-run", action="store_true", help="Discover + parse only, no DB write")
    args = parser.parse_args(argv)

    try:
        stats = ingest(args.company, args.year, raw_root=args.path, dry_run=args.dry_run)
    except FileNotFoundError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    print(f"=== Ingest {stats.company_code} {stats.period_year} ===")
    print("Files discovered:")
    if stats.files:
        for k, v in stats.files.items():
            short = Path(v).name if v else "(none)"
            print(f"  {k:6s} → {short}")
    print("Rows parsed:")
    print(f"  M15  (NVL):  {stats.m15_rows}")
    print(f"  M15a (SP):   {stats.m15a_rows}")
    print(f"  M16  (norm): {stats.m16_rows}")
    other = f" (+{stats.bcct_other_year} kỳ khác bị loại)" if stats.bcct_other_year else ""
    print(f"  BCCT:        {stats.bcct_rows}{other}")
    if args.dry_run:
        print("(dry-run — chưa ghi DB)")
    else:
        print("Ingest hoàn tất.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
