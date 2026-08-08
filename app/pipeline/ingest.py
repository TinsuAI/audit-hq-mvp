"""Ingest BCQT data into SQLite for one company × year.

Usage:
    python -m app.pipeline.ingest --company HONG_AN --year 2024
    python -m app.pipeline.ingest --company HONG_AN --year 2024 --dry-run
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from sqlalchemy import delete, select

from app.adapters import parse_bcct, parse_m15, parse_m15a, parse_m16
from app.adapters.evidence import POSITION_ONLY
from app.adapters.sheet_select import SheetNotFound
from app.database import SessionLocal
from app.models import (
    Company,
    CompanyPeriod,
    DataFile,
    DeclarationLine,
    Norm,
    NvlBalance,
    SpBalance,
)
from app.models.data_file import SETTLEMENT_SLOTS
from app.pipeline.discover import DiscoveredFiles, discover
from app.pipeline.period import default_bounds, in_period, resolve_period_bounds
from app.pipeline.saved_map import apply_absent_fields
from app.pipeline.saved_map import officer_absent_maps as saved_officer_absent
from app.pipeline.saved_map import officer_maps as saved_officer_maps
from app.settings import settings


@dataclass
class IngestStats:
    company_code: str
    period_year: int
    m15_rows: int = 0
    m15a_rows: int = 0
    m16_rows: int = 0
    bcct_rows: int = 0  # dòng BCCT ĐÃ LƯU (từ #48: mọi dòng parse được, không loại dòng nào)
    # Dòng đã lưu nhưng ngày tờ khai NGOÀI cửa sổ kỳ — thuộc kỳ khác lúc query, để BÁO.
    bcct_out_of_window: int = 0
    bcct_undated: int = 0  # dòng không có ngày tờ khai — quy theo nhãn nạp
    bcct_skipped: list[str] | None = None  # file trong HANG_CHI_TIET không phải BCCT
    # Cửa sổ kỳ suy từ tiêu đề file bị loại vì không hợp lệ với nhãn kỳ (#66) — thường
    # là file của kỳ khác lẫn vào thư mục năm. Đã thay bằng niên độ DN, nhưng phải BÁO.
    period_window_rejected: list[str] | None = None
    files: dict[str, str | None] | None = None
    # slot → ParseProvenance (cách đọc file: standard/extended/labeled + bằng chứng).
    provenance: dict | None = None
    # "slot:tên file" → tên trang tính đã đọc. Theo TỪNG FILE chứ không theo slot:
    # một kỳ có thể có nhiều file BCCT, mỗi file một trang khác nhau.
    sheets: dict[str, str | None] = field(default_factory=dict)


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


_SETTLEMENT_PARSERS = {"m15": parse_m15, "m15a": parse_m15a, "m16": parse_m16}


def sheet_overrides(company_code: str, year: int, raw_root: Path) -> dict[str, str]:
    """{đường dẫn tuyệt đối: tên trang tính} theo chỉ định của cán bộ ở registry.

    Đọc bằng session riêng để cả đường CLI lẫn dry-run (không có session) đều áp
    cùng một lựa chọn — trang tính khác nhau cho ra bộ dòng khác nhau, xem trước mà
    đọc trang khác lúc nạp thì bản xem trước vô nghĩa. DN chưa có trong DB → {}.
    """
    with SessionLocal() as session:
        company = session.scalar(select(Company).where(Company.code == company_code))
        if company is None:
            return {}
        rows = session.scalars(
            select(DataFile).where(
                DataFile.company_id == company.id,
                DataFile.period_year == year,
                DataFile.sheet_override.is_not(None),
            )
        ).all()
        return {str(raw_root / r.stored_path): r.sheet_override for r in rows}


def officer_column_maps(company_code: str) -> dict[str, dict[str, dict[str, int]]]:
    """`{slot: {vân tay: {field: cột}}}` map cán bộ đã xác nhận của DN — cho parser.

    Đọc bằng phiên riêng như ``sheet_overrides`` và ở ĐÚNG chỗ đó: bước parse chạy
    trước khi `ingest` mở phiên ghi. Chỉ đọc, không ghi. DN chưa có trong DB → {}.
    """
    with SessionLocal() as session:
        company = session.scalar(select(Company).where(Company.code == company_code))
        if company is None:
            return {}
        return saved_officer_maps(session, company.id)


def officer_absent_maps(company_code: str) -> dict[str, dict[str, list[str]]]:
    """`{slot: {vân tay: [trường khai vắng]}}` — cùng đường đọc với `officer_column_maps`."""
    with SessionLocal() as session:
        company = session.scalar(select(Company).where(Company.code == company_code))
        if company is None:
            return {}
        return saved_officer_absent(session, company.id)


class IngestPlanError(RuntimeError):
    """Kế hoạch nạp sẽ làm mất sổ quyết toán — dừng TRƯỚC khi xoá dữ liệu cũ.

    `ingest` xoá sạch (company, year) rồi nạp lại theo kế hoạch, nên một kế hoạch
    thiếu sổ là mất dữ liệu im lặng. Thà hỏng ồn còn hơn gộp nhầm hai sổ làm một.
    """


def _books_already_stored(session, company_id: int, year: int) -> set[str]:
    """Các sổ đang có trong DB cho (DN, kỳ) — nguồn sự thật độc lập với data_files."""
    books: set[str] = set()
    for model in (NvlBalance, SpBalance, Norm):
        books |= {
            b
            for (b,) in session.execute(
                select(model.book)
                .where(
                    model.company_id == company_id,
                    model.period_year == year,
                    model.book.is_not(None),
                )
                .distinct()
            ).all()
        }
    return books


def book_assignment_error(session, company_id: int, year: int) -> str | None:
    """Lý do kế hoạch nạp settlement bị chặn vì gán sổ chưa đủ; None nếu qua được.

    Hai điều kiện, cả hai đều dẫn tới gộp sổ im lặng nếu cho đi tiếp. Tách khỏi
    `_plan_settlement_files` để màn dữ liệu hỏi được "kỳ này còn vướng gán sổ không"
    mà không phải mở file nào, và hỏi bằng CHÍNH đoạn mã chặn lượt nạp.
    """
    rows = session.scalars(
        select(DataFile).where(
            DataFile.company_id == company_id,
            DataFile.period_year == year,
            DataFile.slot.in_(SETTLEMENT_SLOTS),
        )
    ).all()
    if not any(r.book for r in rows):
        # Tag book chỉ sống trong data_files, mà `sync_data_files` prune dòng khi file
        # vắng trên đĩa. Mất tag + nạp tiếp = dựng lại pháp nhân nhiều sổ thành MỘT sổ
        # gộp, im lặng. Đối chiếu với sổ đang có trong DB trước khi cho đi tiếp.
        prior = _books_already_stored(session, company_id, year)
        if prior:
            return (
                f"DN đang có sổ {', '.join(sorted(prior))} trong kỳ {year} nhưng không "
                f"file nào còn nhãn sổ — nạp tiếp sẽ gộp tất cả thành một sổ. Hãy đồng "
                f"bộ lại danh sách file rồi gán nhãn sổ cho từng file quyết toán và nạp lại."
            )
        return None

    # Gán sổ phải là tất-cả-hoặc-không. Dòng của file chưa gán rơi vào book=NULL, mà ở
    # pháp nhân nhiều sổ NULL nghĩa là "liên sổ" — C4.1/C4.3/C6.1 gom NULL thành sổ thứ
    # ba và đối chiếu định mức/tồn kho bên trong cái sổ không tồn tại đó.
    untagged = [f"{r.slot}: {r.stored_path}" for r in rows if not r.book]
    if untagged:
        return (
            "Một số file quyết toán đã gán sổ, số khác chưa: "
            + "; ".join(sorted(untagged))
            + ". Gán sổ cho MỌI file quyết toán của kỳ rồi nạp lại."
        )
    return None


def _plan_settlement_files(
    session, company_id: int, year: int, discovered_parsed: dict, raw_root: Path,
    officer: dict[str, dict[str, dict[str, int]]] | None = None,
) -> dict[str, list[tuple]]:
    """Kế hoạch nạp settlement theo SỔ (ADR #19 Revision — UI + upload).

    Trả `{"m15": [(parsed, book)], "m15a": [...], "m16": [...]}`.

    Nguồn book = cột `data_files.book` mỗi file settlement (gán ở review WS1). Nếu
    KHÔNG có tag book nào (đường CLI/script, pilot một sổ) → dùng file discover một
    lượt, book=NULL → 002/006 + script không đổi. Có tag book → data_files-driven:
    gom MỌI file settlement theo book, parse từng file, tag rows theo book của file
    → re-ingest full reprocess dựng lại mọi sổ, KHÔNG cần guard.
    """
    rows = session.scalars(
        select(DataFile).where(
            DataFile.company_id == company_id,
            DataFile.period_year == year,
            DataFile.slot.in_(SETTLEMENT_SLOTS),
        )
    ).all()
    problem = book_assignment_error(session, company_id, year)
    if problem:
        raise IngestPlanError(problem)
    if not any(r.book for r in rows):
        # Single-book / CLI: file discover đã parse sẵn, book=NULL (hành vi cũ).
        return {slot: ([(obj, None)] if obj else []) for slot, obj in discovered_parsed.items()}

    plan: dict[str, list[tuple]] = {"m15": [], "m15a": [], "m16": []}
    unusable: list[str] = []
    for r in rows:
        path = raw_root / r.stored_path
        label = f"{r.slot}/{r.book or 'không sổ'}: {r.stored_path}"
        if not path.exists():
            unusable.append(f"{label} (không thấy file)")
            continue
        parser = _SETTLEMENT_PARSERS[r.slot]
        try:
            parsed = parser(path, r.sheet_override, year, (officer or {}).get(r.slot))
        except SheetNotFound:
            # File không phục vụ slot đã đăng ký (sync phân loại nhầm). Không nuốt lỗi
            # khác (bug parser phải nổ ra).
            unusable.append(f"{label} (không đọc được trang tính)")
            continue
        plan[r.slot].append((parsed, r.book))

    if unusable:
        # Bỏ qua file ở đây = xoá sổ đó khỏi DB rồi không nạp lại, không báo gì.
        raise IngestPlanError(
            "Không dùng được file quyết toán đã đăng ký: " + "; ".join(unusable)
        )
    return plan


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

    # Trang tính cán bộ đã chỉ định (registry) — None thì `select_sheet` tự chọn.
    picked = sheet_overrides(company_code, year, Path(raw_root))
    # Map cột cán bộ đã xác nhận — thắng template lẫn cột mặc định ở TỪNG trường.
    officer = officer_column_maps(company_code)
    # Trường cán bộ XÁC NHẬN VẮNG — gỡ khỏi kết quả parse TRƯỚC khi dựng dòng Tầng 1,
    # nếu không thì cột đó vẫn nạp theo vị trí mặc định trong khi cổng check bảo
    # "chưa đánh giá được", và hai màn nói ngược nhau.
    absent = officer_absent_maps(company_code)

    # `year` để chọn sheet: hai sheet cùng bố cục khác kỳ chỉ phân biệt được bằng kỳ.
    m15 = (
        parse_m15(files.m15, picked.get(str(files.m15)), year, officer.get("m15"))
        if files.m15 else None
    )
    m15a = (
        parse_m15a(files.m15a, picked.get(str(files.m15a)), year, officer.get("m15a"))
        if files.m15a else None
    )
    m16 = (
        parse_m16(files.m16, picked.get(str(files.m16)), year, officer.get("m16"))
        if files.m16 else None
    )
    # DN có thể tách tờ khai NK / XK thành nhiều file — parse + gộp tất cả. Thư mục
    # HANG_CHI_TIET đôi khi lẫn báo cáo KHÁC (vd "Báo cáo hàng hoá xuất khẩu" gộp theo
    # mã hàng, không có số tờ khai). Bỏ QUA từng file như vậy thay vì hỏng cả kỳ —
    # `diagnose_upload` vẫn báo riêng từng file cho cán bộ.
    bcct_files = []
    bcct_skipped: list[str] = []
    for bp in files.bcct:
        try:
            bcct_files.append(parse_bcct(bp, picked.get(str(bp)), year, officer.get("bcct")))
        except SheetNotFound:
            bcct_skipped.append(bp.name)
    stats.bcct_skipped = bcct_skipped
    for _slot, _parsed in (("m15", m15), ("m15a", m15a), ("m16", m16)):
        if _parsed is not None:
            apply_absent_fields(_parsed, _slot, absent.get(_slot))
    for _parsed in bcct_files:
        apply_absent_fields(_parsed, "bcct", absent.get("bcct"))

    # Trang tính THỰC SỰ đã đọc mỗi file — trang tài liệu và màn review hiện lại đúng
    # trang đó, thay vì mặc định xem trang đầu workbook.
    stats.sheets = {
        f"{slot}:{Path(parsed.source_file).name}": parsed.sheet
        for slot, parsed in (
            *((s, p) for s, p in (("m15", m15), ("m15a", m15a), ("m16", m16)) if p),
            *(("bcct", b) for b in bcct_files),
        )
    }

    stats.m15_rows = len(m15.rows) if m15 else 0
    stats.m15a_rows = len(m15a.rows) if m15a else 0
    stats.m16_rows = len(m16.rows) if m16 else 0
    # BCCT có thể nhiều file trong một kỳ mà `record_parse_result` chỉ giữ MỘT
    # provenance mỗi slot: ưu tiên file đầu tiên còn cột chỉ suy theo vị trí, để badge
    # truy nguồn nêu đúng file cần soi thay vì file sạch nhất.
    bcct_prov = next(
        (b.provenance for b in bcct_files
         if any(s == POSITION_ONLY for s in b.provenance.evidence.values())),
        bcct_files[0].provenance if bcct_files else None,
    )
    stats.provenance = {
        "m15": m15.provenance if m15 else None,
        "m15a": m15a.provenance if m15a else None,
        "m16": m16.provenance if m16 else None,
        "bcct": bcct_prov,
    }
    # BCCT: LƯU TRỌN mọi dòng parse được (#48, ADR #23 T1). Dòng có ngày ngoài cửa sổ
    # kỳ vẫn lưu dưới nhãn nạp — tư cách thuộc kỳ tính lúc query (`declaration_scope`)
    # nên dòng đó rơi vào kỳ đúng của nó thay vì biến mất. Chỉ ĐẾM để báo.
    bcct_all = [r for b in bcct_files for r in b.rows]
    company_meta = next((x.header for x in (m15, m15a, m16) if x is not None), None)

    def _count_flags(period_from: date, period_to: date) -> None:
        stats.bcct_rows = len(bcct_all)
        stats.bcct_undated = sum(1 for r in bcct_all if r.declaration_date is None)
        stats.bcct_out_of_window = sum(
            1
            for r in bcct_all
            if r.declaration_date is not None
            and not in_period(r.declaration_date, period_from, period_to)
        )

    if dry_run:
        # Xem trước: cửa sổ suy tự động (bản sửa tay cần session, không xét ở dry-run).
        _count_flags(*default_bounds(company_meta, year))
        return stats

    bcct_tax = next((b.company_tax_id for b in bcct_files if b.company_tax_id), None)
    bcct_name = next((b.company_name for b in bcct_files if b.company_name), None)
    tax_id = (company_meta.tax_id if company_meta else None) or bcct_tax
    name = (company_meta.name if company_meta else None) or bcct_name
    address = company_meta.address if company_meta else None

    with SessionLocal() as session:
        company = _get_or_create_company(session, company_code, tax_id, name, address)

        # Cửa sổ kỳ (from,to): bản sửa tay > tiêu đề file > dương lịch; ghi company_periods.
        # `rejected` nhận lý do khi tiêu đề file nói một kỳ khác hẳn nhãn đang nạp (#66).
        window_rejected: list[str] = []
        period_from, period_to = resolve_period_bounds(
            session, company.id, year, company_meta, rejected=window_rejected
        )
        stats.period_window_rejected = window_rejected or None

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
        _count_flags(period_from, period_to)

        # Kế hoạch nạp settlement theo SỔ: book per-file từ data_files (không có tag →
        # book=NULL, single-book giữ nguyên). Thay guard cũ — ghi lại mọi sổ một lượt.
        plan = _plan_settlement_files(
            session, company.id, year, {"m15": m15, "m15a": m15a, "m16": m16}, raw_root,
            saved_officer_maps(session, company.id),
        )
        # Pháp nhân nhiều sổ nạp theo data_files chứ theo file discover: ghi thêm trang
        # tính của những file đó, không thì chúng không có `sheet` trong registry.
        stats.sheets.update({
            f"{slot}:{Path(parsed.source_file).name}": parsed.sheet
            for slot, items in plan.items()
            for parsed, _book in items
        })

        # Wipe previous data for this company × year so re-ingest is idempotent.
        for model in (NvlBalance, SpBalance, Norm, DeclarationLine):
            session.execute(
                delete(model).where(
                    (model.company_id == company.id) & (model.period_year == year)
                )
            )

        for parsed, book in plan["m15"]:
            session.add_all(
                NvlBalance(
                    company_id=company.id,
                    period_year=year,
                    book=book,
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
                    source_file=parsed.source_file,
                )
                for r in parsed.rows
            )

        for parsed, book in plan["m15a"]:
            session.add_all(
                SpBalance(
                    company_id=company.id,
                    period_year=year,
                    book=book,
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
                    source_file=parsed.source_file,
                )
                for r in parsed.rows
            )

        for parsed, book in plan["m16"]:
            session.add_all(
                Norm(
                    company_id=company.id,
                    period_year=year,
                    book=book,
                    product_code=r.product_code,
                    product_name=r.product_name,
                    product_unit=r.product_unit,
                    material_code=r.material_code,
                    material_name=r.material_name,
                    material_unit=r.material_unit,
                    norm_qty=r.norm_qty,
                    note=r.note,
                    source_file=parsed.source_file,
                )
                for r in parsed.rows
            )

        # BCCT gán period_year = NHÃN NẠP (`year`) — provenance, KHÔNG phải tư cách
        # thuộc kỳ. Lưu TRỌN mọi dòng: file gộp nhiều kỳ đóng góp cả phần ngoài cửa
        # sổ, phần đó thuộc kỳ khác lúc query. Wipe re-ingest vẫn theo nhãn nạp
        # ("lượt nạp này thay chính nó") nên vẫn idempotent.
        for bcct in bcct_files:
            to_add = []
            for r in bcct.rows:
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
    flags = []
    if stats.bcct_out_of_window:
        flags.append(f"{stats.bcct_out_of_window} ngoài cửa sổ kỳ")
    if stats.bcct_undated:
        flags.append(f"{stats.bcct_undated} không có ngày")
    note = f" ({', '.join(flags)} — vẫn lưu)" if flags else ""
    print(f"  BCCT:        {stats.bcct_rows}{note}")
    if args.dry_run:
        print("(dry-run — chưa ghi DB)")
    else:
        print("Ingest hoàn tất.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
