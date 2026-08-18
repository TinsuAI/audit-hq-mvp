"""Nhóm 6 — Kiểm tra liên kỳ (§4.1 đề án).

C6.1 (NVL, Mẫu 15) và C6.2 (thành phẩm, Mẫu 15a) là CÙNG một phép đối chiếu trên hai
biểu: tồn đầu kỳ N phải bằng tồn cuối kỳ N-1, theo từng mã và trong từng sổ quyết toán.
Hai biểu nạp rời nhau nên mỗi check có cổng kỳ trước của RIÊNG nó — có Mẫu 15 kỳ trước
không nói được gì về việc có Mẫu 15a kỳ trước hay không.

C6.3-C6.5 là W.I.P.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.checks.not_evaluable import (
    REMEDY_NEED_OTHER_PERIOD_OR_CONFIRMATION,
    TARGET_PERIOD,
    CheckResult,
    NotEvaluable,
    RemedyClassification,
    RemedyTarget,
)
from app.checks.registry import Severity
from app.models import Finding, NvlBalance, SpBalance

_TOLERANCE = 0.01


def classify_missing_prev_period(prev_year: int) -> RemedyClassification:
    """(lớp, đích) khi thiếu biểu cân đối của kỳ N−1 — lớp 2, đích là chính kỳ N−1 (ADR #24).

    File của kỳ đang xét không gỡ được: thứ thiếu là dữ liệu của một kỳ khác.
    """
    return REMEDY_NEED_OTHER_PERIOD_OR_CONFIRMATION, RemedyTarget(TARGET_PERIOD, prev_year)


def _previous_period_gate(
    session: Session, company_id: int, year: int, model: type, form: str
) -> tuple[str, RemedyClassification] | None:
    """(lý do, (lớp, đích)) khi chưa có biểu `form` của kỳ N−1; None nếu có.

    Hỏi "có dòng nào không" bằng `LIMIT 1` — cổng chỉ cần biết có hay không, còn check
    mới đọc trọn dòng để đối chiếu. Màn dữ liệu gọi CHÍNH hàm này, nên dự đoán của nó
    không thể lệch với trạng thái check ghi.
    """
    prev_year = year - 1
    if session.scalar(
        select(model.id)
        .where(model.company_id == company_id, model.period_year == prev_year)
        .limit(1)
    ):
        return None
    reason = (
        f"Chưa có {form} của kỳ {prev_year} — không có tồn cuối kỳ trước để "
        f"đối chiếu với tồn đầu kỳ {year}."
    )
    return reason, classify_missing_prev_period(prev_year)


def previous_period_gate(
    session: Session, company_id: int, year: int
) -> tuple[str, RemedyClassification] | None:
    """Cổng kỳ trước của C6.1 — Mẫu 15."""
    return _previous_period_gate(session, company_id, year, NvlBalance, "Mẫu 15")


def previous_period_sp_gate(
    session: Session, company_id: int, year: int
) -> tuple[str, RemedyClassification] | None:
    """Cổng kỳ trước của C6.2 — Mẫu 15a.

    Tách khỏi cổng Mẫu 15 chứ không dùng chung: hai biểu nạp rời nhau, doanh nghiệp
    nộp Mẫu 15 kỳ N−1 mà chưa nộp Mẫu 15a kỳ N−1 là ca có thật. Dùng chung cổng thì
    C6.2 chạy trên tập rỗng và trả 0 phát hiện, đọc như "mọi thành phẩm khớp".
    """
    return _previous_period_gate(session, company_id, year, SpBalance, "Mẫu 15a")


def check_c6_1(session: Session, company_id: int, year: int) -> CheckResult:
    """Tồn đầu kỳ N (M15) khác tồn cuối kỳ N-1 (M15) — từng mã NVL.

    Chưa có M15 kỳ N-1 thì trả `NotEvaluable`, KHÔNG trả danh sách rỗng: rỗng ở đây
    đọc như "mọi mã khớp" trong khi chưa so mã nào. `registry.requires` chỉ gác nguồn
    của kỳ ĐANG xét (issue #53) nên không bắt được ca thiếu kỳ N-1 — cùng lớp lỗi
    "sạch giả", khác trục.
    """
    prev_year = year - 1
    gated = previous_period_gate(session, company_id, year)
    if gated is not None:
        reason, (remedy, _target) = gated
        return NotEvaluable(reason, remedy=remedy)

    prev_rows = session.scalars(
        select(NvlBalance).where(
            NvlBalance.company_id == company_id,
            NvlBalance.period_year == prev_year,
        )
    ).all()
    # Khoá theo (SỔ, mã): mỗi sổ quyết toán là ledger tồn kho riêng — tồn cuối kỳ N-1
    # của một sổ chỉ so với tồn đầu kỳ N CÙNG SỔ (xem ADR #19). book=None (một sổ) là
    # một nhóm → hành vi cũ không đổi.
    prev_closing = {(r.book, r.material_code): (r.closing_qty or 0.0) for r in prev_rows}

    curr_rows = session.scalars(
        select(NvlBalance).where(
            NvlBalance.company_id == company_id,
            NvlBalance.period_year == year,
        )
    ).all()

    def _nvl_filter(period: int, code: str, book: str | None) -> dict:
        f = {"company_id": company_id, "period_year": period, "material_code": code}
        if book is not None:
            f["book"] = book
        return f

    findings: list[Finding] = []
    for r in curr_rows:
        curr_opening = r.opening_qty or 0.0
        key = (r.book, r.material_code)
        if key not in prev_closing:
            # NVL mới xuất hiện kỳ N: nếu opening > 0 nhưng kỳ N-1 không có →
            # lệch (kỳ trước phải có tồn cuối tương ứng).
            if abs(curr_opening) > _TOLERANCE:
                findings.append(Finding(
                    company_id=company_id,
                    period_year=year,
                    check_code="C6.1",
                    severity=Severity.CRITICAL.value,
                    subject_type="material_code",
                    subject_key=r.material_code,
                    book=r.book,
                    title=(
                        f"NVL {r.material_code} có tồn đầu kỳ {year} = {curr_opening:.2f} "
                        f"nhưng kỳ {prev_year} không có dòng tương ứng"
                    ),
                    details={
                        "current_opening": curr_opening,
                        "previous_closing": None,
                    },
                    evidence_refs=[{
                        "table": "nvl_balances",
                        "filter": _nvl_filter(year, r.material_code, r.book),
                    }],
                ))
            continue

        prev = prev_closing[key]
        diff = curr_opening - prev
        if abs(diff) <= _TOLERANCE:
            continue
        findings.append(Finding(
            company_id=company_id,
            period_year=year,
            check_code="C6.1",
            severity=Severity.CRITICAL.value,
            subject_type="material_code",
            subject_key=r.material_code,
            book=r.book,
            title=(
                f"NVL {r.material_code} tồn đầu {year}={curr_opening:.2f} "
                f"khác tồn cuối {prev_year}={prev:.2f} (chênh {diff:+.2f})"
            ),
            details={
                "current_opening": curr_opening,
                "previous_closing": prev,
                "diff": diff,
            },
            evidence_refs=[
                {"table": "nvl_balances", "filter": _nvl_filter(year, r.material_code, r.book)},
                {"table": "nvl_balances", "filter": _nvl_filter(prev_year, r.material_code, r.book)},
            ],
        ))
    return findings


def check_c6_2(session: Session, company_id: int, year: int) -> CheckResult:
    """Tồn đầu kỳ N (M15a) khác tồn cuối kỳ N-1 (M15a) — từng mã thành phẩm.

    Cùng phép đối chiếu với C6.1, khác biểu và khác chủ thể: `sp_balances` thay cho
    `nvl_balances`, `product_code` thay cho `material_code`. Chưa có Mẫu 15a kỳ N-1 thì
    trả `NotEvaluable` chứ KHÔNG trả danh sách rỗng — rỗng ở đây đọc như "mọi mã khớp"
    trong khi chưa so mã nào.
    """
    prev_year = year - 1
    gated = previous_period_sp_gate(session, company_id, year)
    if gated is not None:
        reason, (remedy, _target) = gated
        return NotEvaluable(reason, remedy=remedy)

    prev_rows = session.scalars(
        select(SpBalance).where(
            SpBalance.company_id == company_id,
            SpBalance.period_year == prev_year,
        )
    ).all()
    # Khoá theo (SỔ, mã) như C6.1: mỗi sổ quyết toán là ledger tồn kho riêng (ADR #19).
    prev_closing = {(r.book, r.product_code): (r.closing_qty or 0.0) for r in prev_rows}

    curr_rows = session.scalars(
        select(SpBalance).where(
            SpBalance.company_id == company_id,
            SpBalance.period_year == year,
        )
    ).all()

    def _sp_filter(period: int, code: str, book: str | None) -> dict:
        f = {"company_id": company_id, "period_year": period, "product_code": code}
        if book is not None:
            f["book"] = book
        return f

    findings: list[Finding] = []
    for r in curr_rows:
        curr_opening = r.opening_qty or 0.0
        key = (r.book, r.product_code)
        if key not in prev_closing:
            # TP mới xuất hiện kỳ N: opening > 0 mà kỳ N-1 không có dòng → lệch.
            if abs(curr_opening) > _TOLERANCE:
                findings.append(Finding(
                    company_id=company_id,
                    period_year=year,
                    check_code="C6.2",
                    severity=Severity.CRITICAL.value,
                    subject_type="product_code",
                    subject_key=r.product_code,
                    book=r.book,
                    title=(
                        f"Thành phẩm {r.product_code} có tồn đầu kỳ {year} = "
                        f"{curr_opening:.2f} nhưng kỳ {prev_year} không có dòng tương ứng"
                    ),
                    details={
                        "current_opening": curr_opening,
                        "previous_closing": None,
                    },
                    evidence_refs=[{
                        "table": "sp_balances",
                        "filter": _sp_filter(year, r.product_code, r.book),
                    }],
                ))
            continue

        prev = prev_closing[key]
        diff = curr_opening - prev
        if abs(diff) <= _TOLERANCE:
            continue
        findings.append(Finding(
            company_id=company_id,
            period_year=year,
            check_code="C6.2",
            severity=Severity.CRITICAL.value,
            subject_type="product_code",
            subject_key=r.product_code,
            book=r.book,
            title=(
                f"Thành phẩm {r.product_code} tồn đầu {year}={curr_opening:.2f} "
                f"khác tồn cuối {prev_year}={prev:.2f} (chênh {diff:+.2f})"
            ),
            details={
                "current_opening": curr_opening,
                "previous_closing": prev,
                "diff": diff,
            },
            evidence_refs=[
                {"table": "sp_balances", "filter": _sp_filter(year, r.product_code, r.book)},
                {"table": "sp_balances", "filter": _sp_filter(prev_year, r.product_code, r.book)},
            ],
        ))
    return findings


CHECKS = {
    "C6.1": check_c6_1,
    "C6.2": check_c6_2,
}

__all__ = [
    "CHECKS",
    "check_c6_1",
    "check_c6_2",
    "classify_missing_prev_period",
    "previous_period_gate",
    "previous_period_sp_gate",
]
