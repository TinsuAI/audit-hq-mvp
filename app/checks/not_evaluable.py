"""Trạng thái `not_evaluable` — kiểm tra KHÔNG kết luận vì thiếu đầu vào bắt buộc.

Khác `ok` kèm 0 phát hiện (đã đánh giá, không thấy sai phạm). Một check khai trạng
thái này bằng cách TRẢ VỀ `NotEvaluable(reason=..., remedy=...)` thay cho danh sách
phát hiện:

    def check_c4_3(session, company_id, year) -> CheckResult:
        if chua_biet_dinh_muc:
            return NotEvaluable(
                "Kỳ sớm nhất của DN, chưa biết năm đầu nộp BCQT.",
                remedy=REMEDY_NEED_OTHER_PERIOD_OR_CONFIRMATION,
            )
        return [...]

`run_checks()` ghi trạng thái + lý do + lớp cách gỡ vào `check_runs.status` /
`check_runs.status_reason` / `check_runs.remedy`, và loại mã đó khỏi điểm rủi ro —
cả phần cộng điểm lẫn phần trần (`.ai/GLOSSARY.md`).

LỚP CÁCH GỠ (ADR #24 mục 2) là trường BẮT BUỘC và tính THEO TỪNG LẦN, không suy
theo mã kiểm tra (C4.3 sinh cả ba lớp) cũng không gán tĩnh theo chỗ gọi (nhánh độ
phủ định mức sinh lớp 2 hay 3 tuỳ còn kỳ trước nào chưa nạp). Quy tắc đơn điệu:
còn thứ nạp được thì cách gỡ là nạp nó; hết đường nạp mới là kết luận về DN.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CheckRun, Finding

STATUS_OK = "ok"
STATUS_ERROR = "error"
STATUS_NOT_EVALUABLE = "not_evaluable"

# Trùng độ dài cột `check_runs.status_reason`.
REASON_MAX_LEN = 255

# --- Lớp cách gỡ --------------------------------------------------------------

#: Thiếu nguồn Tầng 1 của CHÍNH kỳ này — nạp file kỳ này là gỡ được.
REMEDY_NEED_FILE_THIS_PERIOD = "need-file-this-period"
#: Cần dữ liệu kỳ khác, hoặc một xác nhận ở mức DN (điển hình: năm đầu nộp BCQT).
REMEDY_NEED_OTHER_PERIOD_OR_CONFIRMATION = "need-other-period-or-confirmation"
#: Không có gì nạp thêm được — đây là kết luận về DN, thuộc về màn phát hiện.
REMEDY_NOTHING_TO_LOAD = "nothing-to-load"

REMEDY_CLASSES = frozenset({
    REMEDY_NEED_FILE_THIS_PERIOD,
    REMEDY_NEED_OTHER_PERIOD_OR_CONFIRMATION,
    REMEDY_NOTHING_TO_LOAD,
})

# Trùng độ dài cột `check_runs.remedy`.
REMEDY_MAX_LEN = 48

# Ba loại đích của một cách gỡ.
TARGET_PERIOD = "period"
TARGET_COMPANY_FIELD = "company-field"
TARGET_DOCUMENT = "document-type"

TARGET_KINDS = frozenset({TARGET_PERIOD, TARGET_COMPANY_FIELD, TARGET_DOCUMENT})


@dataclass(frozen=True)
class RemedyTarget:
    """Đích của một cách gỡ: một kỳ, một trường của DN, hoặc một loại tài liệu.

    KHÔNG lưu xuống DB — hàm phân loại tính lại lúc hiển thị. Lưu đích thì đích đi
    stale ngay khi cán bộ nạp thêm file, trong khi lớp thì không.
    """

    kind: str
    #: Kỳ (int) · tên trường của DN (str) · mã nguồn Tầng 1 (str).
    value: str | int

    def __post_init__(self) -> None:
        if self.kind not in TARGET_KINDS:
            raise ValueError(f"Đích cách gỡ lạ: {self.kind!r}. Nhận: {sorted(TARGET_KINDS)}.")


#: Giá trị mọi hàm phân loại trả về: (lớp cách gỡ, đích) — đích rỗng khi không có.
RemedyClassification = tuple[str, RemedyTarget | None]


@dataclass(frozen=True)
class NotEvaluable:
    """Giá trị check trả về THAY CHO list[Finding] khi không kết luận được.

    `reason` hiện nguyên văn trên UI cho cán bộ, nên phải nêu THIẾU GÌ chứ không
    chỉ nói "không đủ dữ liệu". `remedy` nói cán bộ gỡ bằng cách nào — bắt buộc,
    không mặc định, để một chỗ quyết định mới không lặng lẽ ra đời thiếu lớp.
    """

    reason: str
    remedy: str = field(kw_only=True)

    def __post_init__(self) -> None:
        if not self.reason or not self.reason.strip():
            raise ValueError("NotEvaluable phải kèm lý do — lý do hiện trên UI.")
        if self.remedy not in REMEDY_CLASSES:
            raise ValueError(
                f"Lớp cách gỡ lạ: {self.remedy!r}. Nhận: {sorted(REMEDY_CLASSES)}."
            )


# Kiểu trả về của một check: danh sách phát hiện, hoặc khai không đánh giá được.
CheckResult = list[Finding] | NotEvaluable


def truncate_reason(reason: str) -> str:
    """Cắt lý do vừa cột `check_runs.status_reason`."""
    text = reason.strip()
    return text if len(text) <= REASON_MAX_LEN else text[: REASON_MAX_LEN - 1] + "…"


@dataclass(frozen=True)
class NotEvaluableRun:
    """Trạng thái ĐÃ LƯU của một mã: lý do hiện cho cán bộ + lớp cách gỡ.

    `remedy` rỗng ở dòng ghi trước migration cột `check_runs.remedy` — chỗ đọc phải
    dựng được cả ca đó, không suy lớp thay nó.
    """

    code: str
    reason: str
    remedy: str | None


def load_not_evaluable(
    session: Session, company_id: int, year: int
) -> dict[str, NotEvaluableRun]:
    """{mã check → (lý do, lớp cách gỡ)} cho các check `not_evaluable` của (DN, năm).

    Đọc từ `check_runs` chứ không từ lần chạy hiện tại: chạy lẻ một mã vẫn phải
    thấy trạng thái các mã khác đã ghi ở lần chạy trước, nếu không thì điểm rủi ro
    nhảy qua lại giữa chạy lẻ và chạy đủ.

    Hai chỗ đọc, hai nhu cầu: điểm rủi ro chỉ cần TẬP MÃ (duyệt map ra khoá), màn
    phát hiện cần cả lý do lẫn lớp đã lưu (ADR #24 mục 2 — một phân loại, hai nơi
    đọc).
    """
    return {
        code: NotEvaluableRun(code=code, reason=reason or "", remedy=remedy)
        for code, reason, remedy in session.execute(
            select(CheckRun.check_code, CheckRun.status_reason, CheckRun.remedy).where(
                CheckRun.company_id == company_id,
                CheckRun.period_year == year,
                CheckRun.status == STATUS_NOT_EVALUABLE,
            )
        ).all()
    }


__all__ = [
    "REASON_MAX_LEN",
    "REMEDY_CLASSES",
    "REMEDY_MAX_LEN",
    "REMEDY_NEED_FILE_THIS_PERIOD",
    "REMEDY_NEED_OTHER_PERIOD_OR_CONFIRMATION",
    "REMEDY_NOTHING_TO_LOAD",
    "STATUS_ERROR",
    "STATUS_NOT_EVALUABLE",
    "STATUS_OK",
    "TARGET_COMPANY_FIELD",
    "TARGET_DOCUMENT",
    "TARGET_KINDS",
    "TARGET_PERIOD",
    "CheckResult",
    "NotEvaluable",
    "NotEvaluableRun",
    "RemedyClassification",
    "RemedyTarget",
    "load_not_evaluable",
    "truncate_reason",
]
