"""Unit tests cho Nhóm 3 — Phân loại hàng hoá."""

from __future__ import annotations

from app.checks.c3_classify import check_c3_1, check_c3_2, check_c3_3
from tests.conftest import add_decl, add_nvl

# --- C3.1: NVL × MMTB mâu thuẫn ---


def test_c3_1_fires_when_e31_and_e13(session, company):
    add_decl(session, company.id, declaration_no="1", customs_code="E31", item_code="DUAL", quantity=100)
    add_decl(session, company.id, declaration_no="2", customs_code="E13", item_code="DUAL", quantity=1)
    session.commit()
    findings = check_c3_1(session, company.id, 2024)
    assert len(findings) == 1
    assert findings[0].check_code == "C3.1"
    assert findings[0].severity == "warning"
    assert findings[0].subject_key == "DUAL"


def test_c3_1_no_fire_when_only_nvl(session, company):
    add_decl(session, company.id, declaration_no="1", customs_code="E31", item_code="ONLY_NVL", quantity=100)
    session.commit()
    assert check_c3_1(session, company.id, 2024) == []


# --- C3.2: Mã HS không nhất quán (scale chương/nhóm/phân nhóm) ---


def test_c3_2_no_fire_same_hs(session, company):
    add_decl(session, company.id, declaration_no="1", customs_code="E31",
             item_code="A", quantity=10, hs_code="64041990")
    add_decl(session, company.id, declaration_no="2", customs_code="E31",
             item_code="A", quantity=10, hs_code="64041990")
    session.commit()
    assert check_c3_2(session, company.id, 2024) == []


def test_c3_2_info_when_different_subheading(session, company):
    # 6404 1990 vs 6404 1910 — khác phân nhóm (6 số: 640419 vs 640419 — same)
    # → cần thực sự khác 6 số: 6404 1990 vs 6404 2010 (640419 vs 640420)
    add_decl(session, company.id, declaration_no="1", customs_code="E31",
             item_code="A", quantity=10, hs_code="64041990")
    add_decl(session, company.id, declaration_no="2", customs_code="E31",
             item_code="A", quantity=10, hs_code="64042010")
    session.commit()
    findings = check_c3_2(session, company.id, 2024)
    assert len(findings) == 1
    assert findings[0].severity == "info"
    assert findings[0].details["divergence"] == "subheading"


def test_c3_2_warning_when_different_heading(session, company):
    # 6404 vs 6405 — khác nhóm 4 số, cùng chương 64
    add_decl(session, company.id, declaration_no="1", customs_code="E31",
             item_code="B", quantity=10, hs_code="64041990")
    add_decl(session, company.id, declaration_no="2", customs_code="E31",
             item_code="B", quantity=10, hs_code="64051000")
    session.commit()
    findings = check_c3_2(session, company.id, 2024)
    assert len(findings) == 1
    assert findings[0].severity == "warning"
    assert findings[0].details["divergence"] == "heading"


def test_c3_2_critical_when_different_chapter(session, company):
    # 64 vs 41 — khác chương
    add_decl(session, company.id, declaration_no="1", customs_code="E31",
             item_code="C", quantity=10, hs_code="64041990")
    add_decl(session, company.id, declaration_no="2", customs_code="E31",
             item_code="C", quantity=10, hs_code="41079900")
    session.commit()
    findings = check_c3_2(session, company.id, 2024)
    assert len(findings) == 1
    assert findings[0].severity == "critical"
    assert findings[0].details["divergence"] == "chapter"


# --- C3.3: Đơn vị tính không nhất quán ---


def test_c3_3_alias_mtr_metres_no_fire(session, company):
    add_nvl(session, company.id, material_code="A", unit="MTR")
    add_decl(session, company.id, declaration_no="1", customs_code="E31",
             item_code="A", quantity=10, unit="METRES")
    session.commit()
    assert check_c3_3(session, company.id, 2024) == []


def test_c3_3_fires_when_real_mismatch(session, company):
    add_nvl(session, company.id, material_code="A", unit="KG")
    add_decl(session, company.id, declaration_no="1", customs_code="E31",
             item_code="A", quantity=10, unit="PIECES")
    session.commit()
    findings = check_c3_3(session, company.id, 2024)
    assert len(findings) == 1
    assert findings[0].severity == "critical"
    assert findings[0].subject_key == "A"
