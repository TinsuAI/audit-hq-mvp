"""Tests cho scripts/anonymize.py + scripts/restore.py."""

from __future__ import annotations

from sqlalchemy import select

from app.models import Company, DeclarationLine
from scripts.anonymize import COMPANY_MAPPING, _deterministic_mst, _ncc_alias, anonymize


def test_deterministic_mst_is_stable_and_10_digits():
    a = _deterministic_mst("5400273360")
    b = _deterministic_mst("5400273360")
    assert a == b
    assert len(a) == 10
    assert a.isdigit()


def test_deterministic_mst_different_seeds_give_different_codes():
    assert _deterministic_mst("X") != _deterministic_mst("Y")


def test_ncc_alias_includes_index_and_hash():
    a = _ncc_alias("Canon Park Trading Limited", 5)
    assert a.startswith("NCC_005_")
    assert len(a) >= 14


def test_company_mapping_covers_all_5_demo_companies():
    # Verify mapping cố định trùng với demo plan §6.1.
    for code in ["GROWATT", "KIM_LONG", "HONG_AN", "DO_THANH", "HONG_PHUC"]:
        assert code in COMPANY_MAPPING
        assert COMPANY_MAPPING[code]["code"].startswith("DN_00")


def test_anonymize_replaces_company_fields(session, company):
    # Override company code để khớp với mapping.
    company.code = "HONG_AN"
    company.tax_id = "5400273360"
    company.name = "Công ty Cổ phần Giầy Hồng An"
    session.commit()

    mapping = anonymize(session)

    refreshed = session.scalar(select(Company).where(Company.code == "DN_003"))
    assert refreshed is not None
    assert refreshed.name == "Doanh nghiệp DN_003"
    assert refreshed.tax_id != "5400273360"
    assert len(refreshed.tax_id) == 10
    assert refreshed.tax_id.isdigit()

    assert "DN_003" in mapping["companies"]
    assert mapping["companies"]["DN_003"]["original_tax_id"] == "5400273360"


def test_anonymize_is_idempotent(session, company):
    company.code = "GROWATT"
    company.tax_id = "0202177200"
    session.commit()

    mapping1 = anonymize(session)
    mapping2 = anonymize(session)

    assert mapping1["companies"]
    # Lần thứ 2: không có company nào còn ở dạng raw (đều đã DN_xxx).
    assert mapping2["companies"] == {}


def test_anonymize_replaces_partners(session, company):
    company.code = "HONG_AN"
    session.commit()
    line = DeclarationLine(
        company_id=company.id,
        period_year=2024,
        declaration_no="123456789",
        customs_code="E62",
        partner="Canon Park Trading Limited",
    )
    session.add(line)
    session.commit()

    anonymize(session)

    updated = session.scalar(select(DeclarationLine).where(DeclarationLine.id == line.id))
    assert updated.partner != "Canon Park Trading Limited"
    assert updated.partner.startswith("NCC_")


def test_anonymize_skips_already_anonymized(session, company):
    company.code = "DN_003"
    session.commit()
    mapping = anonymize(session)
    assert mapping["companies"] == {}


def test_anonymize_dry_run_does_not_modify(session, company):
    company.code = "HONG_AN"
    company.tax_id = "5400273360"
    orig_name = company.name = "Original"
    session.commit()

    mapping = anonymize(session, dry_run=True)

    # Mapping có thông tin (preview) nhưng DB không đổi.
    assert "DN_003" in mapping["companies"]
    refreshed = session.scalar(select(Company).where(Company.code == "HONG_AN"))
    assert refreshed is not None
    assert refreshed.tax_id == "5400273360"
    assert refreshed.name == orig_name
