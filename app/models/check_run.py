"""Mốc lần chạy MỚI NHẤT của một check cho (DN, năm) — nền staleness (WS3).

Latest-upsert MỘT dòng mỗi `(company_id, period_year, check_code)`. Ghi TRONG
`run_checks()` cho MỌI check đã chạy, kể cả 0 finding — nên KHÔNG suy được từ
`findings.created_at` (check ra 0 finding thì không có dòng finding). Lịch sử LẦN
CHẠY đã có ở bảng `jobs`; bảng này chỉ giữ trạng thái mới nhất.

Consumer duy nhất: staleness của overview (`check_overviews`). Xem ADR #18
Revision — WS3.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CheckRun(Base):
    __tablename__ = "check_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id"), nullable=False, index=True,
    )
    period_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    check_code: Mapped[str] = mapped_column(String(32), nullable=False)
    # ran_at ghi bằng datetime Python (naive UTC) mỗi upsert — KHÔNG server_default,
    # vì overview so `check_runs.ran_at > based_on_run_at` cần cùng một đồng hồ.
    ran_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    finding_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 'ok' | 'error' | 'not_evaluable'. `not_evaluable` = check không kết luận vì
    # thiếu đầu vào bắt buộc; mã đó bị loại khỏi điểm rủi ro (cả cộng điểm lẫn trần).
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ok")
    # Lý do đi kèm `not_evaluable` (hiện trên UI) hoặc `error` (thông điệp lỗi).
    # NULL khi status = 'ok'.
    status_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Phiên bản dữ liệu (CompanyPeriod.data_version) mà lần chạy này đọc — provenance.
    data_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint(
            "company_id", "period_year", "check_code", name="uq_check_run"
        ),
    )
