"""Trạng thái `not_evaluable` — kiểm tra KHÔNG kết luận vì thiếu đầu vào bắt buộc.

Khác `ok` kèm 0 phát hiện (đã đánh giá, không thấy sai phạm). Một check khai trạng
thái này bằng cách TRẢ VỀ `NotEvaluable(reason=...)` thay cho danh sách phát hiện:

    def check_c4_3(session, company_id, year) -> CheckResult:
        if chua_biet_dinh_muc:
            return NotEvaluable("Kỳ sớm nhất của DN, chưa biết năm đầu nộp BCQT.")
        return [...]

`run_checks()` ghi trạng thái + lý do vào `check_runs.status` / `check_runs.status_reason`,
và loại mã đó khỏi điểm rủi ro — cả phần cộng điểm lẫn phần trần (`.ai/GLOSSARY.md`).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CheckRun, Finding

STATUS_OK = "ok"
STATUS_ERROR = "error"
STATUS_NOT_EVALUABLE = "not_evaluable"

# Trùng độ dài cột `check_runs.status_reason`.
REASON_MAX_LEN = 255


@dataclass(frozen=True)
class NotEvaluable:
    """Giá trị check trả về THAY CHO list[Finding] khi không kết luận được.

    `reason` hiện nguyên văn trên UI cho cán bộ, nên phải nêu THIẾU GÌ chứ không
    chỉ nói "không đủ dữ liệu".
    """

    reason: str

    def __post_init__(self) -> None:
        if not self.reason or not self.reason.strip():
            raise ValueError("NotEvaluable phải kèm lý do — lý do hiện trên UI.")


# Kiểu trả về của một check: danh sách phát hiện, hoặc khai không đánh giá được.
CheckResult = list[Finding] | NotEvaluable


def truncate_reason(reason: str) -> str:
    """Cắt lý do vừa cột `check_runs.status_reason`."""
    text = reason.strip()
    return text if len(text) <= REASON_MAX_LEN else text[: REASON_MAX_LEN - 1] + "…"


def load_not_evaluable(session: Session, company_id: int, year: int) -> dict[str, str]:
    """{mã check → lý do} cho các check đang ở `not_evaluable` của (DN, năm).

    Đọc từ `check_runs` chứ không từ lần chạy hiện tại: chạy lẻ một mã vẫn phải
    thấy trạng thái các mã khác đã ghi ở lần chạy trước, nếu không thì điểm rủi ro
    nhảy qua lại giữa chạy lẻ và chạy đủ.
    """
    return {
        code: (reason or "")
        for code, reason in session.execute(
            select(CheckRun.check_code, CheckRun.status_reason).where(
                CheckRun.company_id == company_id,
                CheckRun.period_year == year,
                CheckRun.status == STATUS_NOT_EVALUABLE,
            )
        ).all()
    }


__all__ = [
    "REASON_MAX_LEN",
    "STATUS_ERROR",
    "STATUS_NOT_EVALUABLE",
    "STATUS_OK",
    "CheckResult",
    "NotEvaluable",
    "load_not_evaluable",
    "truncate_reason",
]
