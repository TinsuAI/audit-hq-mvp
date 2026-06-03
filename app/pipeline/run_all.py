"""Ingest + run_checks cho toàn bộ DN × năm có sẵn trong data/raw/.

Usage:
    python -m app.pipeline.run_all
    python -m app.pipeline.run_all --company HONG_AN
    python -m app.pipeline.run_all --since-year 2023
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.pipeline.ingest import ingest
from app.pipeline.run_checks import run_checks
from app.settings import settings

# Whitelist DN × giai đoạn liền nhau có cả BCQT và BCCT (BCCT có thể nằm trong
# multi_year — discover.py tự fallback). DN khác bị loại do thiếu BCCT ≥1 năm.
DEMO_WHITELIST: dict[str, range] = {
    "HONG_AN": range(2021, 2026),     # 2021-2025
    "GROWATT": range(2023, 2026),     # 2023-2025
    "DO_THANH": range(2024, 2026),    # 2024-2025
    "KIM_LONG": range(2024, 2026),    # 2024-2025
}


def discover_company_years(raw_root: Path) -> list[tuple[str, int]]:
    """Trả list (DN, year) chỉ chứa các cặp trong DEMO_WHITELIST có thư mục năm tồn tại."""
    pairs: list[tuple[str, int]] = []
    if not raw_root.exists():
        return pairs
    for company in sorted(DEMO_WHITELIST):
        company_dir = raw_root / company
        if not company_dir.is_dir():
            continue
        for year in DEMO_WHITELIST[company]:
            if (company_dir / str(year)).is_dir():
                pairs.append((company, year))
    return pairs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest + run_checks cho toàn bộ DN × năm.")
    parser.add_argument("--company", help="Chỉ chạy 1 DN")
    parser.add_argument("--since-year", type=int, default=None, help="Bỏ qua các năm < since-year")
    parser.add_argument("--path", type=Path, default=None, help="Override raw data root")
    args = parser.parse_args(argv)

    raw_root = args.path or settings.raw_data_path
    pairs = discover_company_years(Path(raw_root))

    if args.company:
        pairs = [(c, y) for c, y in pairs if c == args.company]
    if args.since_year:
        pairs = [(c, y) for c, y in pairs if y >= args.since_year]

    if not pairs:
        print("Không tìm thấy (company, year) nào để chạy.", file=sys.stderr)
        return 1

    print(f"Sẽ chạy {len(pairs)} cặp (company, year):")
    for c, y in pairs:
        print(f"  - {c} {y}")
    print()

    # Phase 1: ingest tất cả (cần ingest trước, sau đó mới run_checks có cross-period).
    print("=== Phase 1: INGEST ===")
    ingested: list[tuple[str, int]] = []
    for c, y in pairs:
        try:
            stats = ingest(c, y, raw_root=Path(raw_root))
            other = f" (+{stats.bcct_other_year} BCCT kỳ khác bị loại)" if stats.bcct_other_year else ""
            print(
                f"  ✓ {c} {y}: M15={stats.m15_rows} M15a={stats.m15a_rows} "
                f"M16={stats.m16_rows} BCCT={stats.bcct_rows}{other}"
            )
            ingested.append((c, y))
        except FileNotFoundError as e:
            print(f"  ✗ {c} {y}: {e}", file=sys.stderr)
        except Exception as e:
            # Excel format lỗi, file corrupt, v.v. — log + tiếp tục
            print(f"  ✗ {c} {y}: {type(e).__name__}: {e}", file=sys.stderr)

    # Phase 2: run_checks cho từng năm (C6.1 cần kỳ N-1 đã có trong DB).
    print()
    print("=== Phase 2: RUN CHECKS ===")
    total_findings = 0
    total_combos = 0
    for c, y in ingested:
        try:
            stats = run_checks(c, y)
        except ValueError as e:
            print(f"  ✗ {c} {y}: {e}", file=sys.stderr)
            continue
        total_findings += stats.total
        total_combos += len(stats.combos_fired)
        combo_str = f", combo: {','.join(stats.combos_fired)}" if stats.combos_fired else ""
        print(f"  ✓ {c} {y}: {stats.total} findings, risk_score={stats.risk_score}{combo_str}")

    print()
    print(f"Tổng: {total_findings} findings · {total_combos} combo fired")
    return 0


if __name__ == "__main__":
    sys.exit(main())
