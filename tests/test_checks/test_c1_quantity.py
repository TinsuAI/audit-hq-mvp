"""Unit tests cho Nhóm 1 — Số lượng nhập/xuất."""

from __future__ import annotations

from app.checks.c1_quantity import (
    check_c1_1,
    check_c1_2,
    check_c1_3,
    check_c1_4,
    check_c1_6,
    check_c1_7,
)
from app.checks.company_type import CompanyType, detect_company_type
from tests.conftest import add_decl, add_nvl, add_sp


def test_detect_company_type_sxxk(session, company):
    add_decl(session, company.id, declaration_no="1", customs_code="E31", item_code="X", quantity=100)
    add_decl(session, company.id, declaration_no="2", customs_code="E62", item_code="Y", quantity=50)
    session.commit()
    assert detect_company_type(session, company.id, 2024) == CompanyType.SXXK


def test_detect_company_type_dncx(session, company):
    add_decl(session, company.id, declaration_no="1", customs_code="E11", item_code="X", quantity=100)
    add_decl(session, company.id, declaration_no="2", customs_code="E42", item_code="Y", quantity=50)
    session.commit()
    assert detect_company_type(session, company.id, 2024) == CompanyType.DNCX


# --- C1.1: Lệch số lượng nhập NVL ---


def test_c1_1_no_fire_when_match(session, company):
    add_nvl(session, company.id, material_code="A", imported=1000)
    add_decl(session, company.id, declaration_no="1", customs_code="E31", item_code="A", quantity=1000)
    session.commit()
    assert check_c1_1(session, company.id, 2024) == []


def test_c1_1_fires_info_when_diff_under_5pct(session, company):
    # Diff 4% — Thông tin (INFO band 0.5% ≤ |diff| < 5%).
    add_nvl(session, company.id, material_code="A", imported=1000)
    add_decl(session, company.id, declaration_no="1", customs_code="E31", item_code="A", quantity=960)
    session.commit()
    findings = check_c1_1(session, company.id, 2024)
    assert len(findings) == 1
    assert findings[0].severity == "info"


def test_c1_1_no_fire_when_diff_under_floor(session, company):
    # Diff 0.2% — dưới floor 0.5% (coi như khớp, lọc nhiễu).
    add_nvl(session, company.id, material_code="A", imported=1000)
    add_decl(session, company.id, declaration_no="1", customs_code="E31", item_code="A", quantity=998)
    session.commit()
    assert check_c1_1(session, company.id, 2024) == []


def test_c1_1_fires_warning_when_diff_10pct(session, company):
    add_nvl(session, company.id, material_code="A", imported=1000)
    add_decl(session, company.id, declaration_no="1", customs_code="E31", item_code="A", quantity=900)
    session.commit()
    findings = check_c1_1(session, company.id, 2024)
    assert len(findings) == 1
    assert findings[0].check_code == "C1.1"
    assert findings[0].severity == "warning"
    assert abs(findings[0].details["diff_pct"] + 10.0) < 0.01


def test_c1_1_fires_critical_when_diff_50pct(session, company):
    add_nvl(session, company.id, material_code="A", imported=1000)
    add_decl(session, company.id, declaration_no="1", customs_code="E31", item_code="A", quantity=500)
    session.commit()
    findings = check_c1_1(session, company.id, 2024)
    assert len(findings) == 1
    assert findings[0].severity == "critical"


def test_c1_1_uses_sxxk_import_codes(session, company):
    # E31 + E33 are SXXK import codes; E11 (DNCX) must NOT be summed for SXXK.
    add_decl(session, company.id, declaration_no="z", customs_code="E62", item_code="X", quantity=1)
    add_nvl(session, company.id, material_code="A", imported=1000)
    add_decl(session, company.id, declaration_no="1", customs_code="E31", item_code="A", quantity=300)
    add_decl(session, company.id, declaration_no="2", customs_code="E33", item_code="A", quantity=400)
    add_decl(session, company.id, declaration_no="3", customs_code="E11", item_code="A", quantity=300)
    session.commit()
    # SXXK detected → sum = 300 + 400 = 700, diff = -30% → critical.
    findings = check_c1_1(session, company.id, 2024)
    assert len(findings) == 1
    assert findings[0].severity == "critical"
    assert findings[0].details["bcct_sum"] == 700.0


# --- C1.2: Có tờ khai nhập nhưng không trong M15 ---


def test_c1_2_fires_when_bcct_only(session, company):
    add_decl(session, company.id, declaration_no="z", customs_code="E62", item_code="EX", quantity=1)
    add_decl(session, company.id, declaration_no="1", customs_code="E31", item_code="MISSING", quantity=100)
    session.commit()
    findings = check_c1_2(session, company.id, 2024)
    assert len(findings) == 1
    assert findings[0].check_code == "C1.2"
    assert findings[0].severity == "critical"
    assert findings[0].subject_key == "MISSING"


def test_c1_2_ignores_mmtb_E13_for_dncx(session, company):
    """E13 (MMTB) không được coi là NVL nhập — không phải finding C1.2.

    Trước fix: E13 trong IMPORT_CODES[DNCX] → mọi mã thiết bị nhập E13 bị flag
    "thiếu trong M15" (M15 chỉ chứa NVL). 28% findings C1.2 demo là noise loại này.
    """
    add_decl(session, company.id, declaration_no="d1", customs_code="E11", item_code="NVL_OK", quantity=10)
    add_decl(session, company.id, declaration_no="e1", customs_code="E42", item_code="TP1", quantity=5)
    add_nvl(session, company.id, material_code="NVL_OK", imported=10)
    # Thêm 1 tờ khai E13 (máy móc) — không được trở thành finding.
    add_decl(session, company.id, declaration_no="m1", customs_code="E13", item_code="MAY_MOC", quantity=1)
    session.commit()
    findings = check_c1_2(session, company.id, 2024)
    assert findings == [], f"E13 leak: {[f.subject_key for f in findings]}"


def test_c1_2_no_fire_when_in_m15(session, company):
    add_nvl(session, company.id, material_code="A", imported=0)  # presence is enough
    add_decl(session, company.id, declaration_no="1", customs_code="E31", item_code="A", quantity=100)
    add_decl(session, company.id, declaration_no="z", customs_code="E62", item_code="EX", quantity=1)
    session.commit()
    assert check_c1_2(session, company.id, 2024) == []


# --- C1.3: M15 có nhập_trong_kỳ > 0 nhưng không có tờ khai ---


def test_c1_3_fires_when_m15_only(session, company):
    add_nvl(session, company.id, material_code="ORPHAN", imported=500)
    add_decl(session, company.id, declaration_no="z", customs_code="E62", item_code="EX", quantity=1)
    session.commit()
    findings = check_c1_3(session, company.id, 2024)
    assert len(findings) == 1
    assert findings[0].subject_key == "ORPHAN"
    assert findings[0].severity == "critical"


def test_c1_3_skips_when_import_zero(session, company):
    add_nvl(session, company.id, material_code="ZERO", imported=0, opening=100)
    add_decl(session, company.id, declaration_no="z", customs_code="E62", item_code="EX", quantity=1)
    session.commit()
    assert check_c1_3(session, company.id, 2024) == []


# --- C1.4: Lệch số lượng xuất TP ---


def test_c1_4_fires_when_export_diff(session, company):
    add_sp(session, company.id, product_code="TP1", export_qty=1000)
    add_decl(session, company.id, declaration_no="1", customs_code="E62", item_code="TP1", quantity=900)
    session.commit()
    findings = check_c1_4(session, company.id, 2024)
    assert len(findings) == 1
    # Diff -10% > 5% threshold → critical for C1.4.
    assert findings[0].severity == "critical"


def test_c1_4_fires_info_when_diff_under_1pct(session, company):
    # Diff 0.5% — INFO band cho C1.4 (0.1% ≤ |diff| < 1%).
    add_sp(session, company.id, product_code="TP1", export_qty=1000)
    add_decl(session, company.id, declaration_no="1", customs_code="E62", item_code="TP1", quantity=995)
    session.commit()
    findings = check_c1_4(session, company.id, 2024)
    assert len(findings) == 1
    assert findings[0].severity == "info"


def test_c1_4_no_fire_when_under_floor(session, company):
    # Diff 0.05% — dưới floor 0.1%.
    add_sp(session, company.id, product_code="TP1", export_qty=1000)
    add_decl(session, company.id, declaration_no="1", customs_code="E62", item_code="TP1", quantity=999.5)
    session.commit()
    assert check_c1_4(session, company.id, 2024) == []


# --- C1.6: Chuyển MĐSD không có A42 ---


def test_c1_6_fires_when_no_a42(session, company):
    add_nvl(session, company.id, material_code="A", imported=1000, repurpose=200)
    add_decl(session, company.id, declaration_no="z", customs_code="E62", item_code="EX", quantity=1)
    session.commit()
    findings = check_c1_6(session, company.id, 2024)
    assert len(findings) == 1
    assert findings[0].severity == "critical"
    assert findings[0].subject_key == "A"


def test_c1_6_no_fire_when_a42_present(session, company):
    add_nvl(session, company.id, material_code="A", imported=1000, repurpose=200)
    add_decl(session, company.id, declaration_no="42", customs_code="A42", item_code="A", quantity=200)
    session.commit()
    assert check_c1_6(session, company.id, 2024) == []


# --- C1.7: Tỷ lệ chuyển MĐSD ---


def test_c1_7_no_fire_under_10pct(session, company):
    add_nvl(session, company.id, material_code="A", imported=1000, repurpose=50)
    session.commit()
    assert check_c1_7(session, company.id, 2024) == []


def test_c1_7_warning_at_15pct(session, company):
    add_nvl(session, company.id, material_code="A", imported=1000, repurpose=150)
    session.commit()
    findings = check_c1_7(session, company.id, 2024)
    assert len(findings) == 1
    assert findings[0].severity == "warning"


def test_c1_7_critical_at_30pct(session, company):
    add_nvl(session, company.id, material_code="A", imported=1000, repurpose=300)
    session.commit()
    findings = check_c1_7(session, company.id, 2024)
    assert len(findings) == 1
    assert findings[0].severity == "critical"


def test_c1_7_uses_opening_plus_import(session, company):
    # Denominator = opening + import (theo design)
    add_nvl(session, company.id, material_code="A", opening=500, imported=500, repurpose=200)
    session.commit()
    findings = check_c1_7(session, company.id, 2024)
    # 200/(500+500) = 20% → warning
    assert len(findings) == 1
    assert findings[0].severity == "warning"
    assert abs(findings[0].details["ratio_pct"] - 20.0) < 0.01
