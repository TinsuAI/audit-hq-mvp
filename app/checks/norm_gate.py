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
from app.checks.not_evaluable import (
    REMEDY_NEED_OTHER_PERIOD_OR_CONFIRMATION,
    REMEDY_NOTHING_TO_LOAD,
    TARGET_COMPANY_FIELD,
    TARGET_PERIOD,
    NotEvaluable,
    RemedyClassification,
    RemedyTarget,
)
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


def is_boundary_period(session: Session, company_id: int, year: int) -> bool:
    """Kỳ này là kỳ biên CHƯA được xác nhận là năm đầu nộp BCQT?

    True nghĩa là không phân biệt được "chưa từng khai định mức" với "đã khai trước
    cửa sổ dữ liệu đang có". C4.3 lấy đây làm điều kiện chặn; C4.9 vẫn liệt kê mã
    nhưng gắn kèm cảnh báo này để cán bộ đi hỏi hồ sơ kỳ trước thay vì kết luận
    doanh nghiệp không khai (issue #61 × #62).
    """
    company = session.get(Company, company_id)
    first_bcqt_year = company.first_bcqt_year if company is not None else None
    earliest = earliest_period_held(session, company_id)
    return earliest is not None and year == earliest and first_bcqt_year != year


def periods_without_norms(session: Session, company_id: int, year: int) -> list[int]:
    """Các kỳ TRƯỚC `year`, trong khoảng dữ liệu của DN, chưa có dòng định mức nào.

    Khoảng dữ liệu = [kỳ sớm nhất đang giữ, `year`) — lấy TRỌN dải số nguyên chứ
    không chỉ các kỳ đã có dòng: kỳ trống giữa dải đúng là kỳ Mẫu 16 chưa nạp, mà
    đó chính là thứ còn nạp được. Kỳ đang xét KHÔNG nằm trong dải: Mẫu 16 khuyết
    của chính kỳ này là việc của cổng thiếu nguồn ở bộ điều phối (lớp 1).
    """
    earliest = earliest_period_held(session, company_id)
    if earliest is None:
        return []
    declared = set(
        session.scalars(
            select(Norm.period_year)
            .where(Norm.company_id == company_id, Norm.period_year < year)
            .distinct()
        ).all()
    )
    return [y for y in range(earliest, year) if y not in declared]


def classify_boundary_period() -> RemedyClassification:
    """(lớp, đích) của nhánh kỳ biên — lớp 2, đích là trường `first_bcqt_year` của DN.

    Không nạp file nào gỡ được: thứ còn thiếu là một xác nhận ở mức doanh nghiệp.
    """
    return (
        REMEDY_NEED_OTHER_PERIOD_OR_CONFIRMATION,
        RemedyTarget(TARGET_COMPANY_FIELD, "first_bcqt_year"),
    )


def classify_norm_coverage(session: Session, company_id: int, year: int) -> RemedyClassification:
    """(lớp, đích) của nhánh độ phủ — tính THEO TỪNG LẦN, không tĩnh theo chỗ gọi.

    Còn kỳ trước nào trong khoảng dữ liệu chưa có dòng định mức thì định mức thiếu
    có thể đang nằm ở Mẫu 16 chưa nạp → lớp 2, đích là kỳ trống SỚM NHẤT (định mức
    khai ở kỳ sớm hơn có hiệu lực cho các kỳ sau, xem `effective_norms`). Hết kỳ
    trống thì không còn gì nạp được: "chưa từng khai định mức" là kết luận về DN.
    """
    gaps = periods_without_norms(session, company_id, year)
    if gaps:
        return REMEDY_NEED_OTHER_PERIOD_OR_CONFIRMATION, RemedyTarget(TARGET_PERIOD, gaps[0])
    return REMEDY_NOTHING_TO_LOAD, None


def norm_coverage_gate(session: Session, company_id: int, year: int) -> NotEvaluable | None:
    """`NotEvaluable` kèm lý do + lớp cách gỡ nếu (DN, kỳ) vướng cổng; None nếu đánh
    giá được. Lớp lấy từ chính hàm phân loại mà màn dữ liệu gọi lúc hiển thị — một
    hàm cho cả hai đường thì trạng thái đã lưu và dự đoán không lệch nhau."""
    if is_boundary_period(session, company_id, year):
        remedy, _ = classify_boundary_period()
        return NotEvaluable(_boundary_reason(year), remedy=remedy)

    missing = products_without_norm(session, company_id, year)
    if missing:
        remedy, _ = classify_norm_coverage(session, company_id, year)
        return NotEvaluable(_coverage_reason(missing), remedy=remedy)
    return None


__all__ = [
    "classify_boundary_period",
    "classify_norm_coverage",
    "earliest_period_held",
    "is_boundary_period",
    "norm_coverage_gate",
    "periods_without_norms",
]
