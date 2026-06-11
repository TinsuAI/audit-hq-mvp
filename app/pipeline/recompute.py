"""Tính lại điểm rủi ro từ findings HIỆN CÓ — KHÔNG chạy lại kiểm tra.

Dùng khi cán bộ đổi trạng thái finding (vd đánh dấu "Loại trừ"): điểm phải cập nhật
ngay, nhưng không được đụng tới findings (không xoá, không tái tạo combo). Khác với
`run_checks` (chạy lại toàn bộ check + ghi đè findings).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.checks.denominators import compute_denominators
from app.checks.scoring import compute_company_year_score
from app.models import Company, CompanyYearScore, Finding


def recompute_company_year(session: Session, company_id: int, year: int) -> CompanyYearScore:
    """Upsert điểm 1 (DN, năm) từ findings hiện có (tôn trọng `status`) + refresh risk_score.

    Finding `rejected` không tính vào điểm (xem `compute_rule_score`). Trả CompanyYearScore
    đã cập nhật. Caller tự `commit`.
    """
    findings = session.scalars(
        select(Finding).where(
            Finding.company_id == company_id,
            Finding.period_year == year,
        )
    ).all()
    denominators = compute_denominators(session, company_id, year)
    breakdown = compute_company_year_score(findings, denominators)

    cys = session.scalar(
        select(CompanyYearScore).where(
            CompanyYearScore.company_id == company_id,
            CompanyYearScore.period_year == year,
        )
    )
    if cys is None:
        cys = CompanyYearScore(
            company_id=company_id, period_year=year,
            score=breakdown["score"], tier=breakdown["tier"], breakdown=breakdown,
        )
        session.add(cys)
    else:
        cys.score = breakdown["score"]
        cys.tier = breakdown["tier"]
        cys.breakdown = breakdown
    session.flush()

    # `company.risk_score` = max điểm qua các năm (dùng cho ranking trang danh sách).
    company = session.get(Company, company_id)
    if company is not None:
        scores = session.scalars(
            select(CompanyYearScore.score).where(CompanyYearScore.company_id == company_id)
        ).all()
        company.risk_score = max(scores) if scores else 0

    return cys
