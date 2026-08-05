"""Định mức hiệu lực — Mẫu 16 kế thừa giữa các kỳ (issue #60)."""

from __future__ import annotations

from app.checks.effective_norms import (
    effective_norms,
    produced_products,
    production_intake,
    products_without_norm,
)
from tests.conftest import add_sp
from tests.test_checks.test_c4_norm import add_norm


def test_uses_latest_declaration_at_or_before_the_period(session, company):
    add_norm(session, company.id, product_code="TP", material_code="A", norm_qty=1.0, year=2023)
    add_norm(session, company.id, product_code="TP", material_code="A", norm_qty=2.0, year=2025)
    session.commit()

    assert effective_norms(session, company.id, 2023)[None][("TP", "A")].norm_qty == 1.0
    # 2024 không khai lại → vẫn hiệu lực bản 2023.
    got_2024 = effective_norms(session, company.id, 2024)[None][("TP", "A")]
    assert got_2024.norm_qty == 1.0
    assert got_2024.source_year == 2023
    assert effective_norms(session, company.id, 2025)[None][("TP", "A")].norm_qty == 2.0


def test_ignores_declarations_after_the_period(session, company):
    add_norm(session, company.id, product_code="TP", material_code="A", norm_qty=9.0, year=2026)
    session.commit()
    assert effective_norms(session, company.id, 2025) == {}


def test_does_not_inherit_across_books(session, company):
    add_norm(
        session, company.id, product_code="TP", material_code="A",
        norm_qty=1.0, year=2023, book="EPE",
    )
    session.commit()
    got = effective_norms(session, company.id, 2025)
    assert ("TP", "A") in got["EPE"]
    # Sổ GC không có bản khai nào → không được mượn định mức của sổ EPE (ADR #19).
    assert "GC" not in got


def test_repeated_blocks_in_the_source_period_take_max_and_flag(session, company):
    add_norm(session, company.id, product_code="TP", material_code="A", norm_qty=1.0, year=2023)
    add_norm(session, company.id, product_code="TP", material_code="A", norm_qty=3.0, year=2023)
    session.commit()
    got = effective_norms(session, company.id, 2024)[None][("TP", "A")]
    assert got.norm_qty == 3.0
    assert got.divergent is True


def test_newer_period_wins_over_a_larger_older_value(session, company):
    """Kỳ mới thắng, KHÔNG phải giá trị lớn thắng — MAX chỉ áp trong cùng kỳ nguồn."""
    add_norm(session, company.id, product_code="TP", material_code="A", norm_qty=99.0, year=2023)
    add_norm(session, company.id, product_code="TP", material_code="A", norm_qty=1.0, year=2024)
    session.commit()
    got = effective_norms(session, company.id, 2025)[None][("TP", "A")]
    assert got.norm_qty == 1.0
    assert got.source_year == 2024
    assert got.divergent is False


def test_produced_products_only_counts_positive_intake(session, company):
    add_sp(session, company.id, product_code="MADE", intake=10, year=2025)
    add_sp(session, company.id, product_code="IDLE", intake=0, year=2025)
    add_sp(session, company.id, product_code="SOLD", intake=0, export_qty=50, year=2025)
    session.commit()
    assert produced_products(session, company.id, 2025)[None] == {"MADE"}


def test_production_intake_sums_rows_per_book(session, company):
    add_sp(session, company.id, product_code="TP", intake=10, year=2025)
    add_sp(session, company.id, product_code="TP", intake=15, year=2025)
    add_sp(session, company.id, product_code="TP", intake=7, book="GC", year=2025)
    add_sp(session, company.id, product_code="IDLE", intake=0, year=2025)
    session.commit()

    got = production_intake(session, company.id, 2025)
    assert got == {None: {"TP": 25.0}, "GC": {"TP": 7.0}}
    # Cùng bộ khoá với produced_products — hai hàm không được lệch nhau.
    assert {b: set(v) for b, v in got.items()} == produced_products(session, company.id, 2025)


def test_products_without_norm_accepts_an_inherited_declaration(session, company):
    add_sp(session, company.id, product_code="TP", intake=10, year=2025)
    add_norm(session, company.id, product_code="TP", material_code="A", norm_qty=1.0, year=2023)
    session.commit()
    # Có định mức kế thừa từ 2023 → không thiếu.
    assert products_without_norm(session, company.id, 2025) == {}


def test_products_without_norm_reports_a_product_never_declared(session, company):
    add_sp(session, company.id, product_code="TP", intake=10, year=2025)
    add_sp(session, company.id, product_code="GHOST", intake=5, year=2025)
    add_norm(session, company.id, product_code="TP", material_code="A", norm_qty=1.0, year=2024)
    session.commit()
    assert products_without_norm(session, company.id, 2025) == {None: {"GHOST"}}
