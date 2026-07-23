from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CompanyPeriod(Base):
    """Kỳ báo cáo (period_from, period_to) theo (company, period_year).

    Mặc định suy tự động lúc ingest (tiêu đề file → dương lịch). `is_manual=True`
    khi cán bộ sửa tay — re-ingest phải TÔN TRỌNG, không ghi đè bằng header/default.
    `period_year` vẫn là nhãn kỳ / khoá join (ADR #13); bảng này chỉ mang cửa sổ ngày.
    """

    __tablename__ = "company_periods"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    period_year: Mapped[int] = mapped_column(Integer, index=True)
    period_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_manual: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        UniqueConstraint("company_id", "period_year", name="uq_company_period"),
    )
