from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Finding(Base):
    """Tầng 2 — Phát hiện từ một check trên dữ liệu Tầng 1 của (company, year).

    Mọi finding phải truy nguồn được về Tầng 1 qua `evidence_refs`
    (list of {"table": str, "id": int} hoặc {"table": str, "filter": dict}).
    """

    __tablename__ = "findings"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    period_year: Mapped[int] = mapped_column(Integer, index=True)
    check_code: Mapped[str] = mapped_column(String(16), index=True)
    severity: Mapped[str] = mapped_column(String(16), index=True)  # critical | warning | info
    subject_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    book: Mapped[str | None] = mapped_column(String(32), nullable=True)
    subject_key: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    title: Mapped[str] = mapped_column(String(500))
    #: Giá trị tiền của chính chênh lệch này (VNĐ), để xếp hạng phát hiện. NULL =
    #: chưa quy ra tiền được (không có tờ khai để lấy đơn giá, hoặc check chưa quy).
    #: Khác 0: 0 là "đã quy, ra không đáng kể" — hai thứ không được xếp cùng chỗ.
    value_vnd: Mapped[float | None] = mapped_column(Float, nullable=True)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    evidence_refs: Mapped[list | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="new", index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.current_timestamp()
    )

    __table_args__ = (
        Index("ix_finding_company_year_code", "company_id", "period_year", "check_code"),
    )
