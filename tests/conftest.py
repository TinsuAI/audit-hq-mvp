"""Shared pytest fixtures."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base
from app.database import engine as _default_engine
from app.models import (
    Company,
    DeclarationLine,
    Norm,
    NvlBalance,
    SpBalance,
    UomAlias,
    UomCanonical,
)


@pytest.fixture(scope="session", autouse=True)
def _ensure_default_schema():
    """Đảm bảo default engine có đủ schema cho test nào đụng default DB.

    Pre-existing tests (vd test_spec_gen) gọi code path đọc bảng `ai_settings`
    nhưng không setup DB → fail trên CI runner với fresh sqlite. create_all
    idempotent, không ghi đè data nếu file đã có.
    """
    import app.models  # noqa: F401  load all models metadata trước create_all
    Base.metadata.create_all(_default_engine)


@pytest.fixture
def session() -> Session:
    """In-memory SQLite session — schema từ Base.metadata + seed minimum UOM."""
    from app.checks.uom import invalidate_cache

    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with SessionLocal() as s:
        # Seed UOM cơ bản để C3.3 tests work without hardcoded dict.
        # Flush canonical trước aliases vì FK constraint enabled (PRAGMA fk=ON).
        s.add_all([
            UomCanonical(code="MTR", family="length", base_factor=1.0),
            UomCanonical(code="CMT", family="length", base_factor=0.01),
            UomCanonical(code="KGM", family="mass", base_factor=1.0),
            UomCanonical(code="GRM", family="mass", base_factor=0.001),
            UomCanonical(code="PCE", family="count", base_factor=1.0),
        ])
        s.flush()
        s.add_all([
            UomAlias(alias="MTR", canonical_code="MTR"),
            UomAlias(alias="METRES", canonical_code="MTR"),
            UomAlias(alias="M", canonical_code="MTR"),
            UomAlias(alias="CM", canonical_code="CMT"),
            UomAlias(alias="KG", canonical_code="KGM"),
            UomAlias(alias="KGM", canonical_code="KGM"),
            UomAlias(alias="GAM", canonical_code="GRM"),
            UomAlias(alias="PCE", canonical_code="PCE"),
            UomAlias(alias="PIECES", canonical_code="PCE"),
        ])
        s.commit()
        invalidate_cache()
        yield s
        s.rollback()
        invalidate_cache()


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
    book: str | None = None,
    year: int = 2024,
) -> NvlBalance:
    row = NvlBalance(
        company_id=company_id,
        period_year=year,
        book=book,
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
    book: str | None = None,
    year: int = 2024,
) -> SpBalance:
    row = SpBalance(
        company_id=company_id,
        period_year=year,
        book=book,
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


def add_norm(
    session: Session,
    company_id: int,
    *,
    product_code: str,
    material_code: str,
    norm_qty: float,
    material_unit: str | None = None,
    note: str | None = None,
    book: str | None = None,
    year: int = 2024,
) -> Norm:
    row = Norm(
        company_id=company_id,
        period_year=year,
        book=book,
        product_code=product_code,
        material_code=material_code,
        material_unit=material_unit,
        norm_qty=norm_qty,
        note=note,
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
    value_total: float | None = None,
    unit_price: float | None = None,
    currency: str | None = None,
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
        # `value_total` là trị giá VNĐ của dòng tờ khai (đã quy đổi), `unit_price` là
        # đơn giá nguyên tệ — hai cột khác hệ, đừng suy cột này ra cột kia.
        value_total=value_total,
        unit_price=unit_price,
        currency=currency,
    )
    session.add(row)
    return row
