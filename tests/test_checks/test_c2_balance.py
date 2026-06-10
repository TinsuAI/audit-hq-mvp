"""Unit tests cho Nhóm 2 — Cân bằng và tồn kho."""

from __future__ import annotations

from app.checks.c2_balance import check_c2_1, check_c2_2, check_c2_3, check_c2_4
from tests.conftest import add_nvl, add_sp

# --- C2.1: Mất cân bằng phương trình M15 ---


def test_c2_1_no_fire_when_balanced(session, company):
    # tồn_cuối = 100 + 50 - 0 - 0 - 30 - 0 = 120
    add_nvl(session, company.id, material_code="A", opening=100, imported=50, production_out=30, closing=120)
    session.commit()
    assert check_c2_1(session, company.id, 2024) == []


def test_c2_1_no_fire_within_tolerance(session, company):
    # Diff 0.005 dưới tolerance ±0.01
    add_nvl(
        session, company.id, material_code="A",
        opening=100, imported=50, production_out=30, closing=120.005,
    )
    session.commit()
    assert check_c2_1(session, company.id, 2024) == []


def test_c2_1_fires_when_unbalanced(session, company):
    # Closing thiếu 20 đơn vị
    add_nvl(session, company.id, material_code="A", opening=100, imported=50, production_out=30, closing=100)
    session.commit()
    findings = check_c2_1(session, company.id, 2024)
    assert len(findings) == 1
    f = findings[0]
    assert f.check_code == "C2.1"
    assert f.severity == "critical"
    assert f.subject_key == "A"
    assert abs(f.details["diff"] + 20.0) < 0.01
    assert "ghost_stock" not in f.details


def test_c2_1_ghost_stock_pattern(session, company):
    # opening = 0, closing > import → tồn ảo
    add_nvl(session, company.id, material_code="GHOST", opening=0, imported=100, closing=500)
    session.commit()
    findings = check_c2_1(session, company.id, 2024)
    assert len(findings) == 1
    f = findings[0]
    assert f.details.get("ghost_stock") is True
    assert "TỒN ẢO" in f.title


def test_c2_1_includes_all_components(session, company):
    # Có tái xuất + repurpose + xuất khác — phương trình đầy đủ
    # expected = 1000 + 200 - 50 - 30 - 800 - 20 = 300
    add_nvl(
        session, company.id, material_code="FULL",
        opening=1000, imported=200, reexport=50, repurpose=30,
        production_out=800, other_out=20, closing=300,
    )
    session.commit()
    assert check_c2_1(session, company.id, 2024) == []


# --- C2.2: Mất cân bằng phương trình M15a ---


def test_c2_2_no_fire_when_balanced(session, company):
    # closing = 0 + 1000 - 0 - 800 - 0 = 200
    add_sp(session, company.id, product_code="TP1", intake=1000, export_qty=800, closing=200)
    session.commit()
    assert check_c2_2(session, company.id, 2024) == []


def test_c2_2_fires_when_unbalanced(session, company):
    # closing đáng lẽ 200, khai 250 → diff +50
    add_sp(session, company.id, product_code="TP1", intake=1000, export_qty=800, closing=250)
    session.commit()
    findings = check_c2_2(session, company.id, 2024)
    assert len(findings) == 1
    f = findings[0]
    assert f.check_code == "C2.2"
    assert f.subject_key == "TP1"
    assert abs(f.details["diff"] - 50.0) < 0.01


# --- C2.3: Tồn cuối NVL âm ---


def test_c2_3_no_fire_when_zero_or_positive(session, company):
    add_nvl(session, company.id, material_code="POS", closing=10)
    add_nvl(session, company.id, material_code="ZERO", closing=0)
    add_nvl(session, company.id, material_code="TINY_NEG", closing=-0.005)  # under tolerance
    session.commit()
    assert check_c2_3(session, company.id, 2024) == []


def test_c2_3_fires_when_closing_negative(session, company):
    add_nvl(session, company.id, material_code="NEG1", closing=-50, unit="KG")
    add_nvl(session, company.id, material_code="NEG2", closing=-0.5, unit="MTR")
    add_nvl(session, company.id, material_code="POS", closing=10)
    session.commit()
    findings = check_c2_3(session, company.id, 2024)
    assert len(findings) == 2
    keys = {f.subject_key for f in findings}
    assert keys == {"NEG1", "NEG2"}
    assert all(f.severity == "critical" for f in findings)


# --- C2.4: Tồn cuối TP âm ---


def test_c2_4_no_fire_when_zero_or_positive(session, company):
    add_sp(session, company.id, product_code="POS", closing=10)
    add_sp(session, company.id, product_code="ZERO", closing=0)
    add_sp(session, company.id, product_code="TINY_NEG", closing=-0.005)  # under tolerance
    session.commit()
    assert check_c2_4(session, company.id, 2024) == []


def test_c2_4_fires_when_closing_negative(session, company):
    add_sp(session, company.id, product_code="NEG1", closing=-50, unit="PCE")
    add_sp(session, company.id, product_code="NEG2", closing=-0.5, unit="SET")
    add_sp(session, company.id, product_code="POS", closing=10)
    session.commit()
    findings = check_c2_4(session, company.id, 2024)
    assert len(findings) == 2
    keys = {f.subject_key for f in findings}
    assert keys == {"NEG1", "NEG2"}
    assert all(f.check_code == "C2.4" for f in findings)
    assert all(f.subject_type == "product_code" for f in findings)
    assert all(f.severity == "critical" for f in findings)
