"""Khôi phục tên thực từ mapping file của anonymize.

Chỉ dùng cho dev/debug nội bộ. Đọc `data/anonymize_mapping.json`
(file gitignored) và rollback Company + DeclarationLine.partner về
giá trị gốc.

Usage:
    python -m scripts.restore
    python -m scripts.restore --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Company, DeclarationLine

MAPPING_FILE = Path(__file__).resolve().parent.parent / "db-data" / "anonymize_mapping.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Restore tên thực từ mapping file.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if not MAPPING_FILE.exists():
        print(f"Không tìm thấy mapping file: {MAPPING_FILE}", file=sys.stderr)
        return 1

    mapping = json.loads(MAPPING_FILE.read_text(encoding="utf-8"))

    with SessionLocal() as session:
        # Restore companies
        restored = 0
        for new_code, info in mapping.get("companies", {}).items():
            company = session.scalar(select(Company).where(Company.code == new_code))
            if company is None:
                print(f"  ⚠ Không tìm thấy DN {new_code} trong DB.", file=sys.stderr)
                continue
            print(
                f"  {new_code} → {info['original_code']} | "
                f"MST {info['new_tax_id']} → {info['original_tax_id'] or '—'}"
            )
            if not args.dry_run:
                company.code = info["original_code"]
                company.name = info["original_name"]
                company.tax_id = info["original_tax_id"]
                company.address = info["original_address"]
                restored += 1

        # Restore partners
        partners = mapping.get("partners", {})
        if not args.dry_run:
            for alias, original in partners.items():
                session.execute(
                    DeclarationLine.__table__.update()
                    .where(DeclarationLine.partner == alias)
                    .values(partner=original)
                )
            session.commit()

        print(f"\nKhôi phục {restored} DN, {len(partners)} NCC.")
        if args.dry_run:
            print("(dry-run — chưa ghi DB)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
