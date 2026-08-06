"""Quy phát hiện ra tiền — đơn giá bình quân tờ khai + xếp hạng theo giá trị."""

from __future__ import annotations

from app.checks.c1_quantity import check_c1_1
from app.checks.c4_norm import check_c4_3
from app.checks.valuation import material_prices_vnd, money_value
from tests.conftest import add_decl, add_norm, add_nvl, add_sp


def test_price_is_weighted_by_quantity(session, company):
    # 100 × 1.000đ và 900 × 2.000đ → bình quân 1.900đ, KHÔNG phải trung bình cộng 1.500đ.
    add_decl(session, company.id, declaration_no="1", customs_code="E31",
             item_code="A", quantity=100, value_total=100_000)
    add_decl(session, company.id, declaration_no="2", customs_code="E31",
             item_code="A", quantity=900, value_total=1_800_000)
    session.commit()
    prices = material_prices_vnd(session, company.id, 2024)
    assert prices["A"] == 1_900_000 / 1_000


def test_lines_without_value_do_not_drag_the_average_down(session, company):
    add_decl(session, company.id, declaration_no="1", customs_code="E31",
             item_code="A", quantity=10, value_total=100_000)
    add_decl(session, company.id, declaration_no="2", customs_code="E31",
             item_code="A", quantity=10, value_total=None)
    session.commit()
    assert material_prices_vnd(session, company.id, 2024)["A"] == 10_000


def test_customs_codes_narrow_the_price_source(session, company):
    add_decl(session, company.id, declaration_no="1", customs_code="E31",
             item_code="A", quantity=10, value_total=100_000)
    add_decl(session, company.id, declaration_no="2", customs_code="B13",
             item_code="A", quantity=10, value_total=500_000)
    session.commit()
    assert material_prices_vnd(session, company.id, 2024, {"E31"})["A"] == 10_000


def test_money_value_is_none_without_a_price(session, company):
    # None ≠ 0: mã không tra được giá phải nằm cuối bảng xếp theo tiền, không lẫn
    # vào nhóm giá trị nhỏ.
    assert money_value({}, "A", 100) is None
    assert money_value({"A": 0.0}, "A", 100) == 0.0


def test_c1_1_values_the_gap_not_the_whole_import(session, company):
    # M15 nhập 100, tờ khai 150 → chênh 50 × 10.000đ = 500.000đ.
    add_nvl(session, company.id, material_code="A", unit="PCE", imported=100)
    add_decl(session, company.id, declaration_no="1", customs_code="E31",
             item_code="A", quantity=150, value_total=1_500_000)
    session.commit()
    findings = check_c1_1(session, company.id, 2024)
    assert len(findings) == 1
    assert findings[0].value_vnd == 500_000
    assert findings[0].details["value_vnd"] == 500_000


def test_c1_1_leaves_value_none_when_the_code_has_no_priced_line(session, company):
    add_nvl(session, company.id, material_code="A", unit="PCE", imported=100)
    add_decl(session, company.id, declaration_no="1", customs_code="E31",
             item_code="A", quantity=150)
    session.commit()
    findings = check_c1_1(session, company.id, 2024)
    assert len(findings) == 1
    assert findings[0].value_vnd is None


def test_c4_3_values_the_excess_consumption(session, company):
    company.first_bcqt_year = 2024  # qua cổng kỳ biên, xem test_c4_norm
    add_sp(session, company.id, product_code="TP", intake=100)
    add_norm(session, company.id, product_code="TP", material_code="A", norm_qty=2.0)
    add_nvl(session, company.id, material_code="A", unit="PCE", imported=300,
            production_out=100)
    add_decl(session, company.id, declaration_no="1", customs_code="E31",
             item_code="A", quantity=300, value_total=3_000_000)
    session.commit()
    # Tiêu hao lý thuyết 2 × 100 = 200 vs xuất SX 100 → vượt 100 × 10.000đ.
    findings = check_c4_3(session, company.id, 2024)
    assert len(findings) == 1
    assert findings[0].value_vnd == 1_000_000
