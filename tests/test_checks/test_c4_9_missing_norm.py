"""C4.9 — TP có sản xuất trong kỳ nhưng thiếu định mức M16 (issue #61).

File riêng, không nhập vào `test_c4_norm.py`: C4.9 chỉ dùng chung module với
C4.1/C4.3 chứ không dùng chung dữ liệu dựng sẵn.
"""

from __future__ import annotations

from app.checks.c4_norm import check_c4_9
from tests.conftest import add_sp
from tests.test_checks.test_c4_norm import add_norm


def test_fires_for_a_product_never_declared_in_any_period(session, company):
    add_sp(session, company.id, product_code="TP_MOI", intake=500, year=2025)
    session.commit()

    findings = check_c4_9(session, company.id, 2025)
    assert len(findings) == 1
    f = findings[0]
    assert f.check_code == "C4.9"
    assert f.severity == "warning"
    assert f.subject_type == "product_code"
    assert f.subject_key == "TP_MOI"
    assert f.details["intake"] == 500
    assert "TP_MOI" in f.title


def test_evidence_points_at_the_m15a_row(session, company):
    add_sp(session, company.id, product_code="TP_MOI", intake=500, year=2025)
    session.commit()

    (f,) = check_c4_9(session, company.id, 2025)
    assert f.evidence_refs == [{
        "table": "sp_balances",
        "filter": {"company_id": company.id, "period_year": 2025, "product_code": "TP_MOI"},
    }]


def test_inherited_norm_from_an_earlier_period_does_not_fire(session, company):
    """Cốt lõi của cổng: Mẫu 16 kế thừa giữa các kỳ (issue #60).

    Đo trên pilot 05/08/2026, luật này xoá sạch 16/16 mã của DN 8/2025 — lọc đúng
    `period_year == year` sẽ báo thiếu định mức cho cả 16 mã đó.
    """
    add_sp(session, company.id, product_code="TP", intake=500, year=2025)
    add_norm(session, company.id, product_code="TP", material_code="A", norm_qty=1.0, year=2023)
    session.commit()
    assert check_c4_9(session, company.id, 2025) == []


def test_a_norm_declared_after_the_period_does_not_count(session, company):
    """Bản khai kỳ SAU không hồi tố: kỳ 2025 vẫn thiếu định mức."""
    add_sp(session, company.id, product_code="TP", intake=500, year=2025)
    add_norm(session, company.id, product_code="TP", material_code="A", norm_qty=1.0, year=2026)
    session.commit()

    (f,) = check_c4_9(session, company.id, 2025)
    assert f.subject_key == "TP"


def test_no_production_does_not_fire_even_without_a_norm(session, company):
    """Mã chỉ bán tồn cũ (nhập kho SX = 0) thì không cần định mức kỳ này."""
    add_sp(session, company.id, product_code="TON_CU", intake=0, export_qty=800, year=2025)
    session.commit()
    assert check_c4_9(session, company.id, 2025) == []


def test_norm_in_another_book_does_not_cover_production_in_this_book(session, company):
    """Mỗi sổ quyết toán là ledger riêng — định mức sổ EPE không phủ sản xuất sổ GC
    (ADR #19). Một phát hiện cho sổ GC, sổ EPE im lặng."""
    add_sp(session, company.id, product_code="TP", intake=100, book="EPE", year=2025)
    add_sp(session, company.id, product_code="TP", intake=100, book="GC", year=2025)
    add_norm(
        session, company.id, product_code="TP", material_code="A",
        norm_qty=1.0, book="EPE", year=2025,
    )
    session.commit()

    findings = check_c4_9(session, company.id, 2025)
    assert [(f.book, f.subject_key) for f in findings] == [("GC", "TP")]
    assert findings[0].evidence_refs[0]["filter"]["book"] == "GC"


def test_one_finding_per_product_code_sorted(session, company):
    """Cán bộ cần DANH SÁCH từng mã, không phải một con số tổng (yêu cầu 2.1)."""
    add_sp(session, company.id, product_code="TP_B", intake=10, year=2025)
    add_sp(session, company.id, product_code="TP_A", intake=20, year=2025)
    add_sp(session, company.id, product_code="TP_CO_DM", intake=30, year=2025)
    add_norm(
        session, company.id, product_code="TP_CO_DM", material_code="A",
        norm_qty=1.0, year=2025,
    )
    session.commit()

    findings = check_c4_9(session, company.id, 2025)
    assert [f.subject_key for f in findings] == ["TP_A", "TP_B"]


def test_registered_in_the_module_check_map(session, company):
    from app.checks.c4_norm import CHECKS

    assert CHECKS["C4.9"] is check_c4_9
