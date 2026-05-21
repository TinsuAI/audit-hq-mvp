"""Unit tests cho C5.1 — Truy nguồn NVL."""

from __future__ import annotations

from app.checks.c5_trace import check_c5_1
from tests.conftest import add_nvl


def test_c5_1_fires_when_production_out_but_no_source(session, company):
    add_nvl(session, company.id, material_code="ORPHAN", opening=0, imported=0, production_out=100)
    session.commit()
    findings = check_c5_1(session, company.id, 2024)
    assert len(findings) == 1
    assert findings[0].severity == "critical"
    assert findings[0].subject_key == "ORPHAN"


def test_c5_1_no_fire_when_has_opening(session, company):
    add_nvl(session, company.id, material_code="WITH_STK", opening=50, imported=0, production_out=40)
    session.commit()
    assert check_c5_1(session, company.id, 2024) == []


def test_c5_1_no_fire_when_has_import(session, company):
    add_nvl(session, company.id, material_code="WITH_IMP", opening=0, imported=100, production_out=80)
    session.commit()
    assert check_c5_1(session, company.id, 2024) == []


def test_c5_1_no_fire_when_no_production_out(session, company):
    add_nvl(session, company.id, material_code="NO_OUT", opening=0, imported=0, production_out=0)
    session.commit()
    assert check_c5_1(session, company.id, 2024) == []
