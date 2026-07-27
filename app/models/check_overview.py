"""Tổng quan AI CÓ TRUY NGUỒN cho một check của (DN, năm) — WS3.

Overwrite-upsert MỘT dòng mỗi `(company_id, period_year, check_code)` (KHÔNG version
history — consumer duy nhất là "overview hiện tại + có stale không"). Dòng TỰ mang
telemetry (model/tokens/cost/latency) → mỗi overview tự truy nguồn chi phí mà không
cần bảng history hay `ai_conversation` giả.

Staleness: overview cũ khi `check_runs.ran_at > based_on_run_at` (check chạy lại)
HOẶC `CompanyPeriod.data_version > based_on_data_version` (dữ liệu nạp lại). Xem ADR
#18 Revision — WS3.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CheckOverview(Base):
    __tablename__ = "check_overviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id"), nullable=False, index=True,
    )
    period_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    check_code: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    generated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp(),
    )
    # Snapshot trạng thái nền lúc sinh — so với hiện tại để phát hiện stale.
    based_on_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    based_on_data_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
    )

    # Trạng thái sinh (ADR #21 mục 6): dòng tồn tại NGAY khi cán bộ bấm, mang
    # `running` + job đang chạy, rồi thành `done` hoặc `failed` kèm lỗi.
    STATUS_RUNNING = "running"
    STATUS_DONE = "done"
    STATUS_FAILED = "failed"

    # Bảng số liệu TÍNH ĐƯỢC, đóng băng theo mốc sinh (ADR #21 mục 1-2, 8).
    # Hiện NGAY khi cán bộ bấm — không phải chờ LLM.
    aggregate_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Nhận định do LLM viết, bốn mục cố định (ADR #21 mục 3). NULL = JSON hỏng
    # → template xuống cấp về `content` dạng văn xuôi thô.
    sections_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Có con số trong nhận định không khớp chuỗi nào của bảng số liệu (mục 4).
    needs_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    unsupported_numbers: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(String(16), nullable=False, default=STATUS_DONE)
    job_id: Mapped[int | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Telemetry — gương AiMessage (models/ai.py). Overview là gọi LLM tính tiền.
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tokens_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "company_id", "period_year", "check_code", name="uq_check_overview"
        ),
    )
