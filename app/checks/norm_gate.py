"""Cổng độ phủ định mức cho C4.3 (issue #62 — quyết định Q1 + Q3).

Hai điều kiện, cái nào đúng cũng làm C4.3 trả `NotEvaluable` cho cả (DN, kỳ):

- **Độ phủ định mức (Q3)** — có mã thành phẩm sản xuất trong kỳ mà chưa từng khai
  định mức ở bất kỳ kỳ nào ≤ kỳ đang xét. Cổng NHỊ PHÂN: không ngưỡng phần trăm,
  không cân theo tỷ trọng sản lượng (cả hai đã bị bác). Chặn cả nhóm chứ không
  nhiễm theo từng mã, vì thành phẩm chưa khai định mức thì không biết nó tiêu hao
  nguyên vật liệu nào — không khoanh được vùng ảnh hưởng.
- **Kỳ biên (Q1)** — kỳ sớm nhất hệ thống đang giữ của DN, trừ khi
  `companies.first_bcqt_year` xác nhận đó đúng là năm đầu nộp BCQT. NULL nghĩa là
  chưa biết nên vẫn chặn. Ở kỳ biên không phân biệt được "chưa từng khai" với "đã
  khai trước cửa sổ dữ liệu đang có", và định mức kế thừa từ trước cửa sổ cũng
  không đọc được nên phép nhân Σ(định_mức × sản_lượng) thiếu vế.

Kỳ biên xét TRƯỚC: ở đó chính kết quả của điều kiện độ phủ cũng không tin được.

Độ mịn theo SỔ: C4.3 đánh giá từng sổ quyết toán riêng, nhưng `check_runs` khoá
theo (DN, kỳ) nên không lưu được trạng thái theo sổ. Bất kỳ sổ nào vướng điều kiện
độ phủ thì cả lần chạy `not_evaluable` — đúng tinh thần "chặn cả nhóm" nâng lên
mức lần chạy. Lý do có nêu tên sổ và số mã của từng sổ.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.books import book_label
from app.checks.effective_norms import products_without_norm
from app.checks.not_evaluable import NotEvaluable
from app.models import Company, Norm, NvlBalance, SpBalance

# Cửa sổ dữ liệu BCQT của DN = các kỳ có dòng ở ba bảng Tầng 1 mà C4.3 đọc. Không
# dùng `company_periods`: kỳ có dòng ở đó nhưng chưa nạp M15/M15a/M16 vẫn không cho
# biết định mức đã khai trước đó hay chưa.
_PERIOD_SOURCES = (Norm, SpBalance, NvlBalance)


def earliest_period_held(session: Session, company_id: int) -> int | None:
    """Kỳ sớm nhất hệ thống đang giữ dữ liệu BCQT của DN; None nếu chưa có gì."""
    years = [
        session.scalar(
            select(func.min(model.period_year)).where(model.company_id == company_id)
        )
        for model in _PERIOD_SOURCES
    ]
    present = [y for y in years if y is not None]
    return min(present) if present else None


def _boundary_reason(year: int) -> str:
    return (
        f"Kỳ {year} là kỳ sớm nhất hệ thống đang có dữ liệu của doanh nghiệp và chưa ghi "
        "nhận năm đầu nộp báo cáo quyết toán, nên không phân biệt được thành phẩm chưa "
        "từng khai định mức với thành phẩm đã khai trước kỳ này."
    )


def _coverage_reason(missing: dict[str | None, set[str]]) -> str:
    total = sum(len(codes) for codes in missing.values())
    detail = ""
    if list(missing) != [None]:
        per_book = "; ".join(
            f"{book_label(book)}: {len(missing[book])} mã"
            for book in sorted(missing, key=lambda b: (b is None, b or ""))
        )
        detail = f" — {per_book}"
    return (
        f"{total} mã thành phẩm có sản xuất trong kỳ nhưng chưa từng khai định mức ở kỳ "
        f"này hoặc kỳ trước{detail}. Không có định mức thì không xác định được thành phẩm "
        "tiêu hao nguyên vật liệu nào."
    )


def norm_coverage_gate(session: Session, company_id: int, year: int) -> NotEvaluable | None:
    """`NotEvaluable` kèm lý do nếu (DN, kỳ) vướng cổng; None nếu đánh giá được."""
    company = session.get(Company, company_id)
    first_bcqt_year = company.first_bcqt_year if company is not None else None
    earliest = earliest_period_held(session, company_id)
    if earliest is not None and year == earliest and first_bcqt_year != year:
        return NotEvaluable(_boundary_reason(year))

    missing = products_without_norm(session, company_id, year)
    if missing:
        return NotEvaluable(_coverage_reason(missing))
    return None


__all__ = ["earliest_period_held", "norm_coverage_gate"]
