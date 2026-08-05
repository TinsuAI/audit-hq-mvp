"""Unit tests cho Nhóm 4 — Định mức M16.

Cổng độ phủ định mức (issue #62) có test riêng ở `test_norm_gate.py`.
"""

from __future__ import annotations

import pytest

from app.adapters.m16 import is_domestic_origin
from app.checks.c4_norm import check_c4_1, check_c4_3
from app.models import Norm
from tests.conftest import add_nvl, add_sp


@pytest.fixture(autouse=True)
def confirmed_first_bcqt_year(session, company):
    """Xác nhận 2024 là năm đầu nộp BCQT của DN fixture.

    C4.3 trả `NotEvaluable` ở kỳ sớm nhất hệ thống đang giữ khi chưa biết năm đầu nộp
    BCQT (issue #62). Các test trong file này kiểm PHÉP TÍNH của C4.3, không kiểm cổng
    — không xác nhận thì mọi fixture 1 kỳ đều dừng ở cổng kỳ biên.
    """
    company.first_bcqt_year = 2024
    session.commit()


def add_norm(
    session,
    company_id: int,
    *,
    product_code: str,
    material_code: str,
    norm_qty: float,
    note: str | None = None,
    book: str | None = None,
    year: int = 2024,
):
    n = Norm(
        company_id=company_id,
        period_year=year,
        book=book,
        product_code=product_code,
        material_code=material_code,
        norm_qty=norm_qty,
        note=note,
    )
    session.add(n)
    return n


# --- C4.1: NVL M16 không có nguồn ---


def test_c4_1_fires_when_no_m15(session, company):
    add_sp(session, company.id, product_code="TP", export_qty=100)
    add_norm(session, company.id, product_code="TP", material_code="GHOST", norm_qty=1.0)
    session.commit()
    findings = check_c4_1(session, company.id, 2024)
    assert len(findings) == 1
    assert findings[0].subject_key == "GHOST"
    assert findings[0].details["reason"] == "no_m15"


def test_c4_1_fires_when_m15_zero_source(session, company):
    add_nvl(session, company.id, material_code="ZERO", imported=0, opening=0)
    add_norm(session, company.id, product_code="TP", material_code="ZERO", norm_qty=1.0)
    session.commit()
    findings = check_c4_1(session, company.id, 2024)
    assert len(findings) == 1
    assert findings[0].details["reason"] == "zero_source"


def test_c4_1_no_fire_with_import(session, company):
    add_nvl(session, company.id, material_code="OK", imported=100)
    add_norm(session, company.id, product_code="TP", material_code="OK", norm_qty=1.0)
    session.commit()
    assert check_c4_1(session, company.id, 2024) == []


def test_c4_1_no_fire_with_opening(session, company):
    add_nvl(session, company.id, material_code="STK", imported=0, opening=50)
    add_norm(session, company.id, product_code="TP", material_code="STK", norm_qty=1.0)
    session.commit()
    assert check_c4_1(session, company.id, 2024) == []


def test_is_domestic_origin():
    assert is_domestic_origin("x")
    assert is_domestic_origin(" X ")
    assert not is_domestic_origin(None)
    assert not is_domestic_origin("")
    assert not is_domestic_origin("nhập khẩu")


def test_c4_1_skips_domestic_origin(session, company):
    # Mã xuất xứ trong nước (Ghi chú "x") không có nguồn nhập → KHÔNG flag.
    add_norm(session, company.id, product_code="TP", material_code="VN", norm_qty=1.0, note="x")
    session.commit()
    assert check_c4_1(session, company.id, 2024) == []


def test_c4_1_still_fires_for_imported_no_source(session, company):
    # Cùng tình huống nhưng không phải hàng nội địa → vẫn flag.
    add_norm(session, company.id, product_code="TP", material_code="NK", norm_qty=1.0, note=None)
    session.commit()
    findings = check_c4_1(session, company.id, 2024)
    assert len(findings) == 1
    assert findings[0].subject_key == "NK"


# --- C4.3: tiêu hao lý thuyết vượt xuất SX ---


def test_c4_3_uses_production_output_not_exports(session, company):
    """P-07: số nhân là sản lượng SẢN XUẤT (M15a.intake_qty), không phải xuất khẩu.

    intake (sản lượng sản xuất) = 100 → khớp actual production_out = 100 → 0% lệch,
    KHÔNG fire. export_qty = 1000 rất khác intake — nếu code còn dùng export_qty làm
    số nhân, theoretical = 1.0*1000 = 1000 vs actual 100 → +900% → fire critical sai.
    """
    add_sp(session, company.id, product_code="TP", intake=100, export_qty=1000)
    add_norm(session, company.id, product_code="TP", material_code="X", norm_qty=1.0)
    add_nvl(session, company.id, material_code="X", imported=100, production_out=100)
    session.commit()
    assert check_c4_3(session, company.id, 2024) == []


def test_c4_3_no_fire_when_close(session, company):
    # theoretical = 1.0 * 100 = 100; actual = 100 → 0% lệch
    add_sp(session, company.id, product_code="TP", intake=100)
    add_norm(session, company.id, product_code="TP", material_code="X", norm_qty=1.0)
    add_nvl(session, company.id, material_code="X", imported=100, production_out=100)
    session.commit()
    assert check_c4_3(session, company.id, 2024) == []


def test_c4_3_warning_when_over_10pct(session, company):
    # theoretical = 1.0 * 100 = 100; actual = 90 → +11.1% lệch → warning (5-20%)
    add_sp(session, company.id, product_code="TP", intake=100)
    add_norm(session, company.id, product_code="TP", material_code="X", norm_qty=1.0)
    add_nvl(session, company.id, material_code="X", imported=100, production_out=90)
    session.commit()
    findings = check_c4_3(session, company.id, 2024)
    assert len(findings) == 1
    assert findings[0].severity == "warning"


def test_c4_3_critical_when_over_20pct(session, company):
    # theoretical = 2.0 * 100 = 200; actual = 100 → +100% lệch → critical
    add_sp(session, company.id, product_code="TP", intake=100)
    add_norm(session, company.id, product_code="TP", material_code="X", norm_qty=2.0)
    add_nvl(session, company.id, material_code="X", imported=200, production_out=100)
    session.commit()
    findings = check_c4_3(session, company.id, 2024)
    assert len(findings) == 1
    assert findings[0].severity == "critical"


def test_c4_3_critical_when_m15_has_no_production_out(session, company):
    # theoretical > 0 nhưng M15 không xuất SX gì cả → 100% lệch → critical
    add_sp(session, company.id, product_code="TP", intake=100)
    add_norm(session, company.id, product_code="TP", material_code="X", norm_qty=1.0)
    add_nvl(session, company.id, material_code="X", imported=100, production_out=0)
    session.commit()
    findings = check_c4_3(session, company.id, 2024)
    assert len(findings) == 1
    assert findings[0].severity == "critical"


def test_c4_3_skips_material_without_any_m15_row(session, company):
    """Không có DÒNG M15 nào ≠ có dòng M15 với xuất SX = 0 (issue #59).

    Mã NVL có tiêu hao lý thuyết mà không có dòng nào trong M15 là ca THIẾU NGUỒN —
    đất của C4.1 ("NVL trong M16 không có nguồn"). C4.3 bỏ qua, không được coi như
    xuất SX = 0 rồi bắn Nghiêm trọng. Mã CÓ dòng M15 mà xuất SX = 0 là mâu thuẫn thật
    (đã khai nguồn nhưng không xuất cho sản xuất) → vẫn bắn.
    """
    add_sp(session, company.id, product_code="TP", intake=100)
    add_norm(session, company.id, product_code="TP", material_code="GHOST", norm_qty=1.0)
    add_norm(session, company.id, product_code="TP", material_code="ZERO", norm_qty=1.0)
    add_nvl(session, company.id, material_code="ZERO", imported=100, production_out=0)
    session.commit()
    findings = check_c4_3(session, company.id, 2024)
    assert [f.subject_key for f in findings] == ["ZERO"]
    assert findings[0].severity == "critical"


def test_c4_3_missing_m15_row_is_judged_inside_the_book(session, company):
    """Dòng M15 ở SỔ KHÁC không kéo mã vào phạm vi C4.3 của sổ này (ADR #19).

    Sổ EPE: mã X có dòng M15, tiêu hao khớp → không lệch. Sổ GC: cùng mã X có định mức
    và sản lượng nhưng KHÔNG có dòng M15 trong sổ đó → bỏ qua. Nếu tra "có dòng M15"
    trên toàn DN thay vì trong sổ thì dòng của EPE kéo mã X của GC vào và bắn Nghiêm
    trọng với xuất SX = 0.
    """
    add_norm(session, company.id, product_code="TP_E", material_code="X", norm_qty=1.0, book="EPE")
    add_sp(session, company.id, product_code="TP_E", intake=100, book="EPE")
    add_nvl(session, company.id, material_code="X", production_out=100, book="EPE")
    add_norm(session, company.id, product_code="TP_G", material_code="X", norm_qty=2.0, book="GC")
    add_sp(session, company.id, product_code="TP_G", intake=100, book="GC")
    session.commit()
    assert check_c4_3(session, company.id, 2024) == []


def test_c4_3_repeated_bom_block_counted_once(session, company):
    """Mẫu 16 lặp nguyên khối định mức cho MỖI đợt sản xuất.

    Catalog (đề án §C4.3): tiêu hao = Σ(định_mức × sản_lượng_sản_xuất). Cộng dồn qua
    mọi DÒNG sẽ nhân thêm số lần lặp — 3 khối giống nhau thành 300 thay vì 100.
    """
    add_sp(session, company.id, product_code="TP", intake=100)
    for _ in range(3):
        add_norm(session, company.id, product_code="TP", material_code="X", norm_qty=1.0)
    add_nvl(session, company.id, material_code="X", imported=100, production_out=100)
    session.commit()
    assert check_c4_3(session, company.id, 2024) == []


def test_c4_3_divergent_repeated_norms_use_max_and_are_reported(session, company):
    """Khối lặp mang định mức KHÁC nhau: lấy MAX, nhưng phải hiện ra, không chọn thầm."""
    add_sp(session, company.id, product_code="TP", intake=100)
    add_norm(session, company.id, product_code="TP", material_code="X", norm_qty=1.0)
    add_norm(session, company.id, product_code="TP", material_code="X", norm_qty=2.0)
    add_nvl(session, company.id, material_code="X", imported=200, production_out=100)
    session.commit()
    findings = check_c4_3(session, company.id, 2024)
    assert len(findings) == 1
    # MAX = 2.0 -> theoretical 200 vs actual 100
    assert findings[0].details["theoretical_consumption"] == 200.0
    assert findings[0].details["divergent_norm_products"] == ["TP"]


# --- Nội-sổ: đánh giá per book (đa loại hình) ---


def test_c4_1_evaluates_each_book_independently(session, company):
    # Mã X ở hai sổ: sổ EPE có nguồn (M15 nhập>0), sổ GC KHÔNG có dòng M15.
    # Phải fire cho sổ GC (thiếu nguồn) và KHÔNG bị dòng M15 sổ EPE che.
    add_norm(session, company.id, product_code="TP", material_code="X", norm_qty=1.0, book="EPE")
    add_nvl(session, company.id, material_code="X", imported=100, book="EPE")
    add_norm(session, company.id, product_code="TP", material_code="X", norm_qty=1.0, book="GC")
    session.commit()
    findings = check_c4_1(session, company.id, 2024)
    assert len(findings) == 1
    assert findings[0].subject_key == "X"
    assert findings[0].book == "GC"
    assert findings[0].details["reason"] == "no_m15"


def test_c4_3_computes_each_book_independently(session, company):
    # Mã X dùng ở hai sổ với định mức khác nhau — tiêu hao lý thuyết tính TRONG từng
    # sổ, không cộng chéo sổ.
    # Sổ EPE: 1.0 × 100 = 100 == xuất SX 100 → không lệch.
    add_norm(session, company.id, product_code="TP_E", material_code="X", norm_qty=1.0, book="EPE")
    add_sp(session, company.id, product_code="TP_E", intake=100, book="EPE")
    add_nvl(session, company.id, material_code="X", production_out=100, book="EPE")
    # Sổ GC: 2.0 × 100 = 200 > xuất SX 100 → lệch +100%.
    add_norm(session, company.id, product_code="TP_G", material_code="X", norm_qty=2.0, book="GC")
    add_sp(session, company.id, product_code="TP_G", intake=100, book="GC")
    add_nvl(session, company.id, material_code="X", production_out=100, book="GC")
    session.commit()
    findings = check_c4_3(session, company.id, 2024)
    assert len(findings) == 1
    assert findings[0].book == "GC"
    assert findings[0].subject_key == "X"
    assert findings[0].details["theoretical_consumption"] == 200.0


# --- Định mức hiệu lực: kế thừa giữa các kỳ (issue #60) ---


def test_c4_3_uses_a_norm_inherited_from_an_earlier_period(session, company):
    # DN khai định mức năm 2023, năm 2024 không khai lại. Lọc period_year == 2024
    # làm mất định mức và C4.3 im lặng; bản khai gần nhất ≤ kỳ thì vẫn tính được.
    add_norm(session, company.id, product_code="TP", material_code="X", norm_qty=2.0, year=2023)
    add_sp(session, company.id, product_code="TP", intake=100, year=2024)
    add_nvl(session, company.id, material_code="X", production_out=100, year=2024)
    session.commit()
    findings = check_c4_3(session, company.id, 2024)
    assert len(findings) == 1
    assert findings[0].subject_key == "X"
    assert findings[0].details["theoretical_consumption"] == 200.0
    assert findings[0].details["norm_source_years"] == [2023]


def test_c4_3_evidence_points_at_the_period_the_norm_was_declared_in(session, company):
    # Truy nguồn (đề án §5.1): chứng cứ định mức phải trỏ về kỳ ĐÃ KHAI, không phải
    # kỳ phát hiện — kỳ phát hiện không có dòng norms nào để mở ra.
    add_norm(session, company.id, product_code="TP", material_code="X", norm_qty=2.0, year=2023)
    add_sp(session, company.id, product_code="TP", intake=100, year=2024)
    add_nvl(session, company.id, material_code="X", production_out=100, year=2024)
    session.commit()
    findings = check_c4_3(session, company.id, 2024)
    norm_ref = next(r for r in findings[0].evidence_refs if r["table"] == "norms")
    assert norm_ref["filter"]["period_year__in"] == [2023]
    nvl_ref = next(r for r in findings[0].evidence_refs if r["table"] == "nvl_balances")
    assert nvl_ref["filter"]["period_year"] == 2024


def test_c4_3_prefers_the_redeclared_norm_over_the_inherited_one(session, company):
    add_norm(session, company.id, product_code="TP", material_code="X", norm_qty=9.0, year=2023)
    add_norm(session, company.id, product_code="TP", material_code="X", norm_qty=2.0, year=2024)
    add_sp(session, company.id, product_code="TP", intake=100, year=2024)
    add_nvl(session, company.id, material_code="X", production_out=100, year=2024)
    session.commit()
    findings = check_c4_3(session, company.id, 2024)
    assert findings[0].details["theoretical_consumption"] == 200.0
    assert findings[0].details["norm_source_years"] == [2024]


def test_c4_3_does_not_inherit_a_norm_from_a_later_period(session, company):
    # TP đã khai định mức cho mã A ở 2024 nên độ phủ định mức đủ (cổng #62 không
    # chặn); mã X chỉ được khai ở 2025 → không được kéo ngược về kỳ 2024.
    add_norm(session, company.id, product_code="TP", material_code="A", norm_qty=1.0, year=2024)
    add_norm(session, company.id, product_code="TP", material_code="X", norm_qty=2.0, year=2025)
    add_sp(session, company.id, product_code="TP", intake=100, year=2024)
    add_nvl(session, company.id, material_code="A", production_out=100, year=2024)
    add_nvl(session, company.id, material_code="X", production_out=100, year=2024)
    session.commit()
    assert check_c4_3(session, company.id, 2024) == []
