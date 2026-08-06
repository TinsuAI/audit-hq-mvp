"""Unit tests cho Nhóm 3 — Phân loại hàng hoá."""

from __future__ import annotations

from app.checks.c3_classify import check_c3_1, check_c3_2, check_c3_3
from app.checks.not_evaluable import NotEvaluable
from tests.conftest import add_decl, add_norm, add_nvl

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


def test_c3_1_and_c3_2_are_not_attributed_to_a_book(session, company):
    # Cả hai check đọc DUY NHẤT `declaration_lines` — bảng không có cột `book` vì tờ
    # khai là của cả pháp nhân. Dù DN có hai sổ, finding vẫn phải để "Chung (liên sổ)".
    add_nvl(session, company.id, material_code="DUAL", book="EPE", imported=1)
    add_nvl(session, company.id, material_code="DUAL", book="GC", imported=1)
    add_decl(session, company.id, declaration_no="1", customs_code="E31", item_code="DUAL",
             quantity=100, hs_code="39011000")
    add_decl(session, company.id, declaration_no="2", customs_code="E13", item_code="DUAL",
             quantity=1, hs_code="84771000")
    session.commit()
    c3_1 = check_c3_1(session, company.id, 2024)
    c3_2 = check_c3_2(session, company.id, 2024)
    assert len(c3_1) == 1 and len(c3_2) == 1
    assert c3_1[0].book is None
    assert c3_2[0].book is None


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


def test_c3_3_checks_unit_per_book(session, company):
    # Mã X ở hai sổ với đơn vị khác nhau: đối chiếu đơn vị M15 vs tờ khai theo TỪNG sổ,
    # không để đơn vị sổ này che sổ kia.
    add_decl(session, company.id, declaration_no="1", customs_code="E31",
             item_code="X", quantity=10, unit="KG")
    add_nvl(session, company.id, material_code="X", unit="KG", book="EPE")      # khớp tờ khai
    add_nvl(session, company.id, material_code="X", unit="PIECES", book="GC")   # lệch
    session.commit()
    findings = check_c3_3(session, company.id, 2024)
    assert len(findings) == 1
    assert findings[0].book == "GC"
    assert findings[0].severity == "critical"


def test_c3_3_result_does_not_depend_on_m15_row_order(session, company):
    # Cùng một mã ghi ở hai đơn vị: nếu MỘT đơn vị khớp tờ khai thì sổ đó nhất quán.
    # Hai mã dưới đây chỉ khác nhau thứ tự dòng — kết quả phải giống nhau.
    add_decl(session, company.id, declaration_no="1", customs_code="E11",
             item_code="DUAL_A", quantity=3000, unit="M")
    add_decl(session, company.id, declaration_no="2", customs_code="E11",
             item_code="DUAL_B", quantity=3000, unit="M")
    add_nvl(session, company.id, material_code="DUAL_A", unit="MTR", imported=3000)
    add_nvl(session, company.id, material_code="DUAL_A", unit="PIECES", imported=1)
    add_nvl(session, company.id, material_code="DUAL_B", unit="PIECES", imported=1)
    add_nvl(session, company.id, material_code="DUAL_B", unit="MTR", imported=3000)
    session.commit()
    findings = check_c3_3(session, company.id, 2024)
    assert [f.subject_key for f in findings] == []


def test_c3_3_reports_every_m15_unit_it_saw(session, company):
    # Mã ghi ở hai đơn vị, cả hai đều lệch tờ khai → finding phải nêu cả hai,
    # không chỉ đơn vị đại diện, vì evidence trả về cả hai dòng.
    add_decl(session, company.id, declaration_no="1", customs_code="E11",
             item_code="TWO", quantity=10, unit="KG")
    add_nvl(session, company.id, material_code="TWO", unit="MTR", imported=10)
    add_nvl(session, company.id, material_code="TWO", unit="PIECES", imported=1)
    session.commit()
    findings = check_c3_3(session, company.id, 2024)
    assert len(findings) == 1
    assert findings[0].details["m15_units"] == ["MTR", "PIECES"]
    assert "MTR" in findings[0].title and "PIECES" in findings[0].title


# --- C3.3 vế M16 (sổ yêu cầu dòng 2.6) ---


def test_c3_3_fires_when_m16_unit_differs_from_m15(session, company):
    # Định mức khai KG, tồn kho khai PIECES: C4.3 nhân định mức rồi so với xuất SX
    # của M15 — hai vế khác họ đơn vị thì con số đó vô nghĩa.
    add_nvl(session, company.id, material_code="A", unit="KG")
    add_norm(session, company.id, product_code="TP", material_code="A",
             norm_qty=2.0, material_unit="PIECES")
    session.commit()
    findings = check_c3_3(session, company.id, 2024)
    assert len(findings) == 1
    assert findings[0].severity == "critical"
    assert findings[0].details["m16_units"] == ["PIECES"]
    assert findings[0].details["diverging_sources"] == ["M16"]


def test_c3_3_no_fire_when_m16_unit_is_an_alias(session, company):
    add_nvl(session, company.id, material_code="A", unit="MTR")
    add_norm(session, company.id, product_code="TP", material_code="A",
             norm_qty=2.0, material_unit="METRES")
    session.commit()
    assert check_c3_3(session, company.id, 2024) == []


def test_c3_3_names_both_sources_when_both_diverge(session, company):
    add_nvl(session, company.id, material_code="A", unit="KG")
    add_norm(session, company.id, product_code="TP", material_code="A",
             norm_qty=2.0, material_unit="PIECES")
    add_decl(session, company.id, declaration_no="1", customs_code="E31",
             item_code="A", quantity=10, unit="MTR")
    session.commit()
    findings = check_c3_3(session, company.id, 2024)
    assert len(findings) == 1
    assert findings[0].details["diverging_sources"] == ["BCCT", "M16"]


def test_c3_3_m16_compared_within_the_same_book(session, company):
    # Định mức sổ EPE không đem so với tồn kho sổ GC (ADR #19).
    add_nvl(session, company.id, material_code="X", unit="KG", book="EPE")
    add_nvl(session, company.id, material_code="X", unit="PIECES", book="GC")
    add_norm(session, company.id, product_code="TP", material_code="X",
             norm_qty=1.0, material_unit="KG", book="EPE")
    add_norm(session, company.id, product_code="TP", material_code="X",
             norm_qty=1.0, material_unit="PIECES", book="GC")
    session.commit()
    assert check_c3_3(session, company.id, 2024) == []


def test_c3_3_not_evaluable_without_bcct_and_m16(session, company):
    # Chỉ có M15: không có vế nào để đối chiếu. 0 phát hiện ở đây đọc như
    # "đơn vị nhất quán" trong khi chưa so gì.
    add_nvl(session, company.id, material_code="A", unit="KG")
    session.commit()
    result = check_c3_3(session, company.id, 2024)
    assert isinstance(result, NotEvaluable)
