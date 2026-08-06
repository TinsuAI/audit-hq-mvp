"""Chạy lại kiểm tra cho mọi (DN, kỳ) đã có dữ liệu. KHÔNG ingest, KHÔNG đụng file.

Khác `app.pipeline.run_all`: chỗ đó ingest lại từ `data/raw` theo whitelist tên DN
thật, không dùng được trên DB đã ẩn danh. Chỗ này chỉ chạy lại check trên dữ liệu
đã nằm trong DB.

CẢNH BÁO — MẤT TRẠNG THÁI CÁN BỘ: `run_checks()` xoá cứng `Finding` của các mã sắp
chạy rồi insert lại, và không check nào truyền `status=`/`notes=`. Mọi finding đang ở
`confirmed` / `rejected` / `noted` và mọi ghi chú sẽ về `new`. Chạy `--report` trước
để biết mất bao nhiêu.

Usage:
    python -m scripts.rerun_all_checks --report      # chỉ đếm, không đụng dữ liệu
    python -m scripts.rerun_all_checks               # chạy lại tất cả
    python -m scripts.rerun_all_checks --company HONG_AN
"""

from __future__ import annotations

import argparse
import sys
import time

from sqlalchemy import func, select

from app.database import SessionLocal
from app.models import CheckRun, Company, Finding


def _pairs(session, only_company: str | None) -> list[tuple[str, int]]:
    """(mã DN, kỳ) đã từng chạy check — nguồn sự thật cho tập cần chạy lại."""
    stmt = (
        select(Company.code, CheckRun.period_year)
        .join(CheckRun, CheckRun.company_id == Company.id)
        .distinct()
    )
    if only_company:
        stmt = stmt.where(Company.code == only_company)
    return sorted(session.execute(stmt).all())


def _officer_marked(session) -> tuple[int, int]:
    """(số finding status != 'new', số finding có ghi chú) — thứ sẽ mất khi chạy lại."""
    marked = session.scalar(
        select(func.count()).select_from(Finding).where(Finding.status != "new")
    )
    noted = session.scalar(
        select(func.count())
        .select_from(Finding)
        .where(Finding.notes.is_not(None), Finding.notes != "")
    )
    return marked or 0, noted or 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--company", help="Chỉ chạy 1 DN (mã lưu trữ)")
    parser.add_argument(
        "--report", action="store_true",
        help="Chỉ in tập sẽ chạy + trạng thái cán bộ sẽ mất; KHÔNG chạy",
    )
    args = parser.parse_args(argv)

    with SessionLocal() as session:
        pairs = _pairs(session, args.company)
        marked, noted = _officer_marked(session)
        total_findings = session.scalar(select(func.count()).select_from(Finding)) or 0

    print(f"{len(pairs)} cặp (DN, kỳ) · {total_findings} finding hiện có")
    print(f"Trạng thái cán bộ sẽ MẤT nếu chạy lại: {marked} finding đã đánh dấu · "
          f"{noted} finding có ghi chú")
    if args.report:
        for code, year in pairs:
            print(f"  {code} {year}")
        return 0
    if not pairs:
        print("Không có cặp nào để chạy.", file=sys.stderr)
        return 1

    from app.pipeline.run_checks import run_checks

    failed = 0
    for i, (code, year) in enumerate(pairs, 1):
        t = time.time()
        try:
            stats = run_checks(code, year)
            print(
                f"[{i}/{len(pairs)}] {code} {year}: {stats.total} phát hiện · "
                f"{len(stats.not_evaluable)} chưa đánh giá được · {time.time() - t:.1f}s",
                flush=True,
            )
        except Exception as e:  # một DN hỏng không được dừng cả lượt
            failed += 1
            print(f"[{i}/{len(pairs)}] {code} {year}: LỖI {type(e).__name__}: {e}",
                  file=sys.stderr, flush=True)
    print(f"Xong. {len(pairs) - failed}/{len(pairs)} cặp chạy được.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
