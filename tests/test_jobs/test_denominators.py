"""Test compute_denominators — số mã NVL/TP/Norm distinct theo (DN, năm)."""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.checks.denominators import RULE_SCOPE, compute_denominators
from app.models import Company, DeclarationLine, Norm, NvlBalance, SpBalance


def _company(session: Session) -> int:
    c = Company(code="DN_D", tax_id="1", name="D")
    session.add(c)
    session.commit()
    return c.id


def test_empty_denominators_are_zero(session: Session) -> None:
    cid = _company(session)
    d = compute_denominators(session, cid, 2024)
    assert d["nvl"] == 0
    assert d["tp"] == 0
    assert d["m16"] == 0


def test_nvl_denominator_union_m15_and_bcct(session: Session) -> None:
    cid = _company(session)
    session.add_all([
        NvlBalance(company_id=cid, period_year=2024, material_code="A", unit="KG"),
        NvlBalance(company_id=cid, period_year=2024, material_code="B", unit="KG"),
        DeclarationLine(
            company_id=cid, period_year=2024, declaration_no="1",
            declaration_date=date(2024, 1, 1), customs_code="E31",
            item_code="C", hs_code="1", quantity=1, unit="KG",
        ),
    ])
    session.commit()
    d = compute_denominators(session, cid, 2024)
    # NVL distinct = {A, B} ∪ NVL-side declarations {C} = 3.
    assert d["nvl"] == 3


def test_tp_denominator_counts_sp_balances_and_export_decls(session: Session) -> None:
    cid = _company(session)
    session.add_all([
        SpBalance(company_id=cid, period_year=2024, product_code="P1", unit="PCE"),
        SpBalance(company_id=cid, period_year=2024, product_code="P2", unit="PCE"),
        # Export-side declaration (E62) introduces extra product code.
        DeclarationLine(
            company_id=cid, period_year=2024, declaration_no="2",
            declaration_date=date(2024, 1, 1), customs_code="E62",
            item_code="P3", hs_code="1", quantity=10, unit="PCE",
        ),
    ])
    session.commit()
    d = compute_denominators(session, cid, 2024)
    assert d["tp"] == 3


def test_m16_denominator_counts_distinct_material_in_norms(session: Session) -> None:
    cid = _company(session)
    session.add_all([
        Norm(company_id=cid, period_year=2024, product_code="P1",
             material_code="M1", norm_qty=1.0, product_unit="PCE", material_unit="KG"),
        Norm(company_id=cid, period_year=2024, product_code="P1",
             material_code="M2", norm_qty=2.0, product_unit="PCE", material_unit="KG"),
        Norm(company_id=cid, period_year=2024, product_code="P2",
             material_code="M1", norm_qty=1.0, product_unit="PCE", material_unit="KG"),
    ])
    session.commit()
    d = compute_denominators(session, cid, 2024)
    # Distinct material_code in norms = {M1, M2}.
    assert d["m16"] == 2


def test_rule_scope_covers_all_known_checks() -> None:
    """Mỗi check trong catalog phải có scope nvl/tp/m16."""
    from app.checks.registry import SPECS
    for code in SPECS:
        assert code in RULE_SCOPE, f"Missing denominator scope cho {code}"
        assert RULE_SCOPE[code] in {"nvl", "tp", "m16"}
