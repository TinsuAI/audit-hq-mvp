"""Điểm rủi ro dữ liệu BCQT — rate-based theo §2.6 đề án + research TT 81/2019.

**LEGACY (linear sum)** — giữ cho backward compat: `score_finding`, `compute_risk_score`,
`SEVERITY_POINTS`, `COMBO_BONUS`. Vẫn dùng được nhưng KHÔNG nên dùng cho ranking
mới vì bị volume bias (DN nhiều mã → cao điểm tự động).

**RATE-BASED (khuyến nghị)** — `compute_rule_score`, `compute_company_year_score`,
`tier_for`. Mỗi rule contribute tối đa `MAX_RULE_SCORE` điểm dựa trên tỷ lệ
finding/denominator. Loại volume bias, output score 0-1000.

**Cảnh báo pháp lý**: 5 hạng (`TIERS`) là chỉ số rủi ro dữ liệu, KHÔNG phải đánh giá
tuân thủ pháp luật theo TT 81/2019/TT-BTC. Xem `.ai/legal/thong-tu-81-2019-tt-btc.md`.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from app.checks.registry import Severity
from app.models import Finding

# --- Severity weights (dùng chung cho cả legacy lẫn rate-based) ---

SEVERITY_POINTS: dict[str, int] = {
    Severity.CRITICAL.value: 10,
    Severity.WARNING.value: 3,
    Severity.INFO.value: 1,
}

COMBO_BONUS = 20

# Mỗi rule contribute tối đa MAX_RULE_SCORE điểm trong rate-based scoring.
MAX_RULE_SCORE = 10.0

# 5 hạng neutral cho score 0-1000. CẬN TRÊN (inclusive) → label.
# KHÔNG dùng tên "Mức N" để tránh nhầm với TT 81/2019.
# `TIERS` chỉ là default cho code path legacy / tests. Runtime nên dùng
# `app.app_settings.get_tiers()` để đọc ngưỡng admin có thể chỉnh ở
# /admin/risk-tiers — cùng nhãn, ngưỡng cận trên có thể khác.
TIERS: tuple[tuple[int, str, str], ...] = (
    (50,   "Dữ liệu nhất quán",        "tier-green"),
    (100,  "Có chênh lệch nhỏ",        "tier-yellow-green"),
    (300,  "Cần rà soát",              "tier-yellow"),
    (600,  "Có dấu hiệu bất thường",   "tier-orange"),
    (1000, "Bất thường nghiêm trọng",  "tier-red"),
)


def _active_tiers() -> tuple[tuple[int, str, str], ...]:
    """Đọc tiers runtime; fallback default nếu thiếu DB context."""
    try:
        from app.app_settings import get_tiers
        return get_tiers()
    except Exception:
        return TIERS


# --- Legacy linear-sum (giữ nguyên cho backward compat) ---


def score_finding(finding: Finding) -> int:
    """Điểm 1 finding theo severity. Combo tính COMBO_BONUS bất kể severity."""
    if finding.check_code.startswith("COMBO_"):
        return COMBO_BONUS
    return SEVERITY_POINTS.get(finding.severity, 0)


def compute_risk_score(findings: Iterable[Finding]) -> int:
    """LEGACY: tổng điểm tuyến tính cho 1 (DN, năm). Bị volume bias.

    Vẫn dùng được cho callers cũ; ranking mới nên dùng `compute_company_year_score`.
    """
    total = 0
    for f in findings:
        if f.status == "rejected":
            continue
        total += score_finding(f)
    return total


# --- Rate-based scoring ---


def compute_rule_score(findings: Iterable[Finding], denominator: int) -> float:
    """Score 0..MAX_RULE_SCORE cho 1 rule trên 1 (DN, năm).

    Formula:
        points       = Σ severity_weight cho findings không rejected, không combo
        max_points   = MAX_SEVERITY_WEIGHT × denominator  (= 10 × denom)
        rate         = min(1, points / max_points)
        rule_score   = rate × MAX_RULE_SCORE

    Denominator = 0 → score = 0 (không có exposure để so).
    """
    if denominator <= 0:
        return 0.0
    points = 0
    for f in findings:
        if f.status == "rejected":
            continue
        if f.check_code.startswith("COMBO_"):
            continue  # combo xử lý riêng ở compute_company_year_score
        points += SEVERITY_POINTS.get(f.severity, 0)
    max_points = SEVERITY_POINTS[Severity.CRITICAL.value] * denominator  # 10 × denom
    rate = min(1.0, points / max_points) if max_points > 0 else 0.0
    return rate * MAX_RULE_SCORE


def tier_for(score: int) -> str:
    """Map score 0-1000 → 1 trong 5 nhãn neutral (ngưỡng từ app_settings)."""
    tiers = _active_tiers()
    for upper, label, _css in tiers:
        if score <= upper:
            return label
    return tiers[-1][1]


def tier_css_for(score: int) -> str:
    """CSS class cho hạng (vd tier-green, tier-red) — ngưỡng từ app_settings."""
    tiers = _active_tiers()
    for upper, _label, css in tiers:
        if score <= upper:
            return css
    return tiers[-1][2]


def compute_company_year_score(
    findings: Iterable[Finding],
    denominators: dict[str, int],
) -> dict:
    """Score 0-1000 + tier + breakdown chi tiết cho 1 (DN, năm).

    Args:
        findings: tất cả Finding của (DN, năm), bao gồm cả COMBO_*.
        denominators: dict {nvl, tp, m16} từ `compute_denominators`.

    Returns:
        {
          score: int 0-1000,
          tier: str (1 trong 5 nhãn),
          rule_scores: dict[check_code → float 0..10],
          combo_bonus: int (0 hoặc 20),
          raw: float (tổng điểm thô trước khi rescale),
          max_raw: float (trần lý thuyết — để debug),
          denominators: dict (lưu lại để audit trail),
        }
    """
    from app.checks.denominators import RULE_SCOPE

    findings_list = list(findings)

    # Group findings theo check_code, bỏ combo.
    by_rule: dict[str, list[Finding]] = defaultdict(list)
    has_combo = False
    for f in findings_list:
        if f.check_code.startswith("COMBO_"):
            if f.status != "rejected":
                has_combo = True
            continue
        by_rule[f.check_code].append(f)

    rule_scores: dict[str, float] = {}
    for code, fs in by_rule.items():
        scope = RULE_SCOPE.get(code, "nvl")
        denom = denominators.get(scope, 0)
        score = compute_rule_score(fs, denom)
        if score > 0:
            rule_scores[code] = round(score, 3)

    combo_bonus = COMBO_BONUS if has_combo else 0
    raw = sum(rule_scores.values()) + combo_bonus

    # Trần lý thuyết: mọi rule trong RULE_SCOPE đều fire max + 1 combo.
    max_raw = len(RULE_SCOPE) * MAX_RULE_SCORE + COMBO_BONUS

    score = round(1000 * raw / max_raw) if max_raw > 0 else 0
    score = max(0, min(1000, score))

    return {
        "score": score,
        "tier": tier_for(score),
        "rule_scores": rule_scores,
        "combo_bonus": combo_bonus,
        "raw": round(raw, 3),
        "max_raw": max_raw,
        "denominators": dict(denominators),
    }


__all__ = [
    "COMBO_BONUS",
    "MAX_RULE_SCORE",
    "SEVERITY_POINTS",
    "TIERS",
    "compute_company_year_score",
    "compute_risk_score",  # legacy
    "compute_rule_score",
    "score_finding",  # legacy
    "tier_css_for",
    "tier_for",
]
