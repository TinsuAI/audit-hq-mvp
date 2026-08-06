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


def score_coverage(breakdown: dict | None) -> tuple[int, int]:
    """(số luật đã đánh giá, tổng số luật) từ `breakdown` đã lưu.

    Điểm là một TRUNG BÌNH trên các luật CHẤM ĐƯỢC, nên bỏ một luật `not_evaluable`
    kéo điểm về trung bình các luật còn lại — điểm có thể GIẢM dù mình biết ÍT hơn
    (đo trên pilot 06/08/2026: DN 10/2025 3→1). Vì vậy con số điểm không bao giờ
    được đứng một mình: mọi chỗ hiện điểm phải hiện kèm độ phủ này, và xếp hạng
    chéo doanh nghiệp phải tách nhóm chưa đủ độ phủ ra khỏi nhóm đã đánh giá trọn.
    Xem `tests/test_checks/test_norm_gate.py::test_gate_does_not_lower_the_risk_score`.

    Trả `(0, 0)` khi chưa có breakdown — chưa chạy kiểm tra thì chưa nói được gì.
    """
    if not breakdown:
        return 0, 0
    total = breakdown.get("rule_count")
    if total is None:
        # Breakdown cũ (trước khi có `rule_count`): suy ngược từ trần đã lưu.
        max_raw = breakdown.get("max_raw") or 0
        total = int(round((max_raw - COMBO_BONUS) / MAX_RULE_SCORE)) if max_raw else 0
        total += len(breakdown.get("not_evaluable") or ())
    return max(0, total - len(breakdown.get("not_evaluable") or ())), total


def compute_company_year_score(
    findings: Iterable[Finding],
    denominators: dict[str, int],
    rule_scope: dict[str, str] | None = None,
    not_evaluable: Iterable[str] | None = None,
) -> dict:
    """Score 0-1000 + tier + breakdown chi tiết cho 1 (DN, năm).

    Args:
        findings: tất cả Finding của (DN, năm), bao gồm cả COMBO_*.
        denominators: dict {nvl, tp, m16} từ `compute_denominators`.
        rule_scope: map check_code → scope. Mặc định = built-in RULE_SCOPE.
            Truyền map MỞ RỘNG (built-in + check mở rộng đã publish) để cả mẫu số
            lẫn trần `max_raw` tính cả check tự do — nếu không, check X.* đẩy `raw`
            lên mà `max_raw` cố định → lệch trần.
        not_evaluable: mã các check KHÔNG kết luận được kỳ này
            (`app.checks.not_evaluable.load_not_evaluable`). Mỗi mã bị gỡ khỏi CẢ
            `rule_scores` LẪN `max_raw`: chỉ gỡ phần cộng điểm mà vẫn tính vào trần
            thì thiếu dữ liệu lại làm điểm đẹp lên (`.ai/GLOSSARY.md`). Kết quả
            bằng đúng lần chạy không có mã đó trong `rule_scope`.

    Returns:
        {
          score: int 0-1000,
          tier: str (1 trong 5 nhãn),
          rule_scores: dict[check_code → float 0..10],
          combo_bonus: int (0 hoặc 20),
          raw: float (tổng điểm thô trước khi rescale),
          max_raw: float (trần lý thuyết — để debug),
          denominators: dict (lưu lại để audit trail),
          not_evaluable: list[str] (mã đã loại khỏi cả hai vế),
        }
    """
    from app.checks.denominators import RULE_SCOPE

    if rule_scope is None:
        rule_scope = RULE_SCOPE

    skipped = {c for c in (not_evaluable or ()) if c}
    if skipped:
        rule_scope = {c: sc for c, sc in rule_scope.items() if c not in skipped}

    findings_list = list(findings)

    # Group findings theo check_code, bỏ combo.
    by_rule: dict[str, list[Finding]] = defaultdict(list)
    has_combo = False
    for f in findings_list:
        if f.check_code.startswith("COMBO_"):
            if f.status != "rejected":
                has_combo = True
            continue
        if f.check_code in skipped:
            continue  # phát hiện cũ còn sót của mã không kết luận được — không tính
        by_rule[f.check_code].append(f)

    rule_scores: dict[str, float] = {}
    for code, fs in by_rule.items():
        scope = rule_scope.get(code, "nvl")
        denom = denominators.get(scope, 0)
        score = compute_rule_score(fs, denom)
        if score > 0:
            rule_scores[code] = round(score, 3)

    combo_bonus = COMBO_BONUS if has_combo else 0
    raw = sum(rule_scores.values()) + combo_bonus

    # Trần lý thuyết: mọi rule trong rule_scope đều fire max + 1 combo. Rule
    # `not_evaluable` đã bị gỡ khỏi `rule_scope` ở trên nên không nằm trong trần.
    max_raw = len(rule_scope) * MAX_RULE_SCORE + COMBO_BONUS

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
        "not_evaluable": sorted(skipped),
        # Tổng số luật của kỳ KỂ CẢ luật bị loại — `max_raw` chỉ còn phần chấm được,
        # nên không suy ngược ra mẫu số độ phủ được nếu không lưu riêng.
        "rule_count": len(rule_scope) + len(skipped),
    }


__all__ = [
    "COMBO_BONUS",
    "MAX_RULE_SCORE",
    "SEVERITY_POINTS",
    "TIERS",
    "compute_company_year_score",
    "compute_risk_score",  # legacy
    "compute_rule_score",
    "score_coverage",
    "score_finding",  # legacy
    "tier_css_for",
    "tier_for",
]
