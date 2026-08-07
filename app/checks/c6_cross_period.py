"""Nhóm 6 — Kiểm tra liên kỳ (§4.1 đề án).

MVP tuần 5: C6.1 (tồn đầu kỳ N ≠ tồn cuối kỳ N-1, NVL).
C6.2-C6.5 là W.I.P.
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
from app.models import Finding, NvlBalance

_TOLERANCE = 0.01


def classify_missing_prev_period(prev_year: int) -> RemedyClassification:
    """(lớp, đích) khi thiếu Mẫu 15 kỳ N−1 — lớp 2, đích là chính kỳ N−1 (ADR #24).

    File của kỳ đang xét không gỡ được: thứ thiếu là dữ liệu của một kỳ khác.
    """
    return REMEDY_NEED_OTHER_PERIOD_OR_CONFIRMATION, RemedyTarget(TARGET_PERIOD, prev_year)


def check_c6_1(session: Session, company_id: int, year: int) -> CheckResult:
    """Tồn đầu kỳ N (M15) khác tồn cuối kỳ N-1 (M15) — từng mã NVL.

    Chưa có M15 kỳ N-1 thì trả `NotEvaluable`, KHÔNG trả danh sách rỗng: rỗng ở đây
    đọc như "mọi mã khớp" trong khi chưa so mã nào. `registry.requires` chỉ gác nguồn
    của kỳ ĐANG xét (issue #53) nên không bắt được ca thiếu kỳ N-1 — cùng lớp lỗi
    "sạch giả", khác trục.
    """
    prev_year = year - 1
    prev_rows = session.scalars(
        select(NvlBalance).where(
            NvlBalance.company_id == company_id,
            NvlBalance.period_year == prev_year,
        )
    ).all()
    if not prev_rows:
        remedy, _ = classify_missing_prev_period(prev_year)
        return NotEvaluable(
            f"Chưa có Mẫu 15 của kỳ {prev_year} — không có tồn cuối kỳ trước để "
            f"đối chiếu với tồn đầu kỳ {year}.",
            remedy=remedy,
        )
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


CHECKS = {
    "C6.1": check_c6_1,
}
