"""Async job queue — bảng `jobs` lưu công việc chạy nền.

Worker thread (xem app/jobs/worker.py) poll bảng này, claim row `queued`,
chạy handler theo `kind`, ghi `result` hoặc `error`. UI poll trạng thái
qua `/jobs/{id}` và badge `/jobs/unread.json`.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class JobKind(StrEnum):
    RUN_CHECKS = "run_checks"
    INGEST = "ingest"
    INGEST_AND_RUN = "ingest_and_run"
    BATCH_RUN = "batch_run"
    AI_OVERVIEW = "ai_overview"
    AI_OVERVIEW_BATCH = "ai_overview_batch"


# Job gọi LLM. Worker kiểm tra LOẠI TRỪ nhóm này, worker AI CHỈ nhận nhóm này —
# nhờ đó hàng đợi kiểm tra không bao giờ phải chờ một lời gọi LLM (ADR #21 mục 5).
AI_JOB_KINDS: frozenset[str] = frozenset(
    {JobKind.AI_OVERVIEW.value, JobKind.AI_OVERVIEW_BATCH.value}
)


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=JobStatus.QUEUED.value, index=True,
    )
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id"), nullable=True, index=True,
    )
    period_year: Mapped[int | None] = mapped_column(Integer, nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp(),
    )
    # Lúc cán bộ thấy kết quả. Mở `/jobs/{id}` là một đường; với job `ingest` còn
    # đường thứ hai là kết quả in ngay tại dòng kỳ — xem `ingest_status.mark_seen`.
    viewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_jobs_status_created_at", "status", "created_at"),
        Index("ix_jobs_created_by_status", "created_by", "status"),
    )
