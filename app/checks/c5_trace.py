"""Nhóm 5 — Truy nguồn nguyên vật liệu nhập khẩu (§4.1 đề án).

MVP tuần 5: C5.1. C5.2 + C5.3 là W.I.P.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.checks.registry import Severity
from app.models import Finding, NvlBalance


def check_c5_1(session: Session, company_id: int, year: int) -> list[Finding]:
    """NVL có `xuất_sản_xuất` > 0 trong M15 nhưng nhập_trong_kỳ = 0 và tồn_đầu = 0.

    Tiêu hao từ nguồn không khai báo — nguyên vật liệu nội địa bị đưa vào
    phạm vi miễn thuế.
    """
    rows = session.scalars(
        select(NvlBalance).where(
            NvlBalance.company_id == company_id,
            NvlBalance.period_year == year,
            NvlBalance.production_out_qty > 0,
            NvlBalance.import_qty == 0,
            NvlBalance.opening_qty == 0,
        )
    ).all()

    return [
        Finding(
            company_id=company_id,
            period_year=year,
            check_code="C5.1",
            severity=Severity.CRITICAL.value,
            subject_type="material_code",
            subject_key=r.material_code,
            book=r.book,
            title=(
                f"NVL {r.material_code} có xuất SX {r.production_out_qty:.2f} "
                f"{r.unit or ''} nhưng không có nhập trong kỳ và không có tồn đầu kỳ"
            ),
            details={
                "production_out": r.production_out_qty,
                "import": r.import_qty,
                "opening": r.opening_qty,
            },
            evidence_refs=[{
                "table": "nvl_balances",
                "filter": (
                    {"company_id": company_id, "period_year": year, "material_code": r.material_code}
                    | ({"book": r.book} if r.book is not None else {})
                ),
            }],
        )
        for r in rows
    ]


CHECKS = {
    "C5.1": check_c5_1,
}
