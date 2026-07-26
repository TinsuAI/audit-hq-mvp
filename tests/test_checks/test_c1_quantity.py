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


# --- C1.1 / C1.4: gộp union theo (mã, đơn vị) khi một mã có nhiều dòng M15 (đa sổ) ---


def test_c1_1_sums_rows_of_same_code_and_unit(session, company):
    # Mã C xuất hiện ở HAI SỔ: import_qty phải CỘNG qua sổ trước khi so tờ khai (một
    # luồng tờ khai cho cả pháp nhân), KHÔNG so per-row và KHÔNG gộp theo (sổ, mã, đơn vị).
    add_nvl(session, company.id, material_code="C", unit="PCE", imported=500, book="EPE")
    add_nvl(session, company.id, material_code="C", unit="PCE", imported=500, book="GC")
    add_decl(session, company.id, declaration_no="1", customs_code="E11", item_code="C", quantity=1000)
    session.commit()
    # 500 + 500 == 1000 khai → khớp → không finding. (per-row hiện tại: 2 finding critical)
    assert check_c1_1(session, company.id, 2024) == []


def test_c1_4_sums_rows_of_same_code_and_unit(session, company):
    # Mã TP P ở hai sổ: export_qty phải CỘNG theo (mã, đơn vị) qua cả hai sổ.
    add_sp(session, company.id, product_code="P", unit="PCE", export_qty=500, book="EPE")
    add_sp(session, company.id, product_code="P", unit="PCE", export_qty=500, book="GC")
    add_decl(session, company.id, declaration_no="1", customs_code="E42", item_code="P", quantity=1000)
    session.commit()
    assert check_c1_4(session, company.id, 2024) == []


def test_c1_3_tags_finding_with_book(session, company):
    # M15 khai nhập nhưng không có tờ khai → fire, mang nhãn sổ để truy nguồn.
    add_nvl(session, company.id, material_code="X", imported=100, book="GC")
    add_decl(session, company.id, declaration_no="1", customs_code="E11", item_code="Y", quantity=5)
    session.commit()
    findings = check_c1_3(session, company.id, 2024)
    assert len(findings) == 1
    assert findings[0].subject_key == "X"
    assert findings[0].book == "GC"


# --- Đa đơn vị: một mã ghi ở hai đơn vị là MỘT lượng tồn ghi lại, không phải hai vật tư ---


def test_c1_3_emits_one_finding_per_material_across_units(session, company):
    add_nvl(session, company.id, material_code="DUAL", unit="MTR", imported=3000)
    add_nvl(session, company.id, material_code="DUAL", unit="PCE", imported=1)
    add_decl(session, company.id, declaration_no="z", customs_code="E11", item_code="OTHER", quantity=1)
    session.commit()
    findings = check_c1_3(session, company.id, 2024)
    assert [f.subject_key for f in findings] == ["DUAL"]


def test_c1_3_reports_the_largest_unit_slice(session, company):
    # Dòng nhỏ nằm trước trong bảng — finding vẫn phải báo lượng lớn, không phụ thuộc thứ tự dòng.
    add_nvl(session, company.id, material_code="DUAL", unit="PCE", imported=1)
    add_nvl(session, company.id, material_code="DUAL", unit="MTR", imported=3000)
    add_decl(session, company.id, declaration_no="z", customs_code="E11", item_code="OTHER", quantity=1)
    session.commit()
    findings = check_c1_3(session, company.id, 2024)
    assert len(findings) == 1
    assert findings[0].details["m15_import"] == 3000
    assert "3000" in findings[0].title


def test_c1_3_keeps_one_finding_per_book_for_shared_code(session, company):
    # Khử trùng theo (sổ, mã) — KHÔNG được gộp hai sổ vào một finding.
    add_nvl(session, company.id, material_code="SHARED", unit="MTR", imported=100, book="EPE")
    add_nvl(session, company.id, material_code="SHARED", unit="MTR", imported=200, book="GC")
    add_decl(session, company.id, declaration_no="z", customs_code="E11", item_code="OTHER", quantity=1)
    session.commit()
    findings = check_c1_3(session, company.id, 2024)
    assert sorted(f.book for f in findings) == ["EPE", "GC"]


def test_c1_6_emits_one_finding_per_material_across_units(session, company):
    add_nvl(session, company.id, material_code="DUAL", unit="MTR", imported=3000, repurpose=600)
    add_nvl(session, company.id, material_code="DUAL", unit="PCE", imported=1, repurpose=0.2)
    add_decl(session, company.id, declaration_no="z", customs_code="E62", item_code="EX", quantity=1)
    session.commit()
    findings = check_c1_6(session, company.id, 2024)
    assert [f.subject_key for f in findings] == ["DUAL"]
    assert findings[0].details["m15_repurpose"] == 600


def test_c1_1_no_fire_when_one_unit_slice_matches_declaration(session, company):
    # Lát MTR khớp đơn vị tờ khai và khớp số → nhất quán. Lát PIECES là cùng lượng đó
    # ghi lại, KHÔNG được đem so với tổng tờ khai tính bằng mét.
    add_nvl(session, company.id, material_code="DUAL", unit="MTR", imported=20000)
    add_nvl(session, company.id, material_code="DUAL", unit="PIECES", imported=20)
    add_decl(session, company.id, declaration_no="1", customs_code="E11", item_code="DUAL",
             quantity=20000, unit="M")
    session.commit()
    assert check_c1_1(session, company.id, 2024) == []


def test_c1_1_reports_undeclared_dual_unit_material_once(session, company):
    # Không tờ khai nào cho mã này → vẫn phải fire -100%, nhưng CHỈ MỘT lần.
    add_nvl(session, company.id, material_code="DUAL", unit="MTR", imported=4463)
    add_nvl(session, company.id, material_code="DUAL", unit="PIECES", imported=1.49)
    add_decl(session, company.id, declaration_no="z", customs_code="E11", item_code="OTHER", quantity=1)
    session.commit()
    findings = check_c1_1(session, company.id, 2024)
    assert len(findings) == 1
    assert findings[0].subject_key == "DUAL"
    assert findings[0].details["m15_import"] == 4463
    assert abs(findings[0].details["diff_pct"] + 100.0) < 0.01


def test_c1_1_sums_rows_whose_units_are_aliases_of_one_canonical(session, company):
    # 'MTR' và 'METRES' là cùng một đơn vị vật lý (cùng canonical) → phải CỘNG,
    # không tách thành hai lát rồi đem mỗi lát so với cả tổng tờ khai.
    add_nvl(session, company.id, material_code="ALIAS", unit="MTR", imported=10000)
    add_nvl(session, company.id, material_code="ALIAS", unit="METRES", imported=10000)
    add_decl(session, company.id, declaration_no="1", customs_code="E11", item_code="ALIAS",
             quantity=20000, unit="M")
    session.commit()
    assert check_c1_1(session, company.id, 2024) == []


def test_c1_1_handles_row_with_null_unit(session, company):
    # Dòng thiếu đơn vị không được làm hỏng cả lượt chạy check.
    add_nvl(session, company.id, material_code="NU", unit=None, imported=500)
    add_nvl(session, company.id, material_code="NU", unit="MTR", imported=500)
    add_decl(session, company.id, declaration_no="1", customs_code="E11", item_code="NU",
             quantity=500, unit="M")
    session.commit()
    assert check_c1_1(session, company.id, 2024) == []


def test_c1_4_handles_row_with_null_unit(session, company):
    # sp_balances thực tế đang có dòng đơn vị NULL → C1.4 phải chịu được.
    add_sp(session, company.id, product_code="NU", unit=None, export_qty=500)
    add_sp(session, company.id, product_code="NU", unit="MTR", export_qty=500)
    add_decl(session, company.id, declaration_no="1", customs_code="E42", item_code="NU",
             quantity=500, unit="M")
    session.commit()
    assert check_c1_4(session, company.id, 2024) == []


def test_c1_4_no_fire_when_one_unit_slice_matches_declaration(session, company):
    add_sp(session, company.id, product_code="TP", unit="MTR", export_qty=20000)
    add_sp(session, company.id, product_code="TP", unit="PIECES", export_qty=20)
    add_decl(session, company.id, declaration_no="1", customs_code="E42", item_code="TP",
             quantity=20000, unit="M")
    session.commit()
    assert check_c1_4(session, company.id, 2024) == []


def test_c1_7_emits_one_finding_per_material_across_units(session, company):
    # Hai lát tỉ lệ thuận cho cùng một tỉ số → không được bắn hai lần.
    add_nvl(session, company.id, material_code="DUAL", unit="MTR", imported=3000, repurpose=600)
    add_nvl(session, company.id, material_code="DUAL", unit="PCE", imported=1, repurpose=0.2)
    session.commit()
    findings = check_c1_7(session, company.id, 2024)
    assert [f.subject_key for f in findings] == ["DUAL"]
    assert abs(findings[0].details["ratio_pct"] - 20.0) < 0.01
    assert findings[0].details["import"] == 3000


# --- Pháp nhân nhiều sổ: tờ khai dùng chung, M15 tách sổ (ADR #19) ---


def test_c1_2_treats_m15_of_every_book_as_declared(session, company):
    """Mã chỉ có trong M15 của sổ GC vẫn tính là "đã có trong M15".

    Đây là bản vá union mà ADR #19 sinh ra: luồng tờ khai là của cả pháp nhân, nên
    tập mã M15 đem trừ phải là hợp của mọi sổ. Lọc M15 theo sổ đưa C1.2 của 004 từ
    4 lên 99 — 91 finding giả cho mã thuộc sổ kia.
    """
    add_nvl(session, company.id, material_code="EPE_ONLY", imported=100, book="EPE")
    add_nvl(session, company.id, material_code="GC_ONLY", imported=100, book="GC")
    add_decl(session, company.id, declaration_no="1", customs_code="E11", item_code="EPE_ONLY", quantity=100)
    add_decl(session, company.id, declaration_no="2", customs_code="E11", item_code="GC_ONLY", quantity=100)
    add_decl(session, company.id, declaration_no="3", customs_code="E11", item_code="MISSING_BOTH",
             quantity=7)
    add_decl(session, company.id, declaration_no="4", customs_code="E42", item_code="TP", quantity=1)
    session.commit()
    findings = check_c1_2(session, company.id, 2024)
    assert [f.subject_key for f in findings] == ["MISSING_BOTH"]


def test_c1_2_finding_is_not_attributed_to_a_book(session, company):
    # Không quy được về sổ nào → book=NULL = "Chung (liên sổ)". Gán đại một sổ là
    # khẳng định điều check chưa kết luận (vi phạm truy nguồn, ADR #19 Revision).
    add_nvl(session, company.id, material_code="EPE_ONLY", imported=100, book="EPE")
    add_decl(session, company.id, declaration_no="1", customs_code="E11", item_code="EPE_ONLY", quantity=100)
    add_decl(session, company.id, declaration_no="2", customs_code="E11", item_code="MISSING", quantity=7)
    add_decl(session, company.id, declaration_no="3", customs_code="E42", item_code="TP", quantity=1)
    session.commit()
    findings = check_c1_2(session, company.id, 2024)
    assert len(findings) == 1
    assert findings[0].book is None


def test_c1_3_accepts_an_unlabelled_declaration_for_a_book_labelled_row(session, company):
    """Dòng M15 mang nhãn sổ được thoả bởi tờ khai KHÔNG mang nhãn.

    `declaration_lines` không có cột `book` — tờ khai là của cả pháp nhân. Nếu C1.3
    đòi tờ khai cùng sổ thì MỌI dòng M15 có nhãn đều bắn, vì không tờ khai nào có nhãn.
    """
    add_nvl(session, company.id, material_code="EPE_MAT", imported=100, book="EPE")
    add_nvl(session, company.id, material_code="GC_MAT", imported=100, book="GC")
    add_decl(session, company.id, declaration_no="1", customs_code="E11", item_code="EPE_MAT", quantity=100)
    add_decl(session, company.id, declaration_no="2", customs_code="E11", item_code="GC_MAT", quantity=100)
    add_decl(session, company.id, declaration_no="3", customs_code="E42", item_code="TP", quantity=1)
    session.commit()
    assert check_c1_3(session, company.id, 2024) == []


def test_c1_1_finding_is_not_attributed_to_a_book(session, company):
    # Vế đối chiếu là tổng tờ khai toàn pháp nhân, cộng qua cả hai sổ → book=NULL.
    add_nvl(session, company.id, material_code="SHARED", unit="PCE", imported=500, book="EPE")
    add_nvl(session, company.id, material_code="SHARED", unit="PCE", imported=500, book="GC")
    add_decl(session, company.id, declaration_no="1", customs_code="E11", item_code="SHARED", quantity=900)
    add_decl(session, company.id, declaration_no="2", customs_code="E42", item_code="TP", quantity=1)
    session.commit()
    findings = check_c1_1(session, company.id, 2024)
    assert len(findings) == 1
    assert findings[0].details["m15_import"] == 1000
    assert findings[0].book is None


def test_c1_4_finding_is_not_attributed_to_a_book(session, company):
    add_sp(session, company.id, product_code="P", unit="PCE", export_qty=500, book="EPE")
    add_sp(session, company.id, product_code="P", unit="PCE", export_qty=500, book="GC")
    add_decl(session, company.id, declaration_no="1", customs_code="E42", item_code="P", quantity=900)
    session.commit()
    findings = check_c1_4(session, company.id, 2024)
    assert len(findings) == 1
    assert findings[0].details["m15a_export"] == 1000
    assert findings[0].book is None
