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
from app.checks.combos import detect_combos
from app.checks.company_type import CompanyType, detect_company_type
from app.checks.scoring import compute_risk_score
from app.database import SessionLocal
from app.models import Company, Finding


@dataclass
class RunStats:
    company_code: str
    period_year: int
    company_type: CompanyType
    findings_per_check: dict[str, int] = field(default_factory=dict)
    combos_fired: list[str] = field(default_factory=list)
    risk_score: int = 0

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

        # Wipe previous findings cho (company, year) — bao gồm cả meta-finding
        # combo, vì combo phụ thuộc kết quả check vừa chạy lại.
        codes_to_run = set(ALL_CHECKS) if only is None else only & set(ALL_CHECKS)
        if codes_to_run:
            s.execute(
                delete(Finding).where(
                    Finding.company_id == company.id,
                    Finding.period_year == year,
                    Finding.check_code.in_(codes_to_run | {"COMBO_*"}),
                )
            )
        # Wipe combos riêng vì check_code COMBO_* không match in_().
        s.execute(
            delete(Finding).where(
                Finding.company_id == company.id,
                Finding.period_year == year,
                Finding.check_code.like("COMBO_%"),
            )
        )

        run_findings: list[Finding] = []
        for code in sorted(codes_to_run):
            fn = ALL_CHECKS[code]
            findings = fn(s, company.id, year)
            for f in findings:
                s.add(f)
            run_findings.extend(findings)
            stats.findings_per_check[code] = len(findings)

        # Combo chỉ chạy khi không filter --check (cần đủ findings để match).
        if only is None:
            s.flush()  # gán id cho findings để evidence_refs trỏ về
            combos = detect_combos(s, company.id, year, run_findings)
            for f in combos:
                s.add(f)
            stats.combos_fired = sorted({c.check_code for c in combos})
            run_findings.extend(combos)

        # Cập nhật risk_score cho Company (tổng cả 16 check + combo).
        all_year_findings = s.scalars(
            select(Finding).where(
                Finding.company_id == company.id,
                Finding.period_year == year,
            )
        ).all()
        # Tổng score xét trên toàn bộ năm, không chỉ run này (để giữ ổn định
        # khi --check 1 rule).
        latest_company_score = max(
            company.risk_score or 0,
            compute_risk_score(all_year_findings),
        ) if only else compute_risk_score(all_year_findings)
        company.risk_score = latest_company_score
        stats.risk_score = latest_company_score

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
    if stats.combos_fired:
        print(f"Combo fired: {', '.join(stats.combos_fired)}")
    print(f"Risk score: {stats.risk_score}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
