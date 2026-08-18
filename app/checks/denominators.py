"""Denominator (mẫu số) cho công thức rate-based scoring.

Mỗi check thuộc 1 scope:
- `nvl` : exposure = số mã NVL distinct (M15 ∪ BCCT phía nhập NVL)
- `tp`  : exposure = số mã TP distinct (M15a ∪ BCCT phía xuất)
- `m16` : exposure = số mã NVL distinct trong định mức M16

Rate = min(1, findings / denominator). Denominator=0 → rate=0 (không có cơ sở so).
"""

from __future__ import annotations

from sqlalchemy import distinct, select
from sqlalchemy.orm import Session

from app.checks.company_type import (
    EXPORT_CODES,
    IMPORT_CODES,
    detect_company_type,
)
from app.checks.scope import declaration_scope
from app.models import DeclarationLine, NvlBalance, SpBalance

# Mỗi check trong catalog 16 MVP map vào 1 scope.
# Khi thêm check mới: phải add vào đây hoặc test_rule_scope_covers_all_known_checks sẽ fail.
RULE_SCOPE: dict[str, str] = {
    # Nhóm 1: số lượng nhập / xuất
    "C1.1": "nvl", "C1.2": "nvl", "C1.3": "nvl",
    "C1.4": "tp",
    "C1.6": "nvl", "C1.7": "nvl",
    # Nhóm 2: cân bằng và tồn kho
    "C2.1": "nvl", "C2.2": "tp", "C2.3": "nvl", "C2.4": "tp",
    # Nhóm 3: phân loại hàng hoá
    "C3.1": "nvl", "C3.2": "nvl", "C3.3": "nvl",
    # Nhóm 4: định mức M16. C4.9 là ngoại lệ: chủ thể phát hiện là MÃ THÀNH PHẨM có
    # sản xuất trong kỳ, nên mẫu số là số mã TP ('tp'), không phải số mã NVL trong M16.
    "C4.1": "m16", "C4.3": "m16", "C4.9": "tp",
    # Nhóm 5: truy nguồn NVL
    "C5.1": "nvl",
    # Nhóm 6: liên kỳ
    "C6.1": "nvl", "C6.2": "tp",
}


def _count_distinct_nvl(session: Session, company_id: int, year: int) -> int:
    """Số mã NVL distinct = (mã trong M15) ∪ (mã trong BCCT phía nhập NVL)."""
    company_type = detect_company_type(session, company_id, year)
    import_codes = IMPORT_CODES.get(company_type, set())

    m15_codes = set(session.scalars(
        select(distinct(NvlBalance.material_code))
        .where(NvlBalance.company_id == company_id, NvlBalance.period_year == year)
    ).all())

    if import_codes:
        bcct_codes = set(session.scalars(
            select(distinct(DeclarationLine.item_code))
            .where(
                declaration_scope(session, company_id, year),
                DeclarationLine.customs_code.in_(import_codes),
            )
        ).all())
    else:
        # Loại hình unknown — count tất cả declaration codes làm fallback.
        bcct_codes = set(session.scalars(
            select(distinct(DeclarationLine.item_code))
            .where(declaration_scope(session, company_id, year))
        ).all())

    return len(m15_codes | bcct_codes)


def _count_distinct_tp(session: Session, company_id: int, year: int) -> int:
    """Số mã TP distinct = (mã trong M15a) ∪ (mã trong BCCT phía xuất)."""
    company_type = detect_company_type(session, company_id, year)
    export_codes = EXPORT_CODES.get(company_type, set())

    m15a_codes = set(session.scalars(
        select(distinct(SpBalance.product_code))
        .where(SpBalance.company_id == company_id, SpBalance.period_year == year)
    ).all())

    if export_codes:
        bcct_codes = set(session.scalars(
            select(distinct(DeclarationLine.item_code))
            .where(
                declaration_scope(session, company_id, year),
                DeclarationLine.customs_code.in_(export_codes),
            )
        ).all())
    else:
        bcct_codes = set()

    return len(m15a_codes | bcct_codes)


def _count_distinct_m16(session: Session, company_id: int, year: int) -> int:
    """Số mã NVL distinct trong định mức HIỆU LỰC của kỳ.

    Đếm theo định mức hiệu lực (bản khai gần nhất ≤ kỳ, issue #60) chứ KHÔNG theo
    `period_year == year`. Mẫu 16 kế thừa giữa các kỳ, nên một kỳ không khai lại có
    0 dòng `norms` mà C4.3 vẫn đánh giá được. Đếm theo kỳ thì mẫu số = 0,
    `compute_rule_score` trả 0, và mọi phát hiện C4.3 của kỳ đó KHÔNG vào điểm rủi
    ro — doanh nghiệp ngừng khai lại định mức thì điểm tự đẹp lên, đúng cái loạt
    ticket #56 sinh ra để chặn. Mẫu số phải đếm đúng tập mà check đã chấm.
    """
    from app.checks.effective_norms import effective_norms

    codes = {
        material_code
        for pairs in effective_norms(session, company_id, year).values()
        for _product_code, material_code in pairs
    }
    return len(codes)


def compute_denominators(session: Session, company_id: int, year: int) -> dict[str, int]:
    """Trả dict {scope: denominator} cho (company, year).

    Scope: nvl, tp, m16. Dùng làm mẫu số trong rate-based scoring.
    """
    return {
        "nvl": _count_distinct_nvl(session, company_id, year),
        "tp": _count_distinct_tp(session, company_id, year),
        "m16": _count_distinct_m16(session, company_id, year),
    }


def denominator_for_rule(
    check_code: str, denominators: dict[str, int],
) -> int:
    """Lookup denominator cho 1 check. Fallback 'nvl' nếu chưa map (an toàn)."""
    scope = RULE_SCOPE.get(check_code, "nvl")
    return denominators.get(scope, 0)


def extended_rule_scope(session) -> dict[str, str]:
    """RULE_SCOPE built-in + scope của các check mở rộng đã publish.

    Dùng cho scoring để check tự do (X.*) được tính vào cả mẫu số lẫn trần
    `max_raw`. Check thiếu `scope` rơi về 'nvl' (an toàn) qua `.get` ở caller.
    """
    from sqlalchemy import select

    from app.models.check_definition import CheckDefinition, CheckStatus

    scope = dict(RULE_SCOPE)
    for code, sc in session.execute(
        select(CheckDefinition.code, CheckDefinition.scope).where(
            CheckDefinition.status == CheckStatus.PUBLISHED
        )
    ).all():
        scope[code] = sc if sc in ("nvl", "tp", "m16") else "nvl"
    return scope


__all__ = [
    "RULE_SCOPE",
    "compute_denominators",
    "denominator_for_rule",
    "extended_rule_scope",
]
