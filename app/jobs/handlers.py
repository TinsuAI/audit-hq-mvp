"""Job handler implementations.

Mỗi handler nhận `(payload: dict, session: Session)` và trả `dict` result hoặc raise.
Register trong app/main.py lifespan.
"""

from __future__ import annotations

from sqlalchemy import distinct, select, union_all
from sqlalchemy.orm import Session

from app.models import Company, DeclarationLine, Norm, NvlBalance, SpBalance
from app.pipeline.run_checks import run_checks as run_checks_pipeline


def find_years_with_data(session: Session, company_id: int) -> list[int]:
    """Trả về list năm distinct có dữ liệu ở bất kỳ table nào (M15/M15a/M16/BCCT).

    Sorted ascending. Dùng cho batch run "tất cả năm có dữ liệu".
    """
    stmt = union_all(
        select(distinct(NvlBalance.period_year)).where(NvlBalance.company_id == company_id),
        select(distinct(SpBalance.period_year)).where(SpBalance.company_id == company_id),
        select(distinct(Norm.period_year)).where(Norm.company_id == company_id),
        select(distinct(DeclarationLine.period_year)).where(
            DeclarationLine.company_id == company_id
        ),
    )
    years = set(session.scalars(stmt).all())
    return sorted(y for y in years if y is not None)


def run_checks_handler(payload: dict, session: Session) -> dict:
    """Chạy `run_checks` cho (company_code, year).

    `only` (tuỳ chọn, list[str]) → chạy tập con check; không có → full năm.
    """
    company_code = payload.get("company_code")
    year = payload.get("year")
    if not company_code or year is None:
        raise ValueError(f"Payload thiếu company_code/year: {payload!r}")
    only_raw = payload.get("only")
    only = {str(c) for c in only_raw} if only_raw else None
    stats = run_checks_pipeline(company_code, int(year), only=only, session=session)
    return {
        "company_code": stats.company_code,
        "period_year": stats.period_year,
        "company_type": stats.company_type.value,
        "only": sorted(only) if only else None,
        "total_findings": stats.total,
        "findings_per_check": stats.findings_per_check,
        "not_evaluable": stats.not_evaluable,
        "combos_fired": stats.combos_fired,
        "risk_score": stats.risk_score,
    }


def run_batch_handler(payload: dict, session: Session) -> dict:
    """Chạy checks cho mọi năm có dữ liệu của 1 DN. Aggregate stats.

    Payload: {"company_code": "HONG_AN"}
    """
    company_code = payload.get("company_code")
    if not company_code:
        raise ValueError(f"Payload thiếu company_code: {payload!r}")

    company = session.scalar(select(Company).where(Company.code == company_code))
    if company is None:
        raise ValueError(f"Không tìm thấy DN {company_code}. Chạy ingest trước.")

    years = find_years_with_data(session, company.id)
    if not years:
        return {
            "company_code": company_code,
            "years_processed": [],
            "total_findings": 0,
            "risk_score": 0,
            "note": "Không có dữ liệu nào để chạy kiểm tra.",
        }

    per_year: dict[int, dict] = {}
    total_findings = 0
    for year in years:
        stats = run_checks_pipeline(company_code, year, session=session)
        per_year[year] = {
            "total_findings": stats.total,
            "risk_score": stats.risk_score,
            "combos_fired": stats.combos_fired,
        }
        total_findings += stats.total

    # Sau khi loop, company.risk_score đã được update lần cuối = max qua các năm.
    session.refresh(company)
    return {
        "company_code": company_code,
        "years_processed": years,
        "total_findings": total_findings,
        "risk_score": company.risk_score or 0,
        "per_year": per_year,
    }
