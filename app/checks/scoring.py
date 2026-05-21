"""Cộng dồn điểm rủi ro doanh nghiệp (§2.6 đề án).

Quy tắc điểm:
    🔴 Nghiêm trọng : 10 điểm
    🟡 Cảnh báo     :  3 điểm
    🔵 Thông tin    :  1 điểm
    Mỗi combination signature phát hiện được: +20 điểm bonus.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.checks.registry import Severity
from app.models import Finding

SEVERITY_POINTS: dict[str, int] = {
    Severity.CRITICAL.value: 10,
    Severity.WARNING.value: 3,
    Severity.INFO.value: 1,
}

COMBO_BONUS = 20


def score_finding(finding: Finding) -> int:
    """Điểm 1 finding theo severity. Combo (check_code prefix COMBO_) tính COMBO_BONUS."""
    if finding.check_code.startswith("COMBO_"):
        return COMBO_BONUS
    return SEVERITY_POINTS.get(finding.severity, 0)


def compute_risk_score(findings: Iterable[Finding]) -> int:
    """Tổng điểm cho 1 (company, year).

    Findings đã loại 'rejected' nếu cán bộ đánh dấu là loại trừ (status=rejected).
    """
    total = 0
    for f in findings:
        if f.status == "rejected":
            continue
        total += score_finding(f)
    return total
