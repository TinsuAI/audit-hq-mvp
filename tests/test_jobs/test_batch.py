"""Test find_years_with_data + run_batch_handler."""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.jobs.handlers import find_years_with_data, run_batch_handler
from app.models import Company, CompanyYearScore, DeclarationLine, NvlBalance, SpBalance


def _company(session: Session, code: str = "DN_B") -> int:
    c = Company(code=code, tax_id="1", name=code)
    session.add(c)
    session.commit()
    return c.id


def test_find_years_returns_empty_when_no_data(session: Session) -> None:
    cid = _company(session)
    assert find_years_with_data(session, cid) == []


def test_find_years_unions_all_sources(session: Session) -> None:
    cid = _company(session)
    session.add_all([
        NvlBalance(company_id=cid, period_year=2022, material_code="A", unit="KG"),
        SpBalance(company_id=cid, period_year=2023, product_code="P", unit="PCE"),
        DeclarationLine(
            company_id=cid, period_year=2024, declaration_no="1",
            declaration_date=date(2024, 1, 1), customs_code="E31",
            item_code="A", hs_code="1", quantity=1, unit="KG",
        ),
        # Trùng năm 2022 từ source khác — vẫn distinct.
        SpBalance(company_id=cid, period_year=2022, product_code="P2", unit="PCE"),
    ])
    session.commit()
    years = find_years_with_data(session, cid)
    assert years == [2022, 2023, 2024]  # sorted ascending


def test_find_years_only_for_target_company(session: Session) -> None:
    cid_a = _company(session, "DN_A")
    cid_b = _company(session, "DN_B")
    session.add_all([
        NvlBalance(company_id=cid_a, period_year=2022, material_code="X", unit="KG"),
        NvlBalance(company_id=cid_b, period_year=2024, material_code="Y", unit="KG"),
    ])
    session.commit()
    assert find_years_with_data(session, cid_a) == [2022]
    assert find_years_with_data(session, cid_b) == [2024]


# --- run_batch_handler ---


def test_batch_handler_returns_empty_when_no_data(session: Session) -> None:
    _company(session, "EMPTY")
    result = run_batch_handler({"company_code": "EMPTY"}, session)
    assert result["years_processed"] == []
    assert result["total_findings"] == 0
    assert result["risk_score"] == 0


def test_batch_handler_loops_all_years_and_stores_scores(session: Session) -> None:
    cid = _company(session, "DN_BAT")
    # Seed dữ liệu 2 năm. Mỗi năm có 1 mã NVL gây cân bằng lỗi (C2.1).
    for year in (2023, 2024):
        session.add(NvlBalance(
            company_id=cid, period_year=year, material_code=f"M{year}",
            unit="KG", opening_qty=0, import_qty=100, closing_qty=999,  # lệch lớn
        ))
    session.commit()

    result = run_batch_handler({"company_code": "DN_BAT"}, session)
    assert result["years_processed"] == [2023, 2024]
    assert result["total_findings"] > 0
    assert 2023 in result["per_year"]
    assert 2024 in result["per_year"]

    # CompanyYearScore row tồn tại cho cả 2 năm.
    from sqlalchemy import select as _select
    rows = session.scalars(
        _select(CompanyYearScore).where(CompanyYearScore.company_id == cid)
    ).all()
    years_in_score = {r.period_year for r in rows}
    assert years_in_score == {2023, 2024}


def test_batch_handler_raises_on_missing_company(session: Session) -> None:
    import pytest
    with pytest.raises(ValueError, match="Không tìm thấy DN"):
        run_batch_handler({"company_code": "NOPE"}, session)
