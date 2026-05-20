from __future__ import annotations

from datetime import date

from sqlalchemy import Date, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DeclarationLine(Base):
    """Dòng hàng trên Báo cáo hàng chi tiết XNK (BCCT — xuất từ VNACCS/ECUS)."""

    __tablename__ = "declaration_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    period_year: Mapped[int] = mapped_column(Integer, index=True)
    declaration_no: Mapped[str] = mapped_column(String(32), index=True)
    declaration_date: Mapped[date | None] = mapped_column(Date, index=True, nullable=True)
    customs_code: Mapped[str | None] = mapped_column(String(8), index=True, nullable=True)
    line_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    item_code: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    item_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    hs_code: Mapped[str | None] = mapped_column(String(16), index=True, nullable=True)
    origin: Mapped[str | None] = mapped_column(String(64), nullable=True)
    quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    unit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    value_foreign: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    tax_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    partner: Mapped[str | None] = mapped_column(String(255), nullable=True)
    invoice_no: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_file: Mapped[str | None] = mapped_column(String(500), nullable=True)

    __table_args__ = (
        Index("ix_decl_company_year_code", "company_id", "period_year", "item_code"),
        Index("ix_decl_customs", "company_id", "period_year", "customs_code"),
    )
