"""Unit tests cho C6.1 (NVL, Mẫu 15) và C6.2 (thành phẩm, Mẫu 15a) — tồn đầu kỳ N ≠ tồn cuối kỳ N-1."""

from __future__ import annotations

from app.checks.c6_cross_period import check_c6_1, check_c6_2
from app.checks.not_evaluable import NotEvaluable
from tests.conftest import add_nvl, add_sp


def test_c6_1_not_evaluable_when_no_prev_year(session, company):
    add_nvl(session, company.id, material_code="A", opening=100, year=2024)
    session.commit()
    # Không có M15 kỳ 2023 → không có tồn cuối để đối chiếu. Trả 0 phát hiện ở đây
    # đọc như "tồn đầu kỳ nào cũng khớp", trong khi thực tế chưa so gì cả.
    result = check_c6_1(session, company.id, 2024)
    assert isinstance(result, NotEvaluable)
    assert "2023" in result.reason


def test_c6_1_evaluates_when_prev_year_present(session, company):
    # Có kỳ trước, mọi mã khớp → 'ok' kèm 0 phát hiện, KHÁC not_evaluable ở trên.
    add_nvl(session, company.id, material_code="A", closing=10, year=2023)
    add_nvl(session, company.id, material_code="A", opening=10, year=2024)
    session.commit()
    assert check_c6_1(session, company.id, 2024) == []


def test_c6_1_no_fire_when_match(session, company):
    add_nvl(session, company.id, material_code="A", opening=0, closing=120, year=2023)
    add_nvl(session, company.id, material_code="A", opening=120, year=2024)
    session.commit()
    assert check_c6_1(session, company.id, 2024) == []


def test_c6_1_fires_when_mismatch(session, company):
    add_nvl(session, company.id, material_code="A", opening=0, closing=120, year=2023)
    add_nvl(session, company.id, material_code="A", opening=100, year=2024)  # 100 ≠ 120
    session.commit()
    findings = check_c6_1(session, company.id, 2024)
    assert len(findings) == 1
    assert findings[0].check_code == "C6.1"
    assert findings[0].severity == "critical"
    assert findings[0].details["diff"] == -20.0


def test_c6_1_fires_when_new_code_has_opening(session, company):
    # NVL mới xuất hiện 2024 với opening > 0 nhưng 2023 không có
    add_nvl(session, company.id, material_code="OTHER", opening=0, closing=50, year=2023)
    add_nvl(session, company.id, material_code="NEW", opening=30, year=2024)
    session.commit()
    findings = check_c6_1(session, company.id, 2024)
    assert len(findings) == 1
    assert findings[0].subject_key == "NEW"
    assert findings[0].details["previous_closing"] is None


def test_c6_1_no_fire_when_new_code_zero_opening(session, company):
    # NVL mới chỉ phát sinh trong 2024 với opening = 0 → hợp lệ
    add_nvl(session, company.id, material_code="OTHER", opening=0, closing=50, year=2023)
    add_nvl(session, company.id, material_code="NEW", opening=0, imported=100, year=2024)
    session.commit()
    assert check_c6_1(session, company.id, 2024) == []


def test_c6_1_compares_within_each_book(session, company):
    # Mã X ở hai sổ: tồn cuối kỳ trước phải so TRONG cùng sổ, không lẫn sổ.
    # Sổ EPE: cuối 2023 = 100, đầu 2024 = 100 → khớp.
    add_nvl(session, company.id, material_code="X", closing=100, book="EPE", year=2023)
    add_nvl(session, company.id, material_code="X", opening=100, book="EPE", year=2024)
    # Sổ GC: cuối 2023 = 50, đầu 2024 = 100 → lệch +50.
    add_nvl(session, company.id, material_code="X", closing=50, book="GC", year=2023)
    add_nvl(session, company.id, material_code="X", opening=100, book="GC", year=2024)
    session.commit()
    findings = check_c6_1(session, company.id, 2024)
    assert len(findings) == 1
    assert findings[0].book == "GC"
    assert findings[0].details["previous_closing"] == 50


# --- C6.2 — cùng phép đối chiếu, đọc Mẫu 15a thay vì Mẫu 15 ---


def test_c6_2_not_evaluable_when_no_prev_year(session, company):
    add_sp(session, company.id, product_code="TP-A", opening=100, year=2024)
    session.commit()
    result = check_c6_2(session, company.id, 2024)
    assert isinstance(result, NotEvaluable)
    assert "2023" in result.reason
    # Lý do phải gọi đúng tên biểu — cán bộ đi tìm Mẫu 15a, không phải Mẫu 15.
    assert "15a" in result.reason


def test_c6_2_does_not_read_m15_to_decide_it_can_run(session, company):
    """Có Mẫu 15 kỳ trước KHÔNG đủ để chạy C6.2 — nó cần Mẫu 15a kỳ trước.

    Hai biểu nạp rời nhau, nên đây là ca thật chứ không phải giả định: đọc nhầm cổng
    sang M15 thì C6.2 chạy trên tập rỗng và trả 0 phát hiện, đọc như "mọi thành phẩm
    khớp" trong khi chưa so mã nào.
    """
    add_nvl(session, company.id, material_code="A", closing=10, year=2023)
    add_sp(session, company.id, product_code="TP-A", opening=100, year=2024)
    session.commit()
    assert isinstance(check_c6_2(session, company.id, 2024), NotEvaluable)


def test_c6_2_evaluates_when_prev_year_present(session, company):
    add_sp(session, company.id, product_code="TP-A", closing=10, year=2023)
    add_sp(session, company.id, product_code="TP-A", opening=10, year=2024)
    session.commit()
    assert check_c6_2(session, company.id, 2024) == []


def test_c6_2_fires_when_mismatch(session, company):
    add_sp(session, company.id, product_code="TP-A", opening=0, closing=120, year=2023)
    add_sp(session, company.id, product_code="TP-A", opening=100, year=2024)
    session.commit()
    findings = check_c6_2(session, company.id, 2024)
    assert len(findings) == 1
    assert findings[0].check_code == "C6.2"
    assert findings[0].severity == "critical"
    assert findings[0].subject_type == "product_code"
    assert findings[0].subject_key == "TP-A"
    assert findings[0].details["diff"] == -20.0
    assert [ref["table"] for ref in findings[0].evidence_refs] == ["sp_balances", "sp_balances"]


def test_c6_2_no_fire_inside_tolerance(session, company):
    add_sp(session, company.id, product_code="TP-A", closing=120.0, year=2023)
    add_sp(session, company.id, product_code="TP-A", opening=120.005, year=2024)
    session.commit()
    assert check_c6_2(session, company.id, 2024) == []


def test_c6_2_fires_when_new_code_has_opening(session, company):
    add_sp(session, company.id, product_code="TP-OTHER", closing=50, year=2023)
    add_sp(session, company.id, product_code="TP-NEW", opening=30, year=2024)
    session.commit()
    findings = check_c6_2(session, company.id, 2024)
    assert len(findings) == 1
    assert findings[0].subject_key == "TP-NEW"
    assert findings[0].details["previous_closing"] is None


def test_c6_2_no_fire_when_new_code_zero_opening(session, company):
    add_sp(session, company.id, product_code="TP-OTHER", closing=50, year=2023)
    add_sp(session, company.id, product_code="TP-NEW", opening=0, intake=100, year=2024)
    session.commit()
    assert check_c6_2(session, company.id, 2024) == []


def test_c6_2_compares_within_each_book(session, company):
    add_sp(session, company.id, product_code="TP-X", closing=100, book="EPE", year=2023)
    add_sp(session, company.id, product_code="TP-X", opening=100, book="EPE", year=2024)
    add_sp(session, company.id, product_code="TP-X", closing=50, book="GC", year=2023)
    add_sp(session, company.id, product_code="TP-X", opening=100, book="GC", year=2024)
    session.commit()
    findings = check_c6_2(session, company.id, 2024)
    assert len(findings) == 1
    assert findings[0].book == "GC"
    assert findings[0].details["previous_closing"] == 50


def test_c6_1_and_c6_2_do_not_gate_on_each_other(session, company):
    """Mẫu 15 kỳ trước có, Mẫu 15a kỳ trước không — mỗi check tự quyết theo biểu của nó."""
    add_nvl(session, company.id, material_code="A", closing=10, year=2023)
    add_nvl(session, company.id, material_code="A", opening=10, year=2024)
    add_sp(session, company.id, product_code="TP-A", opening=10, year=2024)
    session.commit()
    assert check_c6_1(session, company.id, 2024) == []
    assert isinstance(check_c6_2(session, company.id, 2024), NotEvaluable)
