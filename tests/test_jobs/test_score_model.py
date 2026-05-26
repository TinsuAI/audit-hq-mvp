"""Schema + unique constraint cho company_year_scores."""

from __future__ import annotations

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Company, CompanyYearScore


def test_company_year_score_schema(session: Session) -> None:
    inspector = inspect(session.bind)
    assert "company_year_scores" in inspector.get_table_names()
    cols = {c["name"] for c in inspector.get_columns("company_year_scores")}
    assert cols >= {
        "id", "company_id", "period_year", "score", "tier",
        "breakdown", "computed_at",
    }


def test_company_year_score_unique_per_company_year(session: Session) -> None:
    c = Company(code="DN_T", tax_id="1", name="T")
    session.add(c)
    session.commit()

    session.add(CompanyYearScore(
        company_id=c.id, period_year=2024, score=120, tier="Có chênh lệch nhỏ", breakdown={},
    ))
    session.commit()

    session.add(CompanyYearScore(
        company_id=c.id, period_year=2024, score=130, tier="Có chênh lệch nhỏ", breakdown={},
    ))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_company_year_score_roundtrip(session: Session) -> None:
    c = Company(code="DN_T2", tax_id="2", name="T2")
    session.add(c)
    session.commit()

    s = CompanyYearScore(
        company_id=c.id, period_year=2024, score=450,
        tier="Cần rà soát",
        breakdown={"rule_scores": {"C1.1": 2.5, "C2.1": 4.0}, "combo_bonus": 0, "raw": 6.5},
    )
    session.add(s)
    session.commit()

    fetched = session.scalar(
        select(CompanyYearScore).where(
            CompanyYearScore.company_id == c.id,
            CompanyYearScore.period_year == 2024,
        )
    )
    assert fetched is not None
    assert fetched.score == 450
    assert fetched.tier == "Cần rà soát"
    assert fetched.breakdown["rule_scores"]["C1.1"] == 2.5
