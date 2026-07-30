"""Phạm vi kiểm tra sau thông quan (KTSTQ) 5 năm — VIEW, không phải khoá dữ liệu.

`companies.audit_decision_date` (D) là mốc duy nhất được LƯU. Cửa sổ `[D − 5 năm, D]`
TÍNH lúc render, neo trên `declaration_date` (= "Ngày ĐK") — đúng mốc khoản 3 Điều 77
Luật Hải quan 54/2014. Đổi D = re-render: không đụng dữ liệu, không dời
`data_version`, không xếp job.

Kỳ đầu bị cắt vẫn chạy ĐỦ check trên TRỌN kỳ (đẳng thức cân đối chỉ đúng trên trọn
kỳ); phần "ngoài phạm vi" chỉ là nhãn hiển thị, KHÔNG lưu trên finding.

Hình thái tương lai đã ghi nhận ở ADR #23: bảng `audit_engagements` nhiều đợt mỗi DN.
KHÔNG build bây giờ, và không được couple sâu hơn "đọc một cột date nullable".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select

from app.checks.scope import declaration_scope
from app.models import CheckRun, CompanyPeriod, DeclarationLine, Norm, NvlBalance, SpBalance
from app.pipeline.period import fiscal_bounds

AUDIT_YEARS = 5

STATUS_LABEL_VI = {
    "inside": "Trọn trong phạm vi",
    "cut_start": "Cắt đầu",
    "cut_end": "Cắt đuôi",
    "cut_both": "Cắt cả hai đầu",
    "outside": "Ngoài phạm vi",
}


def _minus_years(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year - years)
    except ValueError:  # 29/02 → năm không nhuận
        return d.replace(year=d.year - years, day=28)


def audit_window(decision_date: date) -> tuple[date, date]:
    """`[D − 5 năm, D]` — phạm vi neo trên ngày đăng ký tờ khai."""
    return _minus_years(decision_date, AUDIT_YEARS), decision_date


def classify_period(
    window: tuple[date, date], period_from: date, period_to: date
) -> str:
    """Kỳ quyết toán nằm thế nào so với cửa sổ kiểm tra."""
    audit_from, audit_to = window
    if period_to < audit_from or period_from > audit_to:
        return "outside"
    starts_early = period_from < audit_from
    ends_late = period_to > audit_to
    if starts_early and ends_late:
        return "cut_both"
    if starts_early:
        return "cut_start"
    if ends_late:
        return "cut_end"
    return "inside"


def label_year_of(d: date, fiscal_start_month: int) -> int:
    """Nhãn kỳ chứa ngày `d` — nhãn là năm BẮT ĐẦU kỳ (ADR #23 T2)."""
    if fiscal_start_month == 1:
        return d.year
    return d.year if d.month >= fiscal_start_month else d.year - 1


@dataclass(frozen=True)
class PeriodCoverage:
    period_year: int
    period_from: date
    period_to: date
    status: str
    has_bcqt: bool
    checks_run: int
    checks_waiting: int

    @property
    def status_label(self) -> str:
        return STATUS_LABEL_VI.get(self.status, self.status)


def scope_coverage(session, company) -> list[PeriodCoverage] | None:
    """Chiếu cửa sổ kiểm tra lên các kỳ quyết toán của DN.

    Trả None khi DN chưa đặt ngày quyết định — mọi màn giữ nguyên như cũ.

    Kỳ lấy từ `company_periods` khi có, còn lại suy từ niên độ DN, nên kỳ ĐUÔI (chưa
    nạp gì, chưa đến hạn nộp BCQT) vẫn xuất hiện thay vì biến mất khỏi màn.
    """
    if company.audit_decision_date is None:
        return None

    window = audit_window(company.audit_decision_date)
    audit_from, audit_to = window
    month = company.fiscal_start_month or 1

    stored = {
        r.period_year: r
        for r in session.scalars(
            select(CompanyPeriod).where(CompanyPeriod.company_id == company.id)
        ).all()
    }

    labels = set(range(label_year_of(audit_from, month), label_year_of(audit_to, month) + 1))
    labels |= set(stored)

    out: list[PeriodCoverage] = []
    for label in sorted(labels):
        row = stored.get(label)
        if row is not None and row.period_from is not None and row.period_to is not None:
            period_from, period_to = row.period_from, row.period_to
        else:
            period_from, period_to = fiscal_bounds(label, month)
        status = classify_period(window, period_from, period_to)
        if status == "outside":
            continue
        runs = session.execute(
            select(CheckRun.skip_reason, func.count())
            .where(CheckRun.company_id == company.id, CheckRun.period_year == label)
            .group_by(CheckRun.skip_reason)
        ).all()
        checks_run = sum(n for reason, n in runs if reason is None)
        checks_waiting = sum(n for reason, n in runs if reason is not None)
        out.append(PeriodCoverage(
            period_year=label,
            period_from=period_from,
            period_to=period_to,
            status=status,
            has_bcqt=_has_bcqt(session, company.id, label),
            checks_run=checks_run,
            checks_waiting=checks_waiting,
        ))
    return out


def _has_bcqt(session, company_id: int, year: int) -> bool:
    """Kỳ đã có ít nhất một mẫu BCQT (M15 / M15a / M16)."""
    for model in (NvlBalance, SpBalance, Norm):
        if session.scalar(
            select(func.count())
            .select_from(model)
            .where(model.company_id == company_id, model.period_year == year)
            .limit(1)
        ):
            return True
    return False


def finding_scope_tag(
    window: tuple[date, date],
    date_span: tuple[date, date] | None,
    period_status: str,
) -> str | None:
    """Nhãn hiển thị của một phát hiện so với cửa sổ kiểm tra.

    - `outside` — mọi dòng nguồn của phát hiện đều ngoài 5 năm (hết thời hiệu).
    - `partial` — dòng nguồn nằm cả trong lẫn ngoài.
    - `period_wider` — phát hiện KHÔNG neo được vào ngày (đẳng thức cân đối tính trên
      trọn kỳ) mà kỳ lại rộng hơn phạm vi.
    - None — nằm gọn trong phạm vi.
    """
    audit_from, audit_to = window
    if date_span is None:
        return "period_wider" if period_status in ("cut_start", "cut_end", "cut_both") else None
    span_from, span_to = date_span
    if span_to < audit_from or span_from > audit_to:
        return "outside"
    if span_from < audit_from or span_to > audit_to:
        return "partial"
    return None


def declaration_spans(
    session, company_id: int, year: int, subject_keys: list[str]
) -> dict[str, tuple[date, date]]:
    """`{mã hàng: (ngày sớm nhất, ngày muộn nhất)}` của các dòng tờ khai THUỘC kỳ.

    Chỉ hỏi đúng các mã đang render — phát hiện chỉ neo được vào ngày qua dòng tờ
    khai của chính mã đó; phát hiện thuần cân đối không có mã nào khớp và giữ
    `date_span = None`.
    """
    if not subject_keys:
        return {}
    rows = session.execute(
        select(
            DeclarationLine.item_code,
            func.min(DeclarationLine.declaration_date),
            func.max(DeclarationLine.declaration_date),
        )
        .where(
            declaration_scope(session, company_id, year),
            DeclarationLine.item_code.in_(subject_keys),
            DeclarationLine.declaration_date.is_not(None),
        )
        .group_by(DeclarationLine.item_code)
    ).all()
    return {code: (lo, hi) for code, lo, hi in rows if lo is not None and hi is not None}


__all__ = [
    "AUDIT_YEARS",
    "STATUS_LABEL_VI",
    "PeriodCoverage",
    "audit_window",
    "classify_period",
    "declaration_spans",
    "finding_scope_tag",
    "label_year_of",
    "scope_coverage",
]
