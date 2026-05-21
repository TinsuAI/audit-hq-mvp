"""Shared pytest fixtures."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.models import Company, DeclarationLine, NvlBalance, SpBalance


@pytest.fixture
def session() -> Session:
    """In-memory SQLite session — no migrations, schema from Base.metadata."""
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with SessionLocal() as s:
        yield s
        s.rollback()


@pytest.fixture
def company(session: Session) -> Company:
    c = Company(code="TEST_DN", tax_id="9999999999", name="Công ty Test", address="Hà Nội")
    session.add(c)
    session.commit()
    return c


def add_nvl(
    session: Session,
    company_id: int,
    *,
    material_code: str,
    unit: str = "PCE",
    opening: float = 0,
    imported: float = 0,
    reexport: float = 0,
    repurpose: float = 0,
    production_out: float = 0,
    other_out: float = 0,
    closing: float = 0,
    year: int = 2024,
) -> NvlBalance:
    row = NvlBalance(
        company_id=company_id,
        period_year=year,
        material_code=material_code,
        unit=unit,
        opening_qty=opening,
        import_qty=imported,
        reexport_qty=reexport,
        repurpose_qty=repurpose,
        production_out_qty=production_out,
        other_out_qty=other_out,
        closing_qty=closing,
    )
    session.add(row)
    return row


def add_sp(
    session: Session,
    company_id: int,
    *,
    product_code: str,
    unit: str = "PCE",
    opening: float = 0,
    intake: float = 0,
    repurpose: float = 0,
    export_qty: float = 0,
    other_out: float = 0,
    closing: float = 0,
    year: int = 2024,
) -> SpBalance:
    row = SpBalance(
        company_id=company_id,
        period_year=year,
        product_code=product_code,
        unit=unit,
        opening_qty=opening,
        intake_qty=intake,
        repurpose_qty=repurpose,
        export_qty=export_qty,
        other_out_qty=other_out,
        closing_qty=closing,
    )
    session.add(row)
    return row


def add_decl(
    session: Session,
    company_id: int,
    *,
    declaration_no: str,
    customs_code: str,
    item_code: str,
    quantity: float,
    unit: str = "PCE",
    hs_code: str = "00000000",
    year: int = 2024,
    declaration_date: date | None = None,
) -> DeclarationLine:
    row = DeclarationLine(
        company_id=company_id,
        period_year=year,
        declaration_no=declaration_no,
        declaration_date=declaration_date or date(year, 6, 15),
        customs_code=customs_code,
        item_code=item_code,
        hs_code=hs_code,
        quantity=quantity,
        unit=unit,
    )
    session.add(row)
    return row
