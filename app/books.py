"""Sổ quyết toán (book) — nhãn + gate hiển thị theo sổ (ADR #19 Revision — UI).

Một pháp nhân có thể giữ nhiều sổ quyết toán khác loại hình (004: EPE + GC). Cột
`book` trên `nvl_balances`/`sp_balances`/`norms`/`findings` mang mã sổ; `null` =
pháp nhân một sổ (002/006) → KHÔNG có chrome theo sổ. Xem GLOSSARY `Sổ quyết toán
(book)`, `Pháp nhân nhiều sổ`, `Chung (phát hiện liên sổ)`.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import DataFile, Finding, Norm, NvlBalance, SpBalance
from app.models.data_file import SETTLEMENT_SLOTS

# Known-map mã sổ → nhãn tiếng Việt. Book code là chuỗi tự do per-pháp-nhân
# (không enum) — mã lạ dùng fallback `Sổ {code}`, null → "Liên sổ".
BOOK_LABELS: dict[str, str] = {
    "EPE": "Sổ EPE (chế xuất)",
    "GC": "Sổ GC (gia công)",
}

# Nhãn UI cho finding book=NULL ở pháp nhân nhiều sổ (phát hiện liên sổ — cross-layer
# đối chiếu tờ khai dùng chung với UNION các sổ, không quy được về sổ nào).
CHUNG_LABEL = "Liên sổ"

# Nguồn book ở tầng dữ liệu — nơi book THỰC SỰ nằm (KHÔNG suy từ findings, vì sổ
# sạch 0 finding vẫn là một sổ).
_BOOK_COLUMNS = (
    (NvlBalance, NvlBalance.book),
    (SpBalance, SpBalance.book),
    (Norm, Norm.book),
)


def book_label(code: str | None) -> str:
    """Nhãn tiếng Việt cho một mã sổ; null → 'Liên sổ', lạ → 'Sổ {code}'."""
    if code is None:
        return CHUNG_LABEL
    return BOOK_LABELS.get(code, f"Sổ {code}")


def normalize_book(raw: str | None) -> str | None:
    """Chuẩn hoá mã sổ nhập ở selector review: trim + upper; rỗng → None (một sổ)."""
    if raw is None:
        return None
    code = raw.strip().upper()
    return code or None


def company_books(db: Session, company_id: int, year: int) -> list[str]:
    """Tập mã sổ (book khác null) của một pháp nhân theo năm, đã sort.

    Nguồn = `nvl_balances ∪ sp_balances ∪ norms`. KHÔNG suy từ findings.
    """
    books: set[str] = set()
    for model, col in _BOOK_COLUMNS:
        books |= set(
            db.scalars(
                select(col)
                .where(
                    model.company_id == company_id,
                    model.period_year == year,
                    col.is_not(None),
                )
                .distinct()
            ).all()
        )
    return sorted(books)


def is_multi_book(db: Session, company_id: int, year: int) -> bool:
    """Pháp nhân nhiều sổ ⇔ ≥2 sổ quyết toán khác loại hình trong năm."""
    return len(company_books(db, company_id, year)) >= 2


def company_book_codes(db: Session, company_id: int) -> list[str]:
    """Mọi mã sổ của pháp nhân, MỌI kỳ — gồm cả nhãn đã gán cho file chưa nạp.

    `company_books` bó theo năm, nên một kỳ vừa mở của DN nhiều sổ trả về rỗng: chưa
    có dòng nào mang sổ. Nút nạp của kỳ đó khi ấy không khoá, và lượt nạp dựng lại
    hai sổ thành một sổ gộp im lặng (004: EPE + GC). Ô chọn sổ và cổng khoá phải hỏi
    ở mức pháp nhân, cộng thêm nhãn đã gán trên `data_files` của chính kỳ đang làm.
    """
    codes: set[str] = set()
    for model, col in _BOOK_COLUMNS:
        codes |= set(db.scalars(
            select(col).where(model.company_id == company_id, col.is_not(None)).distinct()
        ).all())
    codes |= set(db.scalars(
        select(DataFile.book).where(
            DataFile.company_id == company_id, DataFile.book.is_not(None)
        ).distinct()
    ).all())
    return sorted(codes)


@dataclass(frozen=True)
class BookLock:
    """Tình trạng gán sổ của một kỳ — TẦNG CHẶN SỚM của nút nạp (#88).

    Một hàm, hai nơi đọc: màn dữ liệu (khoá nút, in câu thiếu file nào) và handler
    nạp (từ chối xếp việc). Tách đôi thì nút hiện một đằng, máy chủ làm một nẻo.

    Chặt hơn `book_assignment_error` một cách có chủ ý: cổng kia bó theo năm nên kỳ
    mới của DN nhiều sổ lọt qua cả hai tầng. `IngestPlanError` vẫn giữ nguyên làm
    tầng chặn cuối cho đường dòng lệnh.
    """

    options: tuple[str, ...]
    untagged: tuple[str, ...]

    @property
    def multi_book(self) -> bool:
        return len(self.options) >= 2

    @property
    def locked(self) -> bool:
        return self.multi_book and bool(self.untagged)

    @property
    def message(self) -> str:
        if not self.locked:
            return ""
        return (
            f"Chưa nạp được: còn {len(self.untagged)} file quyết toán chưa gán sổ — "
            + ", ".join(self.untagged)
            + ". Chọn sổ cho từng file rồi bấm nạp."
        )


def book_lock(db: Session, company_id: int, year: int) -> BookLock:
    """Ô chọn sổ nào được hiện, và file quyết toán nào của kỳ còn chưa gán sổ."""
    options = company_book_codes(db, company_id)
    rows = db.scalars(
        select(DataFile).where(
            DataFile.company_id == company_id,
            DataFile.period_year == year,
            DataFile.slot.in_(SETTLEMENT_SLOTS),
        )
    ).all()
    # Tờ khai (bcct) luôn toàn pháp nhân — không nằm trong phép đếm này.
    untagged = sorted({r.original_filename for r in rows if not r.book})
    return BookLock(options=tuple(options), untagged=tuple(untagged))


def _nvl_code_counts(db: Session, company_id: int, year: int) -> dict[str, int]:
    """Số mã NVL riêng biệt theo sổ (chỉ book khác null)."""
    rows = db.execute(
        select(NvlBalance.book, func.count(func.distinct(NvlBalance.material_code)))
        .where(
            NvlBalance.company_id == company_id,
            NvlBalance.period_year == year,
            NvlBalance.book.is_not(None),
        )
        .group_by(NvlBalance.book)
    ).all()
    return {book: n for book, n in rows}


def _finding_counts(db: Session, company_id: int, year: int) -> dict[str | None, int]:
    """Số phát hiện thật (không combo) theo sổ; key None = book IS NULL (Chung)."""
    rows = db.execute(
        select(Finding.book, func.count())
        .where(
            Finding.company_id == company_id,
            Finding.period_year == year,
            ~Finding.check_code.startswith("COMBO_"),
        )
        .group_by(Finding.book)
    ).all()
    return {book: n for book, n in rows}


def book_summary(db: Session, company_id: int, year: int) -> dict | None:
    """Strip tổng quan theo sổ cho header (chỉ pháp nhân nhiều sổ, ngược lại None).

    Trả `{"books": [{code, label, nvl_codes, findings}], "chung": {label, findings}
    | None}`. Con số mã NVL làm "0 phát hiện" đọc thành ĐÃ đánh giá-sạch (không phải
    chưa chạy). Luôn tổng toàn pháp nhân — KHÔNG theo bộ lọc `?book=`.
    """
    books = company_books(db, company_id, year)
    if len(books) < 2:
        return None
    nvl_counts = _nvl_code_counts(db, company_id, year)
    find_counts = _finding_counts(db, company_id, year)
    cells = [
        {
            "code": code,
            "label": book_label(code),
            "nvl_codes": nvl_counts.get(code, 0),
            "findings": find_counts.get(code, 0),
        }
        for code in books
    ]
    chung_n = find_counts.get(None, 0)
    chung = {"label": CHUNG_LABEL, "findings": chung_n} if chung_n else None
    return {"books": cells, "chung": chung}
