"""Tests cho scoring (§2.6) + combination signatures (§2.7)."""

from __future__ import annotations

from app.checks.combos import detect_combos
from app.checks.scoring import COMBO_BONUS, SEVERITY_POINTS, compute_risk_score, score_finding
from app.models import Finding


def make_finding(check_code: str, severity: str, subject_key: str = "X", status: str = "new") -> Finding:
    return Finding(
        company_id=1, period_year=2024,
        check_code=check_code, severity=severity,
        subject_type="material_code", subject_key=subject_key, status=status,
        title="x",
    )


def test_severity_points_constants():
    assert SEVERITY_POINTS["critical"] == 10
    assert SEVERITY_POINTS["warning"] == 3
    assert SEVERITY_POINTS["info"] == 1
    assert COMBO_BONUS == 20


def test_score_finding_per_severity():
    assert score_finding(make_finding("C1.1", "critical")) == 10
    assert score_finding(make_finding("C1.1", "warning")) == 3
    assert score_finding(make_finding("C1.1", "info")) == 1


def test_score_finding_combo_uses_bonus_regardless_of_severity():
    # Combo dù gắn severity warning vẫn tính COMBO_BONUS.
    assert score_finding(make_finding("COMBO_HS_GAMING", "warning")) == COMBO_BONUS
    assert score_finding(make_finding("COMBO_FORGED_NORM", "critical")) == COMBO_BONUS


def test_compute_risk_score_sums_active_findings():
    findings = [
        make_finding("C1.1", "critical"),  # 10
        make_finding("C2.1", "warning"),   # 3
        make_finding("C3.2", "info"),      # 1
        make_finding("COMBO_X", "critical"),  # 20
    ]
    assert compute_risk_score(findings) == 34


def test_compute_risk_score_ignores_rejected():
    findings = [
        make_finding("C1.1", "critical"),                              # 10
        make_finding("C2.1", "warning", status="rejected"),            # skip
        make_finding("C3.2", "info", status="confirmed"),              # 1
    ]
    assert compute_risk_score(findings) == 11


# --- Combos ---


def test_detect_combos_forged_norm_when_c23_and_c43_same_material(session, company):
    findings = [
        make_finding("C2.3", "critical", subject_key="A"),
        make_finding("C4.3", "critical", subject_key="A"),
    ]
    for f in findings:
        f.company_id = company.id
        session.add(f)
    session.flush()
    combos = detect_combos(session, company.id, 2024, findings)
    codes = {c.check_code for c in combos}
    assert "COMBO_FORGED_NORM" in codes
    fn = next(c for c in combos if c.check_code == "COMBO_FORGED_NORM")
    assert fn.subject_key == "A"
    assert fn.severity == "critical"


def test_detect_combos_no_fire_when_different_subjects(session, company):
    findings = [
        make_finding("C2.3", "critical", subject_key="A"),
        make_finding("C4.3", "critical", subject_key="B"),
    ]
    for f in findings:
        f.company_id = company.id
        session.add(f)
    session.flush()
    combos = detect_combos(session, company.id, 2024, findings)
    assert combos == []


def test_detect_combos_undeclared_source(session, company):
    findings = [
        make_finding("C1.3", "critical", subject_key="X"),
        make_finding("C5.1", "critical", subject_key="X"),
    ]
    for f in findings:
        f.company_id = company.id
        session.add(f)
    session.flush()
    combos = detect_combos(session, company.id, 2024, findings)
    assert any(c.check_code == "COMBO_UNDECLARED_SOURCE" for c in combos)


def test_detect_combos_hs_gaming(session, company):
    findings = [
        make_finding("C3.2", "warning", subject_key="DUAL"),
        make_finding("C3.3", "critical", subject_key="DUAL"),
    ]
    for f in findings:
        f.company_id = company.id
        session.add(f)
    session.flush()
    combos = detect_combos(session, company.id, 2024, findings)
    assert any(c.check_code == "COMBO_HS_GAMING" for c in combos)


def test_detect_combos_skips_existing_combo_findings(session, company):
    # Một combo "đã có sẵn" trong list không được dùng làm trigger cho combo khác.
    findings = [
        make_finding("COMBO_FORGED_NORM", "critical", subject_key="A"),
        make_finding("C2.3", "critical", subject_key="A"),
    ]
    for f in findings:
        f.company_id = company.id
        session.add(f)
    session.flush()
    combos = detect_combos(session, company.id, 2024, findings)
    # COMBO_FORGED_NORM cần C2.3 + C4.3 — chỉ có C2.3, không fire.
    assert combos == []
