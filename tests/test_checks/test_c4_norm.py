"""Unit tests cho Nhóm 4 — Định mức M16."""

from __future__ import annotations

from app.adapters.m16 import is_domestic_origin
from app.checks.c4_norm import check_c4_1, check_c4_3
from app.models import Norm
from tests.conftest import add_nvl, add_sp


def add_norm(
    session,
    company_id: int,
    *,
    product_code: str,
    material_code: str,
    norm_qty: float,
    note: str | None = None,
    year: int = 2024,
):
    n = Norm(
        company_id=company_id,
        period_year=year,
        product_code=product_code,
        material_code=material_code,
        norm_qty=norm_qty,
        note=note,
    )
    session.add(n)
    return n


# --- C4.1: NVL M16 không có nguồn ---


def test_c4_1_fires_when_no_m15(session, company):
    add_sp(session, company.id, product_code="TP", export_qty=100)
    add_norm(session, company.id, product_code="TP", material_code="GHOST", norm_qty=1.0)
    session.commit()
    findings = check_c4_1(session, company.id, 2024)
    assert len(findings) == 1
    assert findings[0].subject_key == "GHOST"
    assert findings[0].details["reason"] == "no_m15"


def test_c4_1_fires_when_m15_zero_source(session, company):
    add_nvl(session, company.id, material_code="ZERO", imported=0, opening=0)
    add_norm(session, company.id, product_code="TP", material_code="ZERO", norm_qty=1.0)
    session.commit()
    findings = check_c4_1(session, company.id, 2024)
    assert len(findings) == 1
    assert findings[0].details["reason"] == "zero_source"


def test_c4_1_no_fire_with_import(session, company):
    add_nvl(session, company.id, material_code="OK", imported=100)
    add_norm(session, company.id, product_code="TP", material_code="OK", norm_qty=1.0)
    session.commit()
    assert check_c4_1(session, company.id, 2024) == []


def test_c4_1_no_fire_with_opening(session, company):
    add_nvl(session, company.id, material_code="STK", imported=0, opening=50)
    add_norm(session, company.id, product_code="TP", material_code="STK", norm_qty=1.0)
    session.commit()
    assert check_c4_1(session, company.id, 2024) == []


def test_is_domestic_origin():
    assert is_domestic_origin("x")
    assert is_domestic_origin(" X ")
    assert not is_domestic_origin(None)
    assert not is_domestic_origin("")
    assert not is_domestic_origin("nhập khẩu")


def test_c4_1_skips_domestic_origin(session, company):
    # Mã xuất xứ trong nước (Ghi chú "x") không có nguồn nhập → KHÔNG flag.
    add_norm(session, company.id, product_code="TP", material_code="VN", norm_qty=1.0, note="x")
    session.commit()
    assert check_c4_1(session, company.id, 2024) == []


def test_c4_1_still_fires_for_imported_no_source(session, company):
    # Cùng tình huống nhưng không phải hàng nội địa → vẫn flag.
    add_norm(session, company.id, product_code="TP", material_code="NK", norm_qty=1.0, note=None)
    session.commit()
    findings = check_c4_1(session, company.id, 2024)
    assert len(findings) == 1
    assert findings[0].subject_key == "NK"


# --- C4.3: tiêu hao lý thuyết vượt xuất SX ---


def test_c4_3_no_fire_when_close(session, company):
    # theoretical = 1.0 * 100 = 100; actual = 100 → 0% lệch
    add_sp(session, company.id, product_code="TP", export_qty=100)
    add_norm(session, company.id, product_code="TP", material_code="X", norm_qty=1.0)
    add_nvl(session, company.id, material_code="X", imported=100, production_out=100)
    session.commit()
    assert check_c4_3(session, company.id, 2024) == []


def test_c4_3_warning_when_over_10pct(session, company):
    # theoretical = 1.0 * 100 = 100; actual = 90 → +11.1% lệch → warning (5-20%)
    add_sp(session, company.id, product_code="TP", export_qty=100)
    add_norm(session, company.id, product_code="TP", material_code="X", norm_qty=1.0)
    add_nvl(session, company.id, material_code="X", imported=100, production_out=90)
    session.commit()
    findings = check_c4_3(session, company.id, 2024)
    assert len(findings) == 1
    assert findings[0].severity == "warning"


def test_c4_3_critical_when_over_20pct(session, company):
    # theoretical = 2.0 * 100 = 200; actual = 100 → +100% lệch → critical
    add_sp(session, company.id, product_code="TP", export_qty=100)
    add_norm(session, company.id, product_code="TP", material_code="X", norm_qty=2.0)
    add_nvl(session, company.id, material_code="X", imported=200, production_out=100)
    session.commit()
    findings = check_c4_3(session, company.id, 2024)
    assert len(findings) == 1
    assert findings[0].severity == "critical"


def test_c4_3_critical_when_m15_has_no_production_out(session, company):
    # theoretical > 0 nhưng M15 không xuất SX gì cả → 100% lệch → critical
    add_sp(session, company.id, product_code="TP", export_qty=100)
    add_norm(session, company.id, product_code="TP", material_code="X", norm_qty=1.0)
    add_nvl(session, company.id, material_code="X", imported=100, production_out=0)
    session.commit()
    findings = check_c4_3(session, company.id, 2024)
    assert len(findings) == 1
    assert findings[0].severity == "critical"
