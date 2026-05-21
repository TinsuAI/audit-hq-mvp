"""Đơn vị tính (UOM) — chuẩn hoá để giảm false-positive cho C3.3.

Hai bảng:
- `uom_canonical`: 1 dòng/đơn vị chuẩn (code, family, base_factor, tên VN).
  Family group các đơn vị cùng kiểu đo (length, mass, count...).
  base_factor = hệ số quy đổi về đơn vị gốc trong family (vd 1m = 1.0, 1cm = 0.01).
- `uom_alias`: many-to-1 → canonical. Mỗi alias là một biến thể text user nhập
  (vd "METRES" → MTR, "Chiếc" → PCE).

Equivalent:
- 2 đơn vị cùng canonical → identical (skip C3.3).
- 2 đơn vị khác canonical NHƯNG cùng family → convertible (C3.3 → INFO).
- 2 đơn vị khác family hoàn toàn → mismatch thực (C3.3 → CRITICAL).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UomCanonical(Base):
    """Đơn vị chuẩn — vd MTR (length, base 1.0), CM (length, 0.01)."""

    __tablename__ = "uom_canonical"

    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    family: Mapped[str] = mapped_column(String(32), index=True)
    base_factor: Mapped[float] = mapped_column(Float, default=1.0)
    name_vi: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp()
    )

    def __repr__(self) -> str:
        return f"<UomCanonical {self.code} family={self.family} base={self.base_factor}>"


class UomAlias(Base):
    """Mapping text raw (từ Excel) → canonical code."""

    __tablename__ = "uom_aliases"

    id: Mapped[int] = mapped_column(primary_key=True)
    alias: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    canonical_code: Mapped[str] = mapped_column(ForeignKey("uom_canonical.code"), index=True)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp()
    )

    __table_args__ = (
        Index("ix_uom_alias_canonical", "canonical_code"),
    )
