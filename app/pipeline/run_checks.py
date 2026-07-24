"""Run registered checks on a (company, year) and persist Findings.

Usage:
    python -m app.pipeline.run_checks --company HONG_AN --year 2024
    python -m app.pipeline.run_checks --company HONG_AN --year 2024 --check C1.1
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.checks import ALL_CHECKS
from app.checks.combos import detect_combos
from app.checks.company_type import CompanyType, detect_company_type
from app.checks.sql_runner import CheckRunError, run_check
from app.database import SessionLocal
from app.models import CheckRun, Company, Finding
from app.models.check_definition import CheckDefinition, CheckStatus
from app.pipeline.period import current_data_version


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

        # data_version đọc ở ĐẦU lần chạy (ràng buộc advisor b): re-ingest ở route-thread
        # có thể commit GIỮA lúc worker chạy check; ghi giá trị đọc-đầu vào check_runs
        # (không phải lúc-commit) để snapshot đúng dữ liệu check đã đọc.
        data_version = current_data_version(s, company.id, year)

        # Load dynamic checks (published) từ DB — kind 'sql' | 'python'.
        from sqlalchemy import select as _select
        dynamic_rows = s.scalars(
            _select(CheckDefinition).where(CheckDefinition.status == CheckStatus.PUBLISHED)
        ).all()
        dynamic_defs = {row.code: row for row in dynamic_rows}

        # Tập mã sẽ chạy = (built-in ∪ dynamic đã công bố) lọc theo `only`. Phải gồm
        # cả dynamic để wipe tương ứng — nếu chỉ wipe built-in thì chạy lẻ 1 check X.*
        # (nút "Chạy lại X.1") add finding mới mà KHÔNG xoá cũ → nhân đôi.
        codes_to_run = set(ALL_CHECKS) | set(dynamic_defs)
        if only is not None:
            codes_to_run = codes_to_run & only

        # Wipe finding cũ đúng các mã sắp chạy lại (built-in + dynamic).
        if codes_to_run:
            s.execute(
                delete(Finding).where(
                    Finding.company_id == company.id,
                    Finding.period_year == year,
                    Finding.check_code.in_(codes_to_run),
                )
            )
        # Chạy full: dọn thêm finding dynamic (X.*) mồ côi — def đã gỡ công bố nên
        # không nằm trong codes_to_run, sẽ không được dựng lại.
        if only is None:
            s.execute(
                delete(Finding).where(
                    Finding.company_id == company.id,
                    Finding.period_year == year,
                    Finding.check_code.like("X.%"),
                )
            )
        # Wipe combos riêng (vô điều kiện) — combo phụ thuộc finding vừa chạy lại; chỉ
        # RECOMPUTE mới gate theo combos_enabled (bên dưới). COMBO_% không match in_().
        s.execute(
            delete(Finding).where(
                Finding.company_id == company.id,
                Finding.period_year == year,
                Finding.check_code.like("COMBO_%"),
            )
        )

        all_codes = codes_to_run

        # Trạng thái mỗi check để ghi check_runs: 'ok' | 'error' (check ĐỘNG raise).
        run_status: dict[str, str] = {}
        for code in sorted(all_codes):
            if code in ALL_CHECKS:
                fn = ALL_CHECKS[code]
                findings = fn(s, company.id, year)
                run_status[code] = "ok"
            elif code in dynamic_defs:
                # Check tự do (SQL/Python) — lỗi 1 check không được làm hỏng cả run.
                try:
                    findings = run_check(dynamic_defs[code], s, company.id, year)
                    run_status[code] = "ok"
                except CheckRunError as exc:
                    import logging
                    logging.getLogger(__name__).warning(
                        "Check mở rộng %s lỗi khi chạy, bỏ qua: %s", code, exc
                    )
                    findings = []
                    run_status[code] = "error"
            else:
                continue
            for f in findings:
                s.add(f)
            stats.findings_per_check[code] = len(findings)

        # Combo recompute — MỌI lần chạy (lẻ hay full), gate theo combos_enabled
        # (default OFF). Đọc TOÀN finding-set (DN, năm), không chỉ finding vừa chạy —
        # combo bắc cầu giữa check re-run và check không đụng. Delete COMBO_* đã vô
        # điều kiện ở trên; chỉ recompute mới gate theo toggle (ADR #18 Revision — WS2).
        from app.app_settings import get_combos_enabled
        s.flush()  # gán id cho findings vừa chạy để evidence_refs trỏ về
        if get_combos_enabled(db=s):
            year_findings = s.scalars(
                select(Finding).where(
                    Finding.company_id == company.id,
                    Finding.period_year == year,
                )
            ).all()
            combos = detect_combos(s, company.id, year, year_findings)
            for f in combos:
                s.add(f)
            stats.combos_fired = sorted({c.check_code for c in combos})

        # Tính điểm rate-based + lưu CompanyYearScore + cập nhật company.risk_score.
        s.flush()
        all_year_findings = s.scalars(
            select(Finding).where(
                Finding.company_id == company.id,
                Finding.period_year == year,
            )
        ).all()

        from app.checks.denominators import compute_denominators, extended_rule_scope
        from app.checks.scoring import compute_company_year_score
        from app.models import CompanyYearScore

        denominators = compute_denominators(s, company.id, year)
        breakdown = compute_company_year_score(
            all_year_findings, denominators, rule_scope=extended_rule_scope(s)
        )
        year_score = breakdown["score"]

        # Upsert CompanyYearScore cho (DN, năm).
        existing = s.scalar(
            select(CompanyYearScore).where(
                CompanyYearScore.company_id == company.id,
                CompanyYearScore.period_year == year,
            )
        )
        if existing is None:
            s.add(CompanyYearScore(
                company_id=company.id, period_year=year,
                score=year_score, tier=breakdown["tier"], breakdown=breakdown,
            ))
        else:
            existing.score = year_score
            existing.tier = breakdown["tier"]
            existing.breakdown = breakdown

        # `company.risk_score` = max điểm qua các năm (cho ranking trang danh sách).
        all_year_scores = s.scalars(
            select(CompanyYearScore.score).where(CompanyYearScore.company_id == company.id)
        ).all()
        all_scores_with_current = list(all_year_scores) + [year_score]
        company.risk_score = max(all_scores_with_current) if all_scores_with_current else 0
        stats.risk_score = company.risk_score

        # WS3: upsert check_runs — 1 dòng mỗi (DN, năm, mã), MỌI check đã chạy kể cả
        # 0 finding. Ghi TRONG run_checks() (không job handler) → CLI + fallback inline
        # cũng dời `ran_at` (nếu không → false-stale). Combo LOẠI (chỉ check thật).
        ran_at = datetime.now(UTC).replace(tzinfo=None)
        if all_codes:
            existing_runs = {
                r.check_code: r
                for r in s.scalars(
                    select(CheckRun).where(
                        CheckRun.company_id == company.id,
                        CheckRun.period_year == year,
                        CheckRun.check_code.in_(all_codes),
                    )
                ).all()
            }
            for code in all_codes:
                fc = stats.findings_per_check.get(code, 0)
                st = run_status.get(code, "ok")
                row = existing_runs.get(code)
                if row is None:
                    s.add(CheckRun(
                        company_id=company.id, period_year=year, check_code=code,
                        ran_at=ran_at, finding_count=fc, status=st,
                        data_version=data_version,
                    ))
                else:
                    row.ran_at = ran_at
                    row.finding_count = fc
                    row.status = st
                    row.data_version = data_version

        # Full run dọn check_runs orphan của mã X.* đã gỡ công bố (soi orphan finding
        # ở trên). Không đụng khi chạy lẻ (`only=`).
        if only is None:
            s.execute(
                delete(CheckRun).where(
                    CheckRun.company_id == company.id,
                    CheckRun.period_year == year,
                    CheckRun.check_code.like("X.%"),
                    CheckRun.check_code.not_in(list(all_codes)),
                )
            )

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
