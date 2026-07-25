"""Sổ quyết toán (book) — nhãn + gate hiển thị theo sổ (ADR #19 Revision — UI).

Một pháp nhân có thể giữ nhiều sổ quyết toán khác loại hình (004: EPE + GC). Cột
`book` trên `nvl_balances`/`sp_balances`/`norms`/`findings` mang mã sổ; `null` =
pháp nhân một sổ (002/006) → KHÔNG có chrome theo sổ. Xem GLOSSARY `Sổ quyết toán
(book)`, `Pháp nhân nhiều sổ`, `Chung (phát hiện liên sổ)`.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Finding, Norm, NvlBalance, SpBalance

# Known-map mã sổ → nhãn tiếng Việt. Book code là chuỗi tự do per-pháp-nhân
# (không enum) — mã lạ dùng fallback `Sổ {code}`, null → "Chung (liên sổ)".
BOOK_LABELS: dict[str, str] = {
    "EPE": "Sổ EPE (chế xuất)",
    "GC": "Sổ GC (gia công)",
}

CHUNG_LABEL = "Chung (liên sổ)"

# Nguồn book ở tầng dữ liệu — nơi book THỰC SỰ nằm (KHÔNG suy từ findings, vì sổ
# sạch 0 finding vẫn là một sổ).
_BOOK_COLUMNS = (
    (NvlBalance, NvlBalance.book),
    (SpBalance, SpBalance.book),
    (Norm, Norm.book),
)


def book_label(code: str | None) -> str:
    """Nhãn tiếng Việt cho một mã sổ; null → 'Chung (liên sổ)', lạ → 'Sổ {code}'."""
    if code is None:
        return CHUNG_LABEL
    return BOOK_LABELS.get(code, f"Sổ {code}")


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
