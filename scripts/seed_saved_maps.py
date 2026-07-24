"""Seed map cột `officer-confirmed` cho các DN whitelist theo shape của mình (WS1-3).

Mỗi DN whitelist duyệt sẵn bố cục hiện tại → đường demo `officer-confirmed` (auto-
verify, không hỏi cột). Với mỗi (DN, năm) có file, dry-run parse để lấy vân tay form
+ map cột + evidence rồi upsert vào `saved_column_maps` theo `(DN, slot, vân tay)`.

Idempotent (upsert theo khoá); KHÔNG tự chạy khi import; KHÔNG ghi dòng dữ liệu
(dùng dry_run). DN chưa có trong DB hoặc thiếu file → bỏ qua, báo lại.

Usage:
    python -m scripts.seed_saved_maps
    python -m scripts.seed_saved_maps --company HONG_AN
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Company
from app.pipeline.ingest import ingest
from app.pipeline.run_all import DEMO_WHITELIST
from app.pipeline.saved_map import save_column_map
from app.settings import settings


def seed_company_year(session, company: Company, code: str, year: int, raw_root: Path) -> int:
    """Upsert map cho mọi slot có provenance ở (DN, năm). Trả số map đã ghi."""
    stats = ingest(code, year, raw_root=raw_root, dry_run=True)
    provenance = stats.provenance or {}
    saved = 0
    for slot, prov in provenance.items():
        if prov is None:
            continue
        detail = getattr(prov, "detail", None) or {}
        form_sig = detail.get("form_signature")
        column_map = detail.get("column_map")
        if not form_sig or not column_map:
            continue
        save_column_map(
            session, company.id, slot, form_sig, column_map,
            evidence=getattr(prov, "evidence", None), confirmed_by=None,
        )
        saved += 1
    return saved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed saved column maps cho DN whitelist.")
    parser.add_argument("--company", help="Chỉ seed 1 DN")
    parser.add_argument("--path", type=Path, default=None, help="Override raw data root")
    args = parser.parse_args(argv)

    raw_root = Path(args.path or settings.raw_data_path)
    total = 0
    with SessionLocal() as session:
        for code, years in DEMO_WHITELIST.items():
            if args.company and code != args.company:
                continue
            company = session.scalar(select(Company).where(Company.code == code))
            if company is None:
                print(f"  - {code}: chưa có trong DB, bỏ qua.", file=sys.stderr)
                continue
            for year in years:
                if not (raw_root / code / str(year)).is_dir():
                    continue
                try:
                    n = seed_company_year(session, company, code, year, raw_root)
                except FileNotFoundError:
                    continue
                except Exception as e:  # noqa: BLE001 — file lỗi không chặn các DN khác
                    print(f"  ✗ {code} {year}: {type(e).__name__}: {e}", file=sys.stderr)
                    continue
                if n:
                    print(f"  ✓ {code} {year}: {n} map")
                    total += n
        session.commit()
    print(f"✓ Seeded {total} saved column map(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
