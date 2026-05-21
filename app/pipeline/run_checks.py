"""Run registered checks on a (company, year) and persist Findings.

Usage:
    python -m app.pipeline.run_checks --company HONG_AN --year 2024
    python -m app.pipeline.run_checks --company HONG_AN --year 2024 --check C1.1
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.checks import ALL_CHECKS
from app.checks.company_type import CompanyType, detect_company_type
from app.database import SessionLocal
from app.models import Company, Finding


@dataclass
class RunStats:
    company_code: str
    period_year: int
    company_type: CompanyType
    findings_per_check: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.findings_per_check.values())


def run_checks(
    company_code: str,
    year: int,
    only: set[str] | None = None,
    session: Session | None = None,
) -> RunStats:
    own_session = session is None
    s = session or SessionLocal()
    try:
        company = s.scalar(select(Company).where(Company.code == company_code))
        if company is None:
            raise ValueError(f"Không tìm thấy DN {company_code}. Chạy ingest trước.")

        company_type = detect_company_type(s, company.id, year)
        stats = RunStats(company_code=company_code, period_year=year, company_type=company_type)

        # Wipe previous findings cho (company, year) trước khi chạy lại.
        codes_to_run = set(ALL_CHECKS) if only is None else only & set(ALL_CHECKS)
        if codes_to_run:
            s.execute(
                delete(Finding).where(
                    Finding.company_id == company.id,
                    Finding.period_year == year,
                    Finding.check_code.in_(codes_to_run),
                )
            )

        for code in sorted(codes_to_run):
            fn = ALL_CHECKS[code]
            findings = fn(s, company.id, year)
            for f in findings:
                s.add(f)
            stats.findings_per_check[code] = len(findings)

        s.commit()
        return stats
    finally:
        if own_session:
            s.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Chạy check trên (company, year).")
    parser.add_argument("--company", required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--check", action="append", help="Chạy chỉ check này (lặp được).")
    args = parser.parse_args(argv)

    only = set(args.check) if args.check else None
    try:
        stats = run_checks(args.company, args.year, only=only)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    print(f"=== Run checks: {stats.company_code} {stats.period_year} ===")
    print(f"Loại hình DN phát hiện: {stats.company_type.value}")
    print(f"Tổng findings: {stats.total}")
    for code in sorted(stats.findings_per_check):
        n = stats.findings_per_check[code]
        marker = "▸" if n > 0 else " "
        print(f"  {marker} {code}: {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
