from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Company, CompanyPeriod


def test_stores_window_and_manual_flag(session, company: Company):
    session.add(
        CompanyPeriod(
            company_id=company.id,
            period_year=2024,
            period_from=date(2024, 4, 1),
            period_to=date(2025, 3, 31),
            is_manual=True,
        )
    )
    session.commit()

    row = (
        session.query(CompanyPeriod)
        .filter_by(company_id=company.id, period_year=2024)
        .one()
    )
    assert row.period_from == date(2024, 4, 1)
    assert row.period_to == date(2025, 3, 31)
    assert row.is_manual is True


def test_is_manual_defaults_false(session, company: Company):
    session.add(
        CompanyPeriod(
            company_id=company.id,
            period_year=2024,
            period_from=date(2024, 1, 1),
            period_to=date(2024, 12, 31),
        )
    )
    session.commit()

    row = (
        session.query(CompanyPeriod)
        .filter_by(company_id=company.id, period_year=2024)
        .one()
    )
    assert row.is_manual is False


def test_unique_company_year(session, company: Company):
    session.add(CompanyPeriod(company_id=company.id, period_year=2024))
    session.commit()

    session.add(CompanyPeriod(company_id=company.id, period_year=2024))
    with pytest.raises(IntegrityError):
        session.commit()
