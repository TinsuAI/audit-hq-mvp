"""Ẩn danh dữ liệu DN cho demo (§6.2 đề án).

Modify in-place DB:
- Company.code, name, tax_id, address → DN_xxx ngẫu nhiên có seed.
- DeclarationLine.partner → NCC_xxx theo thứ tự xuất hiện.
- Giữ nguyên: mã HS, mã loại hình, số lượng, giá trị, material/product_code,
  ngày tờ khai (đã được đề án §6.2 confirm là giữ).

Mapping được lưu vào `data/anonymize_mapping.json` (file local, gitignored)
để có thể restore khi cần debug nội bộ.

Usage:
    python -m scripts.anonymize          # apply
    python -m scripts.anonymize --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Company, DeclarationLine

MAPPING_FILE = Path(__file__).resolve().parent.parent / "db-data" / "anonymize_mapping.json"

# Mapping cố định DN thực → mã demo (chốt 2026-05-21 trong demo plan §6.1).
COMPANY_MAPPING: dict[str, dict[str, str]] = {
    "GROWATT": {
        "code": "DN_001",
        "name": "Doanh nghiệp DN_001",
        "industry": "Điện tử (HS 85)",
        "address": "Khu công nghiệp tỉnh A",
    },
    "KIM_LONG": {
        "code": "DN_002",
        "name": "Doanh nghiệp DN_002",
        "industry": "Cơ khí (HS 84)",
        "address": "Khu công nghiệp tỉnh B",
    },
    "HONG_AN": {
        "code": "DN_003",
        "name": "Doanh nghiệp DN_003",
        "industry": "Dệt may / Da giày (HS 61, 64)",
        "address": "Khu công nghiệp tỉnh C",
    },
    "DO_THANH": {
        "code": "DN_004",
        "name": "Doanh nghiệp DN_004",
        "industry": "Hoá chất (HS 39)",
        "address": "Khu công nghiệp tỉnh D",
    },
    "HONG_PHUC": {
        "code": "DN_005",
        "name": "Doanh nghiệp DN_005",
        "industry": "Cơ khí phụ trợ",
        "address": "Khu công nghiệp tỉnh E",
    },
    "HIEP_QUANG": {
        "code": "DN_006",
        "name": "Doanh nghiệp DN_006 (dự bị, không demo)",
        "industry": "Dệt may",
        "address": "Khu công nghiệp tỉnh F",
    },
}


def _deterministic_mst(seed: str) -> str:
    """Sinh MST 10 chữ số có seed cố định từ original tax_id."""
    h = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    # Lấy 10 chữ số đầu từ hexdigest (chuyển hex → digit).
    digits = "".join(c for c in h if c.isdigit())
    return (digits + "0" * 10)[:10]


def _ncc_alias(seed: str, idx: int) -> str:
    """Mã NCC giả ổn định."""
    h = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:6].upper()
    return f"NCC_{idx:03d}_{h}"


def anonymize(session: Session, dry_run: bool = False) -> dict:
    """Anonymize DB; trả về mapping dict đã apply."""
    mapping: dict = {"companies": {}, "partners": {}}

    # Bước 1: companies
    companies = session.scalars(select(Company)).all()
    for c in companies:
        # Idempotent: skip nếu code đã được ẩn danh (DN_xxx).
        if c.code.startswith("DN_"):
            continue
        target = COMPANY_MAPPING.get(c.code)
        if target is None:
            print(f"  ⚠ Bỏ qua DN không có trong COMPANY_MAPPING: {c.code}", file=sys.stderr)
            continue
        orig_tax = c.tax_id or c.code
        new_tax = _deterministic_mst(orig_tax)
        mapping["companies"][target["code"]] = {
            "original_code": c.code,
            "original_name": c.name,
            "original_tax_id": c.tax_id,
            "original_address": c.address,
            "new_code": target["code"],
            "new_name": target["name"],
            "new_tax_id": new_tax,
            "new_address": target["address"],
            "industry": target["industry"],
        }
        if not dry_run:
            c.code = target["code"]
            c.name = target["name"]
            c.tax_id = new_tax
            c.address = target["address"]

    # Bước 2: partners (NCC) trong DeclarationLine
    distinct_partners = sorted(
        p for p in session.scalars(
            select(DeclarationLine.partner).where(DeclarationLine.partner.is_not(None)).distinct()
        ).all()
        if p and not p.startswith("NCC_")
    )
    for idx, original in enumerate(distinct_partners, start=1):
        alias = _ncc_alias(original, idx)
        mapping["partners"][alias] = original
        if not dry_run:
            session.execute(
                DeclarationLine.__table__.update()
                .where(DeclarationLine.partner == original)
                .values(partner=alias)
            )

    if not dry_run:
        session.commit()

    return mapping


def save_mapping(mapping: dict) -> None:
    MAPPING_FILE.parent.mkdir(parents=True, exist_ok=True)
    MAPPING_FILE.write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Anonymize DN cho demo (§6.2 đề án).")
    parser.add_argument("--dry-run", action="store_true",
                        help="In ra mapping, không sửa DB.")
    args = parser.parse_args(argv)

    with SessionLocal() as session:
        mapping = anonymize(session, dry_run=args.dry_run)

    print("=== Anonymize ===")
    if not mapping["companies"]:
        print("Không có DN nào cần anonymize (có thể đã làm rồi).")
    for new_code, info in sorted(mapping["companies"].items()):
        print(
            f"  {info['original_code']:12s} → {new_code} | "
            f"MST {info['original_tax_id'] or '—'} → {info['new_tax_id']} | "
            f"{info['industry']}"
        )
    if mapping["partners"]:
        print(f"\nĐã anonymize {len(mapping['partners'])} NCC.")

    if not args.dry_run:
        save_mapping(mapping)
        print(f"\nMapping lưu tại: {MAPPING_FILE}")
        print("Để restore, chạy: python -m scripts.restore")
    else:
        print("\n(dry-run — chưa apply vào DB)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
