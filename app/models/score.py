"""Điểm rủi ro dữ liệu BCQT theo (DN, năm).

Tách khỏi `Company.risk_score` (vẫn giữ làm "best year score" cho ranking)
để có thể truy theo từng năm + lưu breakdown chi tiết cho UI debug.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CompanyYearScore(Base):
    __tablename__ = "company_year_scores"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id"), nullable=False, index=True,
    )
    period_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    score: Mapped[int] = mapped_column(Integer, nullable=False)  # 0-1000
    tier: Mapped[str] = mapped_column(String(64), nullable=False)
    breakdown: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp(),
    )

    __table_args__ = (
        UniqueConstraint("company_id", "period_year", name="uq_company_year_score"),
    )
