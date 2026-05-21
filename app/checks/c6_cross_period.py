"""Nhóm 6 — Kiểm tra liên kỳ (§4.1 đề án).

MVP tuần 5: C6.1 (tồn đầu kỳ N ≠ tồn cuối kỳ N-1, NVL).
C6.2-C6.5 là W.I.P.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.checks.registry import Severity
from app.models import Finding, NvlBalance

_TOLERANCE = 0.01


def check_c6_1(session: Session, company_id: int, year: int) -> list[Finding]:
    """Tồn đầu kỳ N (M15) khác tồn cuối kỳ N-1 (M15) — từng mã NVL.

    Skip nếu chưa có dữ liệu kỳ N-1.
    """
    prev_year = year - 1
    prev_rows = session.scalars(
        select(NvlBalance).where(
            NvlBalance.company_id == company_id,
            NvlBalance.period_year == prev_year,
        )
    ).all()
    if not prev_rows:
        return []
    prev_closing = {r.material_code: (r.closing_qty or 0.0) for r in prev_rows}

    curr_rows = session.scalars(
        select(NvlBalance).where(
            NvlBalance.company_id == company_id,
            NvlBalance.period_year == year,
        )
    ).all()

    findings: list[Finding] = []
    for r in curr_rows:
        curr_opening = r.opening_qty or 0.0
        if r.material_code not in prev_closing:
            # NVL mới xuất hiện kỳ N: nếu opening > 0 nhưng kỳ N-1 không có →
            # lệch (kỳ trước phải có tồn cuối tương ứng).
            if abs(curr_opening) > _TOLERANCE:
                findings.append(Finding(
                    company_id=company_id,
                    period_year=year,
                    check_code="C6.1",
                    severity=Severity.CRITICAL.value,
                    subject_type="material_code",
                    subject_key=r.material_code,
                    title=(
                        f"NVL {r.material_code} có tồn đầu kỳ {year} = {curr_opening:.2f} "
                        f"nhưng kỳ {prev_year} không có dòng tương ứng"
                    ),
                    details={
                        "current_opening": curr_opening,
                        "previous_closing": None,
                    },
                    evidence_refs=[{
                        "table": "nvl_balances",
                        "filter": {
                            "company_id": company_id,
                            "period_year": year,
                            "material_code": r.material_code,
                        },
                    }],
                ))
            continue

        prev = prev_closing[r.material_code]
        diff = curr_opening - prev
        if abs(diff) <= _TOLERANCE:
            continue
        findings.append(Finding(
            company_id=company_id,
            period_year=year,
            check_code="C6.1",
            severity=Severity.CRITICAL.value,
            subject_type="material_code",
            subject_key=r.material_code,
            title=(
                f"NVL {r.material_code} tồn đầu {year}={curr_opening:.2f} "
                f"khác tồn cuối {prev_year}={prev:.2f} (chênh {diff:+.2f})"
            ),
            details={
                "current_opening": curr_opening,
                "previous_closing": prev,
                "diff": diff,
            },
            evidence_refs=[
                {
                    "table": "nvl_balances",
                    "filter": {
                        "company_id": company_id,
                        "period_year": year,
                        "material_code": r.material_code,
                    },
                },
                {
                    "table": "nvl_balances",
                    "filter": {
                        "company_id": company_id,
                        "period_year": prev_year,
                        "material_code": r.material_code,
                    },
                },
            ],
        ))
    return findings


CHECKS = {
    "C6.1": check_c6_1,
}
