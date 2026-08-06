"""Phát hiện loại hình doanh nghiệp từ mã loại hình BCCT.

Theo §4.0 đề án:
    DNCX    — Doanh nghiệp chế xuất:     nhập E11/E15/E13 · xuất E42
    GIA_CONG — Gia công thương nhân NN: nhập E21/E23     · xuất E52/E54
    SXXK    — Sản xuất xuất khẩu:        nhập E31/E33    · xuất E62

Một số tờ khai chung: B13 (tái xuất), A42 (chuyển mục đích sử dụng nội địa).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.checks.scope import declaration_scope
from app.models import DeclarationLine, NvlBalance, SpBalance


class CompanyType(StrEnum):
    DNCX = "DNCX"
    GIA_CONG = "GIA_CONG"
    SXXK = "SXXK"
    # Thuê gia công Ở NƯỚC NGOÀI — ảnh gương của ba loại trên: NVL đi RA (E82),
    # thành phẩm về LẠI (E41). Cột biểu cân đối đem đối chiếu vì thế cũng đảo:
    # Mẫu 15 lấy `xuất kho để sản xuất` (không phải `nhập trong kỳ`), Mẫu 15a lấy
    # `nhập trong kỳ` (không phải `xuất khẩu`). Đo trên DN_005 2025: 11/11 mã NVL
    # có `xuất kho để sản xuất` == đúng lượng E82; Mẫu 15a `nhập trong kỳ` == E41.
    GIA_CONG_NN = "GIA_CONG_NN"
    UNKNOWN = "UNKNOWN"


# Mã loại hình NVL nhập (chỉ NVL, KHÔNG bao gồm MMTB).
# E13 = nhập máy móc thiết bị miễn thuế của DNCX → KHÔNG nằm trong M15 (M15 chỉ NVL).
# Dùng cho C1.1 / C1.2 / C1.3 / C1.7 + denominator NVL.
@dataclass(frozen=True)
class Pairing:
    """Tờ khai nào đối chiếu với CỘT nào của biểu cân đối.

    Trước đây cặp (tập mã, cột) bị gắn cứng trong từng check: luôn là
    `M15.import_qty` với tập mã nhập, `M15a.export_qty` với tập mã xuất. Đúng cho
    ba loại hình đầu, SAI cho thuê gia công ở nước ngoài — ở đó dòng vật tư đảo
    chiều nên phải đổi CẢ HAI vế, thêm mã vào tập cũ không sửa được.
    """

    nvl_codes: frozenset[str]
    nvl_column: str
    sp_codes: frozenset[str]
    sp_column: str


PAIRING: dict[CompanyType, Pairing] = {
    CompanyType.DNCX: Pairing(
        frozenset({"E11", "E15"}), "import_qty", frozenset({"E42"}), "export_qty"),
    CompanyType.GIA_CONG: Pairing(
        frozenset({"E21", "E23"}), "import_qty", frozenset({"E52", "E54"}), "export_qty"),
    CompanyType.SXXK: Pairing(
        frozenset({"E31", "E33"}), "import_qty", frozenset({"E62"}), "export_qty"),
    CompanyType.GIA_CONG_NN: Pairing(
        frozenset({"E82"}), "production_out_qty", frozenset({"E41"}), "intake_qty"),
}

IMPORT_CODES = {t: set(p.nvl_codes) for t, p in PAIRING.items()}

EXPORT_CODES = {t: set(p.sp_codes) for t, p in PAIRING.items()}

# Mã MMTB (máy móc thiết bị) miễn thuế — không phải NVL, có check riêng (C3.1, C4.x WIP).
MMTB_CODES = {"E13"}

# Mã dùng chung, không phân biệt loại hình DN (B13 tái xuất, A42 chuyển MĐSD nội địa).
SHARED_CODES = {"B13", "A42"}

# Tập mã giúp detect company type — gồm cả MMTB (E13 là chỉ báo DNCX rõ ràng).
_DETECT_IMPORT_CODES = {
    CompanyType.DNCX: IMPORT_CODES[CompanyType.DNCX] | MMTB_CODES,
    CompanyType.GIA_CONG: IMPORT_CODES[CompanyType.GIA_CONG],
    CompanyType.SXXK: IMPORT_CODES[CompanyType.SXXK],
    CompanyType.GIA_CONG_NN: IMPORT_CODES[CompanyType.GIA_CONG_NN],
}


def _vote(rows: Iterable[tuple[str | None, int]]) -> CompanyType:
    counts: dict[CompanyType, int] = {t: 0 for t in CompanyType if t != CompanyType.UNKNOWN}
    for code, n in rows:
        if not code:
            continue
        for t in counts:
            if code in _DETECT_IMPORT_CODES[t] or code in EXPORT_CODES[t]:
                counts[t] += n

    best_type, best_count = max(counts.items(), key=lambda kv: kv[1])
    return best_type if best_count > 0 else CompanyType.UNKNOWN


def detect_company_type(session: Session, company_id: int, year: int) -> CompanyType:
    """Đếm số dòng BCCT theo mã loại hình; chọn nhóm có nhiều dòng nhất."""
    rows = session.execute(
        select(DeclarationLine.customs_code, func.count())
        .where(declaration_scope(session, company_id, year))
        .group_by(DeclarationLine.customs_code)
    ).all()
    return _vote(rows)


def _book_filter(model, book: str | None):
    return model.book.is_(None) if book is None else model.book == book


def detect_book_types(
    session: Session, company_id: int, year: int
) -> dict[str | None, CompanyType]:
    """Loại hình cho TỪNG sổ quyết toán.

    Bỏ phiếu toàn pháp nhân chọn được đúng một loại hình, nên sổ nhỏ luôn thua sổ
    lớn: DN_005 2025 có 17.756 dòng E31/E62 áp đảo 250 dòng E82/E41 → cả hai sổ
    đều bị coi là SXXK. Ở đây phiếu chỉ đếm tờ khai có mã hàng THUỘC sổ đó
    (`declaration_lines` không mang cột `book`, sổ suy qua mã hàng).
    """
    books = sorted(
        set(
            session.scalars(
                select(NvlBalance.book)
                .where(NvlBalance.company_id == company_id, NvlBalance.period_year == year)
                .distinct()
            )
        )
        | set(
            session.scalars(
                select(SpBalance.book)
                .where(SpBalance.company_id == company_id, SpBalance.period_year == year)
                .distinct()
            )
        ),
        key=lambda b: (b is None, b or ""),
    )
    if books in ([], [None]):
        return {None: detect_company_type(session, company_id, year)}

    out: dict[str | None, CompanyType] = {}
    fallback: CompanyType | None = None
    for book in books:
        nvl_codes = (
            select(NvlBalance.material_code)
            .where(NvlBalance.company_id == company_id, NvlBalance.period_year == year)
            .where(_book_filter(NvlBalance, book))
        )
        sp_codes = (
            select(SpBalance.product_code)
            .where(SpBalance.company_id == company_id, SpBalance.period_year == year)
            .where(_book_filter(SpBalance, book))
        )
        rows = session.execute(
            select(DeclarationLine.customs_code, func.count())
            .where(
                declaration_scope(session, company_id, year),
                or_(
                    DeclarationLine.item_code.in_(nvl_codes),
                    DeclarationLine.item_code.in_(sp_codes),
                ),
            )
            .group_by(DeclarationLine.customs_code)
        ).all()
        t = _vote(rows)
        if t is CompanyType.UNKNOWN:
            if fallback is None:
                fallback = detect_company_type(session, company_id, year)
            t = fallback
        out[book] = t
    return out


def mixed_book_pairings(
    session: Session, company_id: int, year: int
) -> dict[str | None, Pairing] | None:
    """Cặp (tập mã, cột) theo sổ — hoặc None khi KHÔNG cần tách sổ.

    Trả None cho pháp nhân một sổ VÀ cho pháp nhân nhiều sổ mà mọi sổ cùng loại
    hình (004: hai sổ EPE + GC nhưng cả hai đều DNCX). Khi đó check giữ nguyên
    đường cũ — gộp mọi sổ, một tập mã — nên DN đang chạy không đổi kết quả.
    """
    types = detect_book_types(session, company_id, year)
    if len(types) < 2 or len(set(types.values())) < 2:
        return None
    return {b: PAIRING[t] for b, t in types.items() if t in PAIRING}


def import_codes_for(company_type: CompanyType) -> set[str]:
    return IMPORT_CODES.get(company_type, set())


def export_codes_for(company_type: CompanyType) -> set[str]:
    return EXPORT_CODES.get(company_type, set())
