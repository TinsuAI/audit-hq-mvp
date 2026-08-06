"""Định mức hiệu lực — Mẫu 16 kế thừa giữa các kỳ (issue #60).

Doanh nghiệp chỉ khai lại Mẫu 16 khi định mức thay đổi, nên lọc đúng
`period_year == year` sẽ làm mất định mức của mọi mã không khai lại. Định mức áp
cho kỳ N là bản khai có kỳ LỚN NHẤT mà ≤ N của cùng cặp (mã SP, mã NVL).

Gộp theo SỔ quyết toán: mỗi sổ là ledger riêng, định mức sổ này không kế thừa
sang sổ kia (ADR #19).

Kế thừa theo THÀNH PHẨM, không theo cặp (mã SP, mã NVL): bản khai mới của một
thành phẩm THAY TRỌN định mức cũ của chính nó. Thành phẩm A khai 2022, 2023 không
khai lại thì 2023 dùng bản 2022; sang 2025 khai bản mới thì 2025 dùng ĐÚNG bản
2025 — mã NVL có ở bản 2022 mà bản 2025 bỏ đi thì hết hiệu lực, không được sống
tiếp. Ghép từng cặp sẽ trộn hai bản khai thành một định mức chưa từng được khai.
Đo trên dữ liệu 06/08/2026: ghép theo cặp giữ thêm 774 cặp trên 126 mã TP ở 4 kỳ
(DN 8/2025 451, DN 10/2026 302, DN 10/2025 19, DN 10/2024 2), 0 ở các kỳ còn lại.
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
    #: Ghi chú Mẫu 16 ("x" = xuất xứ trong nước) — C4.1 loại NVL nội địa theo cột này.
    note: str | None = None


#: {sổ: {(mã SP, mã NVL): định mức hiệu lực}}
EffectiveNormMap = dict[str | None, dict[tuple[str, str], EffectiveNorm]]


def effective_norms(session: Session, company_id: int, year: int) -> EffectiveNormMap:
    """Định mức hiệu lực cho (DN, kỳ), gộp theo sổ.

    Hai bước, đúng thứ tự:

    1. Với mỗi (sổ, mã SP): tìm kỳ khai gần nhất mà ≤ `year` — đó là BẢN KHAI đang
       có hiệu lực của thành phẩm đó.
    2. Lấy TRỌN các dòng của bản khai đó, không lấy dòng của kỳ nào khác. Mã NVL
       chỉ có ở bản khai cũ hơn thì đã bị bản mới bỏ, không còn hiệu lực.

    Trong cùng bản khai, Mẫu 16 của một số DN lặp lại nguyên khối định mức cho mỗi
    đợt sản xuất — gộp về MỘT giá trị bằng MAX, đúng như `check_c4_3` vẫn làm, và
    bật cờ `divergent` khi các khối lặp không khớp nhau.
    """
    rows = session.execute(
        select(
            Norm.book,
            Norm.product_code,
            Norm.material_code,
            Norm.norm_qty,
            Norm.period_year,
            Norm.note,
        ).where(
            Norm.company_id == company_id,
            Norm.period_year <= year,
        )
    ).all()

    # Bước 1 — kỳ của bản khai đang hiệu lực, theo (sổ, mã SP).
    effective_year: dict[tuple[str | None, str], int] = {}
    for book, product_code, _material_code, _qty, period_year, _note in rows:
        key = (book, product_code)
        if period_year > effective_year.get(key, -1):
            effective_year[key] = period_year

    # Bước 2 — chỉ giữ dòng thuộc chính bản khai đó.
    out: EffectiveNormMap = defaultdict(dict)
    for book, product_code, material_code, norm_qty, period_year, note in rows:
        if period_year != effective_year[(book, product_code)]:
            continue
        key = (product_code, material_code)
        qty = norm_qty or 0.0
        cur = out[book].get(key)
        if cur is None:
            out[book][key] = EffectiveNorm(
                product_code=product_code,
                material_code=material_code,
                norm_qty=qty,
                source_year=period_year,
                divergent=False,
                note=note,
            )
        elif abs(cur.norm_qty - qty) > 1e-9:
            # Khối lặp lệch định mức trong cùng bản khai — lấy MAX, không chọn thầm.
            out[book][key] = EffectiveNorm(
                product_code=product_code,
                material_code=material_code,
                norm_qty=max(cur.norm_qty, qty),
                source_year=period_year,
                divergent=True,
                note=cur.note or note,
            )
    return out


@dataclass(frozen=True)
class ConsumedMaterial:
    """Một mã NVL có tiêu hao lý thuyết > 0 trong kỳ."""

    material_code: str
    note: str | None
    #: Các kỳ đã khai những định mức đang áp cho mã này — chứng cứ phải trỏ đúng đó.
    source_years: tuple[int, ...]


def consumed_materials(
    session: Session, company_id: int, year: int
) -> dict[str | None, dict[str, ConsumedMaterial]]:
    """{sổ: {mã NVL: ConsumedMaterial}} cho NVL có TIÊU HAO LÝ THUYẾT > 0 trong kỳ.

    Tức là mã có định mức hiệu lực gắn với một thành phẩm thực sự có sản lượng sản
    xuất trong kỳ. Đây là tập mà C4.3 bỏ qua khi không có dòng M15 (issue #59) và
    C4.1 phải nhận lại — nếu không, mã có định mức kế thừa mà thiếu nguồn sẽ không
    check nào báo.
    """
    norms = effective_norms(session, company_id, year)
    produced = produced_products(session, company_id, year)

    notes: dict[tuple[str | None, str], str | None] = {}
    years: dict[tuple[str | None, str], set[int]] = defaultdict(set)
    for book, pairs in norms.items():
        made = produced.get(book, set())
        for (product_code, material_code), norm in pairs.items():
            if product_code not in made or norm.norm_qty <= 0:
                continue
            key = (book, material_code)
            years[key].add(norm.source_year)
            if notes.get(key) is None:
                notes[key] = norm.note

    out: dict[str | None, dict[str, ConsumedMaterial]] = defaultdict(dict)
    for (book, material_code), source_years in years.items():
        out[book][material_code] = ConsumedMaterial(
            material_code=material_code,
            note=notes.get((book, material_code)),
            source_years=tuple(sorted(source_years)),
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

    Có DÒNG định mức là đủ, KHÔNG đòi `norm_qty > 0` — khác `consumed_materials`, chỗ
    đó đòi > 0 vì nó tính tiêu hao. Khai định mức bằng 0 vẫn là đã khai: độ phủ đạt,
    còn giá trị 0 là sai phạm riêng, đất của C4.5 ("định mức bằng 0 hoặc âm", chưa
    dựng). Gộp hai thứ vào đây thì một mã khai 0 sẽ chặn cả C4.3 với lý do "thiếu định
    mức", nói sai chuyện đang xảy ra. Đo trên pilot 06/08/2026: 0 mã rơi vào ca này,
    nên khác biệt hiện chưa đổi kết quả nào.
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
    "ConsumedMaterial",
    "EffectiveNorm",
    "EffectiveNormMap",
    "consumed_materials",
    "effective_norms",
    "produced_products",
    "production_intake",
    "products_without_norm",
]
