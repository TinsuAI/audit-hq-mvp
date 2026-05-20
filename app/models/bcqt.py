from __future__ import annotations

from sqlalchemy import Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class NvlBalance(Base):
    """Mẫu 15 — Cân đối nguyên vật liệu (BCQT NVL)."""

    __tablename__ = "nvl_balances"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    period_year: Mapped[int] = mapped_column(Integer, index=True)
    row_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    material_code: Mapped[str] = mapped_column(String(64), index=True)
    material_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    opening_qty: Mapped[float] = mapped_column(Float, default=0.0)
    import_qty: Mapped[float] = mapped_column(Float, default=0.0)
    reexport_qty: Mapped[float] = mapped_column(Float, default=0.0)
    repurpose_qty: Mapped[float] = mapped_column(Float, default=0.0)
    production_out_qty: Mapped[float] = mapped_column(Float, default=0.0)
    other_out_qty: Mapped[float] = mapped_column(Float, default=0.0)
    closing_qty: Mapped[float] = mapped_column(Float, default=0.0)
    source_file: Mapped[str | None] = mapped_column(String(500), nullable=True)

    __table_args__ = (
        Index("ix_nvl_company_year_code", "company_id", "period_year", "material_code"),
    )


class SpBalance(Base):
    """Mẫu 15a — Cân đối thành phẩm (BCQT SP)."""

    __tablename__ = "sp_balances"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    period_year: Mapped[int] = mapped_column(Integer, index=True)
    row_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    product_code: Mapped[str] = mapped_column(String(64), index=True)
    product_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    opening_qty: Mapped[float] = mapped_column(Float, default=0.0)
    intake_qty: Mapped[float] = mapped_column(Float, default=0.0)
    repurpose_qty: Mapped[float] = mapped_column(Float, default=0.0)
    export_qty: Mapped[float] = mapped_column(Float, default=0.0)
    other_out_qty: Mapped[float] = mapped_column(Float, default=0.0)
    closing_qty: Mapped[float] = mapped_column(Float, default=0.0)
    source_file: Mapped[str | None] = mapped_column(String(500), nullable=True)

    __table_args__ = (
        Index("ix_sp_company_year_code", "company_id", "period_year", "product_code"),
    )


class Norm(Base):
    """Mẫu 16 — Định mức thực tế sản xuất."""

    __tablename__ = "norms"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    period_year: Mapped[int] = mapped_column(Integer, index=True)
    product_code: Mapped[str] = mapped_column(String(64), index=True)
    product_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    product_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    material_code: Mapped[str] = mapped_column(String(64), index=True)
    material_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    material_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    norm_qty: Mapped[float] = mapped_column(Float, default=0.0)
    source_file: Mapped[str | None] = mapped_column(String(500), nullable=True)

    __table_args__ = (
        Index("ix_norm_company_year_pair", "company_id", "period_year", "product_code", "material_code"),
    )
