"""Test rate-based scoring + 5 hạng neutral."""

from __future__ import annotations

import pytest

from app.checks.scoring import (
    MAX_RULE_SCORE,
    TIERS,
    compute_company_year_score,
    compute_rule_score,
    tier_for,
)
from app.models import Finding


def _f(check_code: str, severity: str, subject_key: str = "X", status: str = "new") -> Finding:
    return Finding(
        company_id=1, period_year=2024,
        check_code=check_code, severity=severity,
        subject_type="material_code", subject_key=subject_key, status=status,
        title="x",
    )


# --- compute_rule_score ---

def test_rule_score_empty_findings_is_zero() -> None:
    assert compute_rule_score([], denominator=100) == 0.0


def test_rule_score_zero_denominator_is_zero() -> None:
    # Không có exposure → không score được (avoid divide-by-zero + bias).
    assert compute_rule_score([_f("C1.1", "critical")], denominator=0) == 0.0


def test_rule_score_all_critical_at_full_coverage_hits_ceiling() -> None:
    # 10 findings critical, denom=10 → rate=1.0 → score = MAX_RULE_SCORE (10).
    findings = [_f("C1.1", "critical", subject_key=str(i)) for i in range(10)]
    assert compute_rule_score(findings, denominator=10) == MAX_RULE_SCORE


def test_rule_score_caps_at_ceiling_even_when_findings_exceed_denominator() -> None:
    # Edge case: findings > denominator → rate clamp to 1.0.
    findings = [_f("C1.1", "critical", subject_key=str(i)) for i in range(50)]
    assert compute_rule_score(findings, denominator=10) == MAX_RULE_SCORE


def test_rule_score_partial_critical() -> None:
    # 3 critical / 10 denom = 30 points (3*10) / 100 max points = 0.3 rate.
    # rate × MAX_RULE_SCORE = 3.0.
    findings = [_f("C1.1", "critical", subject_key=str(i)) for i in range(3)]
    assert compute_rule_score(findings, denominator=10) == pytest.approx(3.0)


def test_rule_score_warning_weight_lower_than_critical() -> None:
    # 1 warning / 10 denom = 3 points / 100 max = 0.03 → 0.3.
    findings = [_f("C1.1", "warning")]
    assert compute_rule_score(findings, denominator=10) == pytest.approx(0.3)


def test_rule_score_ignores_rejected_findings() -> None:
    findings = [
        _f("C1.1", "critical", status="rejected"),
        _f("C1.1", "warning"),
    ]
    # Chỉ warning được tính: 3 / 100 × 10 = 0.3.
    assert compute_rule_score(findings, denominator=10) == pytest.approx(0.3)


# --- tier_for ---

def test_tier_boundaries() -> None:
    # Ngưỡng mặc định: 50, 100, 300, 600, 1000 (configurable ở /admin/risk-tiers).
    assert tier_for(0) == "Dữ liệu nhất quán"
    assert tier_for(50) == "Dữ liệu nhất quán"
    assert tier_for(51) == "Có chênh lệch nhỏ"
    assert tier_for(100) == "Có chênh lệch nhỏ"
    assert tier_for(101) == "Cần rà soát"
    assert tier_for(300) == "Cần rà soát"
    assert tier_for(301) == "Có dấu hiệu bất thường"
    assert tier_for(600) == "Có dấu hiệu bất thường"
    assert tier_for(601) == "Bất thường nghiêm trọng"
    assert tier_for(1000) == "Bất thường nghiêm trọng"


def test_tier_list_has_5_entries() -> None:
    assert len(TIERS) == 5


# --- compute_company_year_score ---

def test_score_no_findings_is_zero() -> None:
    result = compute_company_year_score([], denominators={"nvl": 100, "tp": 50, "m16": 30})
    assert result["score"] == 0
    assert result["tier"] == "Dữ liệu nhất quán"
    assert result["raw"] == 0.0
    assert result["rule_scores"] == {}


def test_score_combo_bonus_one_shot() -> None:
    # 1 combo + 0 rule findings → raw = COMBO_BONUS (20).
    # max_raw = 17 × MAX_RULE_SCORE + 20 = 190.
    # score = round(1000 × 20 / 190) = 105.
    findings = [_f("COMBO_FORGED_NORM", "critical")]
    result = compute_company_year_score(findings, denominators={"nvl": 10, "tp": 10, "m16": 10})
    assert result["score"] == 105
    assert result["combo_bonus"] == 20


def test_score_combo_bonus_counted_once_even_with_multiple_combos() -> None:
    findings = [
        _f("COMBO_FORGED_NORM", "critical", subject_key="A"),
        _f("COMBO_HS_GAMING", "warning", subject_key="B"),
    ]
    result = compute_company_year_score(findings, denominators={"nvl": 10, "tp": 10, "m16": 10})
    assert result["combo_bonus"] == 20


def test_score_caps_at_1000() -> None:
    # Mọi check fire full critical → score = 1000.
    from app.checks.denominators import RULE_SCOPE
    findings = []
    for code in RULE_SCOPE:
        # Mỗi rule fire 10 finding critical, denom = 10 → max ceiling.
        findings.extend(_f(code, "critical", subject_key=f"{code}-{i}") for i in range(10))
    findings.append(_f("COMBO_X", "critical"))
    denoms = {"nvl": 10, "tp": 10, "m16": 10}
    result = compute_company_year_score(findings, denominators=denoms)
    assert result["score"] == 1000
    assert result["tier"] == "Bất thường nghiêm trọng"


def test_score_volume_invariance() -> None:
    """DN có 500 mã NVL với 50% lỗi (250 findings) ≠ DN có 50 mã với 25 findings.

    Cả 2 đều có rate=0.5 trên C2.1 → cùng rule_score → cùng tier band (cùng số
    rule fire). Volume bias đã được loại bỏ.
    """
    # DN lớn: denom=500, findings=250 critical.
    big_findings = [_f("C2.1", "critical", subject_key=str(i)) for i in range(250)]
    big = compute_company_year_score(big_findings, denominators={"nvl": 500, "tp": 100, "m16": 100})

    # DN nhỏ: denom=50, findings=25 critical (cùng tỷ lệ).
    small_findings = [_f("C2.1", "critical", subject_key=str(i)) for i in range(25)]
    small = compute_company_year_score(small_findings, denominators={"nvl": 50, "tp": 10, "m16": 10})

    # Score 2 DN sau khi bỏ volume bias phải bằng nhau (cùng rule_score C2.1).
    assert big["score"] == small["score"]
    assert big["rule_scores"]["C2.1"] == small["rule_scores"]["C2.1"]


def test_score_breakdown_includes_per_rule_score() -> None:
    findings = [_f("C1.1", "critical", subject_key="A"), _f("C1.1", "warning", subject_key="B")]
    result = compute_company_year_score(findings, denominators={"nvl": 10, "tp": 10, "m16": 10})
    assert "C1.1" in result["rule_scores"]
    # 10 + 3 = 13 points / 100 max = 0.13 rate → 1.3 rule_score.
    assert result["rule_scores"]["C1.1"] == pytest.approx(1.3)
