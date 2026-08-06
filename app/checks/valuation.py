"""Quy phát hiện ra tiền — đơn giá bình quân từ tờ khai (sổ yêu cầu dòng 3.1, 4.1).

Cán bộ đọc danh sách phát hiện theo thứ tự tiền, không theo thứ tự mã: 5.000 phát
hiện xếp theo mã thì mã lớn nhất nằm ở trang 137. Đơn giá lấy từ chính tờ khai của
kỳ — `value_total` của BCCT đã là VNĐ (đo trên dữ liệu thật 06/08/2026: tỉ lệ
`value_total / (quantity × unit_price)` ≈ 1 ở dòng khai VND và ≈ 30.000 ở dòng khai
USD), nên không phải quy đổi tỷ giá.

Con số này để XẾP HẠNG, không phải số liệu kế toán: nó là bình quân gia quyền cả
kỳ, và nó tính theo đơn vị tính của TỜ KHAI — mã nào có đơn vị tờ khai lệch đơn vị
biểu quyết toán thì giá trị lệch đúng bằng hệ số quy đổi (C3.3 gắn cờ ca đó).
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.checks.scope import declaration_scope
from app.models import DeclarationLine


def material_prices_vnd(
    session: Session,
    company_id: int,
    year: int,
    customs_codes: set[str] | None = None,
) -> dict[str, float]:
    """{mã hàng → đơn giá bình quân VNĐ} theo tờ khai trong cửa sổ kỳ.

    `customs_codes` khoanh loại hình (vd chỉ tờ khai nhập NVL) — bỏ trống thì lấy
    mọi tờ khai của kỳ. Chỉ cộng dòng có cả lượng lẫn trị giá > 0: dòng thiếu một
    trong hai làm bình quân lệch xuống mà không báo gì.
    """
    q = (
        select(
            DeclarationLine.item_code,
            func.sum(DeclarationLine.value_total),
            func.sum(DeclarationLine.quantity),
        )
        .where(
            declaration_scope(session, company_id, year),
            DeclarationLine.item_code.is_not(None),
            DeclarationLine.quantity > 0,
            DeclarationLine.value_total > 0,
        )
        .group_by(DeclarationLine.item_code)
    )
    if customs_codes:
        q = q.where(DeclarationLine.customs_code.in_(customs_codes))

    prices: dict[str, float] = {}
    for code, value_sum, qty_sum in session.execute(q).all():
        if not qty_sum:
            continue
        prices[code] = float(value_sum) / float(qty_sum)
    return prices


def money_value(prices: dict[str, float], code: str, qty: float) -> float | None:
    """`qty` × đơn giá, hoặc None khi mã không có tờ khai nào để lấy giá.

    None ≠ 0: mã không tra được giá phải nằm CUỐI danh sách xếp theo tiền, không
    lẫn vào nhóm giá trị nhỏ.
    """
    price = prices.get(code)
    if price is None:
        return None
    return abs(qty) * price


__all__ = ["material_prices_vnd", "money_value"]
