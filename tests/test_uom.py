"""Tests cho UOM helpers + C3.3 severity ladder.

UOM canonical/aliases được seed trong conftest.session fixture.
"""

from __future__ import annotations

from app.checks.uom import UomMatch, compare, get_family, resolve_canonical
from app.models import UomAlias


def _add_alias(session, alias: str, canonical: str):
    session.add(UomAlias(alias=alias, canonical_code=canonical))
    session.commit()
    from app.checks.uom import invalidate_cache
    invalidate_cache()


def test_resolve_canonical_basic(session):
    assert resolve_canonical(session, "MTR") == "MTR"
    assert resolve_canonical(session, "METRES") == "MTR"
    assert resolve_canonical(session, "m") == "MTR"
    _add_alias(session, "CHIẾC", "PCE")
    assert resolve_canonical(session, "CHIẾC") == "PCE"


def test_resolve_unknown_returns_none(session):
    assert resolve_canonical(session, "UNKNOWN_UNIT") is None
    assert resolve_canonical(session, None) is None
    assert resolve_canonical(session, "") is None


def test_get_family(session):
    assert get_family(session, "MTR") == "length"
    assert get_family(session, "CM") == "length"
    assert get_family(session, "KG") == "mass"
    assert get_family(session, "GAM") == "mass"
    assert get_family(session, "UNKNOWN") is None


def test_compare_equivalent_via_alias(session):
    # MTR ↔ METRES = same canonical → EQUIVALENT
    assert compare(session, "MTR", "METRES") == UomMatch.EQUIVALENT
    assert compare(session, "KG", "KGM") == UomMatch.EQUIVALENT
    _add_alias(session, "PCS", "PCE")
    _add_alias(session, "CHIẾC", "PCE")
    assert compare(session, "PCS", "CHIẾC") == UomMatch.EQUIVALENT


def test_compare_same_family_convertible(session):
    # MTR vs CMT: cùng family length nhưng khác canonical → SAME_FAMILY
    assert compare(session, "MTR", "CM") == UomMatch.SAME_FAMILY
    assert compare(session, "KG", "GAM") == UomMatch.SAME_FAMILY


def test_compare_different_family(session):
    # MTR (length) vs KG (mass) → DIFFERENT
    assert compare(session, "MTR", "KG") == UomMatch.DIFFERENT
    assert compare(session, "PCE", "MTR") == UomMatch.DIFFERENT


def test_compare_unknown_units(session):
    # Cả 2 unknown nhưng raw equal → EQUIVALENT (raw fallback)
    assert compare(session, "FOO", "FOO") == UomMatch.EQUIVALENT
    # 1 known, 1 unknown → DIFFERENT
    assert compare(session, "MTR", "FOO") == UomMatch.DIFFERENT


def test_compare_normalizes_case_and_whitespace(session):
    assert compare(session, "  mtr  ", "Metres") == UomMatch.EQUIVALENT


# --- C3.3 với UOM severity ladder ---


def test_c3_3_severity_ladder_with_uom(session, company):
    from app.checks.c3_classify import check_c3_3
    from tests.conftest import add_decl, add_nvl

    # NVL A: KG vs GAM (same family, different canonical) → INFO
    add_nvl(session, company.id, material_code="A", unit="KG")
    add_decl(session, company.id, declaration_no="1", customs_code="E31",
             item_code="A", quantity=10, unit="GAM")

    # NVL B: KG vs PCE (different family) → CRITICAL
    add_nvl(session, company.id, material_code="B", unit="KG")
    add_decl(session, company.id, declaration_no="2", customs_code="E31",
             item_code="B", quantity=10, unit="PCE")

    # NVL C: MTR vs METRES (equivalent via alias) → SKIP
    add_nvl(session, company.id, material_code="C", unit="MTR")
    add_decl(session, company.id, declaration_no="3", customs_code="E31",
             item_code="C", quantity=10, unit="METRES")

    session.commit()
    findings = check_c3_3(session, company.id, 2024)

    by_code = {f.subject_key: f for f in findings}
    assert "C" not in by_code
    assert by_code["A"].severity == "info"
    assert by_code["A"].details["uom_match"] == "same_family"
    assert by_code["B"].severity == "critical"
    assert by_code["B"].details["uom_match"] == "different"
