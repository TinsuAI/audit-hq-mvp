"""Định mức hiệu lực — Mẫu 16 kế thừa giữa các kỳ (issue #60).

Doanh nghiệp chỉ khai lại Mẫu 16 khi định mức thay đổi, nên lọc đúng
`period_year == year` sẽ làm mất định mức của mọi mã không khai lại. Định mức áp
cho kỳ N là bản khai có kỳ LỚN NHẤT mà ≤ N của cùng cặp (mã SP, mã NVL).

Gộp theo SỔ quyết toán: mỗi sổ là ledger riêng, định mức sổ này không kế thừa
sang sổ kia (ADR #19).

Kế thừa tính theo CẶP (mã SP, mã NVL), không theo mã SP. Nghĩa là một mã NVL bị
bỏ khỏi định mức của một thành phẩm ở kỳ sau vẫn còn hiệu lực từ bản khai cũ.
Đo trên pilot 05/08/2026: hai cách chênh nhau 451/86.111 cặp (0,5%) ở DN 8/2025 và
302/44.480 (0,7%) ở DN 10/2026, 0 ở các (DN, kỳ) còn lại.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Norm, SpBalance


@dataclass(frozen=True)
class EffectiveNorm:
    """Một định mức đang có hiệu lực cho kỳ đang xét."""

    product_code: str
    material_code: str
    norm_qty: float
    source_year: int
    #: Cùng kỳ nguồn có nhiều khối lặp lệch giá trị → đã lấy MAX, ghi lại để hiện ra.
    divergent: bool


#: {sổ: {(mã SP, mã NVL): định mức hiệu lực}}
EffectiveNormMap = dict[str | None, dict[tuple[str, str], EffectiveNorm]]


def effective_norms(session: Session, company_id: int, year: int) -> EffectiveNormMap:
    """Định mức hiệu lực cho (DN, kỳ), gộp theo sổ.

    Với mỗi (sổ, mã SP, mã NVL): lấy các dòng Mẫu 16 có `period_year` lớn nhất mà
    ≤ `year`. Trong cùng kỳ nguồn đó, Mẫu 16 của một số DN lặp lại nguyên khối định
    mức cho mỗi đợt sản xuất — gộp về MỘT giá trị bằng MAX, đúng như `check_c4_3`
    vẫn làm, và bật cờ `divergent` khi các khối lặp không khớp nhau.
    """
    rows = session.execute(
        select(
            Norm.book,
            Norm.product_code,
            Norm.material_code,
            Norm.norm_qty,
            Norm.period_year,
        ).where(
            Norm.company_id == company_id,
            Norm.period_year <= year,
        )
    ).all()

    out: EffectiveNormMap = defaultdict(dict)
    for book, product_code, material_code, norm_qty, period_year in rows:
        key = (product_code, material_code)
        qty = norm_qty or 0.0
        cur = out[book].get(key)
        if cur is None or period_year > cur.source_year:
            out[book][key] = EffectiveNorm(
                product_code=product_code,
                material_code=material_code,
                norm_qty=qty,
                source_year=period_year,
                divergent=False,
            )
        elif period_year == cur.source_year and abs(cur.norm_qty - qty) > 1e-9:
            # Khối lặp lệch định mức trong cùng kỳ nguồn — lấy MAX, không chọn thầm.
            out[book][key] = EffectiveNorm(
                product_code=product_code,
                material_code=material_code,
                norm_qty=max(cur.norm_qty, qty),
                source_year=period_year,
                divergent=True,
            )
    return out


def production_intake(
    session: Session, company_id: int, year: int
) -> dict[str | None, dict[str, float]]:
    """{sổ: {mã TP: Σ sản lượng sản xuất nhập kho trong kỳ}} (Mẫu 15a).

    Chỉ giữ mã có ÍT NHẤT một dòng > 0; lượng là tổng qua mọi dòng của mã đó
    trong cùng sổ (dòng điều chỉnh âm, nếu có, được trừ vào tổng nhưng không làm
    mã biến mất khỏi danh sách đã sản xuất).
    """
    rows = session.execute(
        select(SpBalance.book, SpBalance.product_code, SpBalance.intake_qty).where(
            SpBalance.company_id == company_id,
            SpBalance.period_year == year,
        )
    ).all()

    totals: dict[str | None, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    produced: dict[str | None, set[str]] = defaultdict(set)
    for book, product_code, intake_qty in rows:
        qty = intake_qty or 0.0
        totals[book][product_code] += qty
        if qty > 0:
            produced[book].add(product_code)

    return {
        book: {code: totals[book][code] for code in sorted(codes)}
        for book, codes in produced.items()
    }


def produced_products(session: Session, company_id: int, year: int) -> dict[str | None, set[str]]:
    """{sổ: mã TP có sản lượng sản xuất nhập kho > 0 trong kỳ} (Mẫu 15a)."""
    return {
        book: set(codes) for book, codes in production_intake(session, company_id, year).items()
    }


def products_without_norm(
    session: Session, company_id: int, year: int
) -> dict[str | None, set[str]]:
    """{sổ: mã TP có sản xuất trong kỳ mà KHÔNG có định mức hiệu lực nào}.

    Đây vừa là đầu vào của C4.9 (liệt kê từng mã), vừa là điều kiện cổng của C4.3
    (issue #62): thiếu định mức thì không biết thành phẩm đó tiêu hao NVL nào.
    """
    norms = effective_norms(session, company_id, year)
    produced = produced_products(session, company_id, year)

    out: dict[str | None, set[str]] = {}
    for book, codes in produced.items():
        with_norm = {product_code for product_code, _ in norms.get(book, {})}
        missing = codes - with_norm
        if missing:
            out[book] = missing
    return out


__all__ = [
    "EffectiveNorm",
    "EffectiveNormMap",
    "effective_norms",
    "produced_products",
    "production_intake",
    "products_without_norm",
]
