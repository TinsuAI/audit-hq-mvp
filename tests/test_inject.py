"""Tests cho scripts/inject_findings.py."""

from __future__ import annotations

from app.models import Company, Finding, Norm, NvlBalance
from scripts.inject_findings import (
    INJECT_MARK,
    clean_dn_005,
    inject_dn_003_2024,
    recompute_company_scores,
)


def _seed_dn_003(session) -> Company:
    c = Company(code="DN_003", tax_id="9999999999", name="Test")
    session.add(c)
    session.flush()

    # Vài NVL có data sẵn để inject hook vào.
    session.add_all([
        NvlBalance(company_id=c.id, period_year=2024, material_code="DG",
                   opening_qty=3068, import_qty=6400, production_out_qty=0,
                   closing_qty=9468, unit="PR"),
        NvlBalance(company_id=c.id, period_year=2024, material_code="KHUY",
                   opening_qty=0, import_qty=202350, production_out_qty=0,
                   closing_qty=202350, unit="PCE"),
        NvlBalance(company_id=c.id, period_year=2024, material_code="DD-2",
                   opening_qty=1361.54, import_qty=0, production_out_qty=1361.54,
                   closing_qty=0, unit="MTR"),
        NvlBalance(company_id=c.id, period_year=2024, material_code="HDG",
                   opening_qty=1305, import_qty=2382, production_out_qty=0,
                   closing_qty=3687, unit="PR"),
        Norm(company_id=c.id, period_year=2024,
             product_code="TP1", material_code="DG", norm_qty=1.0),
        Norm(company_id=c.id, period_year=2024,
             product_code="TP1", material_code="DD-2", norm_qty=0.5),
    ])
    session.commit()
    return c


def test_inject_dn_003_modifies_4_target_materials(session, company):
    # Use seed-specific company (override conftest fixture).
    session.query(Company).delete()
    session.commit()
    _seed_dn_003(session)

    changes: list = []
    inject_dn_003_2024(session, changes)
    session.commit()

    # Verify mỗi mã đã được modify.
    dg = session.query(NvlBalance).filter_by(material_code="DG").one()
    assert dg.closing_qty == -150.0  # C2.3 fire

    khuy = session.query(NvlBalance).filter_by(material_code="KHUY").one()
    # closing đã được set thành expected + 999 (lệch 999)
    assert abs(khuy.closing_qty - 203349.0) < 0.01  # 202350 + 999

    dd2 = session.query(NvlBalance).filter_by(material_code="DD-2").one()
    assert dd2.opening_qty == 0.0  # C5.1 setup
    assert dd2.production_out_qty == 500.0

    hdg = session.query(NvlBalance).filter_by(material_code="HDG").one()
    assert hdg.repurpose_qty == 250.0  # C1.6 setup


def test_inject_dn_003_is_idempotent(session, company):
    session.query(Company).delete()
    session.commit()
    _seed_dn_003(session)

    changes1: list = []
    inject_dn_003_2024(session, changes1)
    session.commit()
    n1 = len(changes1)

    changes2: list = []
    inject_dn_003_2024(session, changes2)
    session.commit()

    assert n1 > 0
    assert len(changes2) == 0  # lần 2 không thay đổi gì


def test_inject_amplifies_norm_for_combo(session, company):
    session.query(Company).delete()
    session.commit()
    _seed_dn_003(session)

    original_norm = session.query(Norm).filter_by(material_code="DG").first().norm_qty

    changes: list = []
    inject_dn_003_2024(session, changes)
    session.commit()

    new_norm = session.query(Norm).filter_by(material_code="DG").first().norm_qty
    assert new_norm == original_norm * 100  # x100 amplify


def test_clean_dn_005_rejects_critical_findings(session, company):
    session.query(Company).delete()
    session.commit()
    c = Company(code="DN_005", name="Test")
    session.add(c)
    session.flush()
    session.add_all([
        Finding(company_id=c.id, period_year=2024, check_code="C1.1",
                severity="critical", title="x"),
        Finding(company_id=c.id, period_year=2024, check_code="C1.2",
                severity="critical", title="y"),
        Finding(company_id=c.id, period_year=2024, check_code="C3.2",
                severity="warning", title="keep"),
    ])
    session.commit()

    n = clean_dn_005(session)
    session.commit()

    assert n == 2
    rejected = session.query(Finding).filter_by(status="rejected").all()
    assert len(rejected) == 2
    assert all(INJECT_MARK in (f.notes or "") for f in rejected)
    kept = session.query(Finding).filter_by(severity="warning").one()
    assert kept.status == "new"  # warning vẫn giữ


def test_recompute_company_scores(session, company):
    session.query(Company).delete()
    session.commit()
    c = Company(code="X", name="X")
    session.add(c)
    session.flush()
    session.add_all([
        Finding(company_id=c.id, period_year=2024, check_code="C1.1",
                severity="critical", title="x"),     # 10
        Finding(company_id=c.id, period_year=2024, check_code="C1.2",
                severity="warning", title="y"),       # 3
        Finding(company_id=c.id, period_year=2024, check_code="C1.3",
                severity="critical", status="rejected", title="z"),  # skip
    ])
    session.commit()

    recompute_company_scores(session)
    session.commit()

    refreshed = session.query(Company).filter_by(code="X").one()
    assert refreshed.risk_score == 13  # 10 + 3
