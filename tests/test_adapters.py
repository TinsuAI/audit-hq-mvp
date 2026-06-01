"""Integration tests cho adapter — chạy trên dữ liệu thực HONG_AN 2024.

Skipped nếu thư mục data/ chưa được symlink (CI chưa có data).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.adapters import parse_bcct, parse_m15, parse_m15a, parse_m16

DATA_ROOT = Path(__file__).resolve().parent.parent / "data" / "HONG_AN" / "2024"

pytestmark = pytest.mark.skipif(
    not DATA_ROOT.exists(),
    reason=f"Dữ liệu thực không có sẵn ở {DATA_ROOT}",
)


def test_m15_hong_an_2024():
    f = DATA_ROOT / "BCQT" / "TT39_BaoCaoQuyetToan_NVL 2024.xlsx"
    res = parse_m15(f)
    assert res.header.tax_id == "5400273360"
    assert res.header.period_from is not None
    assert res.header.period_from.year == 2024
    assert len(res.rows) > 50
    first = res.rows[0]
    assert first.material_code
    assert first.unit
    assert all(r.material_code for r in res.rows)


def test_m15a_hong_an_2024():
    f = DATA_ROOT / "BCQT" / "TT39_BaoCaoQuyetToan_SP 2024.xlsx"
    res = parse_m15a(f)
    assert res.header.tax_id == "5400273360"
    assert len(res.rows) > 30
    # M15a expects positive exports for at least some products.
    assert any(r.export_qty > 0 for r in res.rows)


def test_m16_hong_an_2024_tt39_format():
    f = DATA_ROOT / "DINH_MUC" / "BCDM_TT39_HA_2024.xls"
    res = parse_m16(f)
    assert len(res.rows) > 100
    # Every row must have both codes filled in (parent-child forward-fill).
    assert all(r.product_code and r.material_code for r in res.rows)
    assert all(r.norm_qty > 0 for r in res.rows)
    # Cột Ghi chú (col9) được đọc; HONG_AN 2024 không đánh dấu xuất xứ nên đều None.
    assert all(r.note is None for r in res.rows)


def test_bcct_hong_an_2024():
    f = DATA_ROOT / "HANG_CHI_TIET" / "BaoCaoHangChiTiet XNK 2024.xls"
    res = parse_bcct(f)
    assert res.company_tax_id == "5400273360"
    assert len(res.rows) > 100
    customs_codes = {r.customs_code for r in res.rows}
    # SXXK: E31 nhập + E62 xuất phải có cả hai.
    assert "E31" in customs_codes
    assert "E62" in customs_codes
    sample = next(r for r in res.rows if r.customs_code == "E62")
    assert sample.item_code
    assert sample.hs_code
    assert sample.quantity is not None and sample.quantity > 0
