"""Tính lại điểm rủi ro từ findings HIỆN CÓ — KHÔNG chạy lại kiểm tra.

Dùng khi cán bộ đổi trạng thái finding (vd đánh dấu "Loại trừ"): điểm phải cập nhật
ngay, nhưng không được đụng tới findings (không xoá, không tái tạo combo). Khác với
`run_checks` (chạy lại toàn bộ check + ghi đè findings).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.app_settings import get_risk_tier_uppers
from app.checks.denominators import compute_denominators, extended_rule_scope
from app.checks.not_evaluable import load_not_evaluable
from app.checks.scoring import compute_company_year_score
from app.models import Company, CompanyYearScore, Finding


def recompute_company_year(session: Session, company_id: int, year: int) -> CompanyYearScore:
    """Upsert điểm 1 (DN, năm) từ findings hiện có (tôn trọng `status`) + refresh risk_score.

    Finding `rejected` không tính vào điểm (xem `compute_rule_score`). Trả CompanyYearScore
    đã cập nhật. Caller tự `commit`.
    """
    # Nạp ngưỡng hạng bằng CHÍNH session này trước khi chấm điểm. `tier_for` gọi
    # `get_tiers()` không truyền db → cache trống thì nó tự mở `SessionLocal()`.
    # Session lồng đó `close()` phát ROLLBACK; khi hai session dùng chung một
    # connection (SQLite in-memory + StaticPool ở test) thì UPDATE `finding.status`
    # đang treo của caller bị huỷ theo, và cán bộ đổi trạng thái xong thấy không ăn.
    # Đọc trước ở đây làm cache nóng nên `get_tiers()` phía dưới không mở session nào.
    get_risk_tier_uppers(session)

    findings = session.scalars(
        select(Finding).where(
            Finding.company_id == company_id,
            Finding.period_year == year,
        )
    ).all()
    denominators = compute_denominators(session, company_id, year)
    # Cùng tập loại trừ như `run_checks`: đổi trạng thái một finding không được kéo
    # check `not_evaluable` trở lại mẫu số/trần, vì thế điểm sẽ nhảy sau mỗi lần
    # cán bộ bấm "Loại trừ".
    breakdown = compute_company_year_score(
        findings, denominators, rule_scope=extended_rule_scope(session),
        not_evaluable=load_not_evaluable(session, company_id, year),
    )

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
