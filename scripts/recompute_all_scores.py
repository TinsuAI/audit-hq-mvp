"""Tính lại CompanyYearScore + Company.risk_score từ findings hiện có.

Idempotent. Không re-run checks (nhanh, không thay đổi findings). Dùng sau khi:
- Đổi công thức scoring (rate-based 2026-05-26).
- Cài migration mới (CompanyYearScore lần đầu).
- Manual edit findings (mark rejected) → muốn score reflect.

Usage:
    python -m scripts.recompute_all_scores
    python -m scripts.recompute_all_scores --company HONG_AN  # chỉ 1 DN
    python -m scripts.recompute_all_scores --dry-run          # chỉ in, không lưu
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import distinct, select
from sqlalchemy.orm import Session

from app.checks.denominators import compute_denominators
from app.checks.scoring import compute_company_year_score
from app.database import SessionLocal
from app.models import Company, CompanyYearScore, Finding


def recompute_company(session: Session, company: Company, *, dry_run: bool = False) -> dict:
    """Tính lại điểm mọi năm có findings cho 1 DN. Trả summary {year: (old, new, tier)}."""
    years = sorted(session.scalars(
        select(distinct(Finding.period_year))
        .where(Finding.company_id == company.id)
    ).all())

    summary: dict[int, dict] = {}
    new_scores: list[int] = []

    for year in years:
        findings = session.scalars(
            select(Finding).where(
                Finding.company_id == company.id, Finding.period_year == year,
            )
        ).all()
        denominators = compute_denominators(session, company.id, year)
        breakdown = compute_company_year_score(findings, denominators)
        new_score = breakdown["score"]
        new_tier = breakdown["tier"]

        existing = session.scalar(
            select(CompanyYearScore).where(
                CompanyYearScore.company_id == company.id,
                CompanyYearScore.period_year == year,
            )
        )
        old_score = existing.score if existing else None

        summary[year] = {"old": old_score, "new": new_score, "tier": new_tier}
        new_scores.append(new_score)

        if not dry_run:
            if existing is None:
                session.add(CompanyYearScore(
                    company_id=company.id, period_year=year,
                    score=new_score, tier=new_tier, breakdown=breakdown,
                ))
            else:
                existing.score = new_score
                existing.tier = new_tier
                existing.breakdown = breakdown

    old_company_score = company.risk_score
    new_company_score = max(new_scores) if new_scores else 0
    summary["company_total"] = {"old": old_company_score, "new": new_company_score}

    if not dry_run:
        company.risk_score = new_company_score

    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Recompute scores từ findings hiện có.")
    parser.add_argument("--company", help="Chỉ tính lại cho 1 DN (mã DN). Mặc định: tất cả.")
    parser.add_argument("--dry-run", action="store_true", help="In thay đổi, không commit.")
    args = parser.parse_args(argv)

    with SessionLocal() as s:
        if args.company:
            companies = s.scalars(
                select(Company).where(Company.code == args.company)
            ).all()
            if not companies:
                print(f"ERROR: Không tìm thấy DN {args.company}", file=sys.stderr)
                return 1
        else:
            companies = s.scalars(select(Company).order_by(Company.code)).all()

        for company in companies:
            print(f"\n=== {company.code} ({company.name or '—'}) ===")
            summary = recompute_company(s, company, dry_run=args.dry_run)
            for key, val in summary.items():
                if key == "company_total":
                    arrow = "→" if val["old"] != val["new"] else "="
                    print(f"  TỔNG (max): {val['old']} {arrow} {val['new']}")
                else:
                    arrow = "→" if val["old"] != val["new"] else "="
                    old = val["old"] if val["old"] is not None else "—"
                    print(f"  {key}: {old} {arrow} {val['new']:>4}  [{val['tier']}]")

        if args.dry_run:
            print("\n(dry-run — không commit)")
            s.rollback()
        else:
            s.commit()
            print("\nĐã commit.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
