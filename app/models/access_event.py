"""Nhật ký truy cập — ghi lại egress dữ liệu + hành động trên DN.

Phục vụ quản trị dữ liệu thật (ai tải/xuất/chạy kiểm tra DN nào, lúc nào). KHÔNG
ghi mọi lượt xem trang (nhiễu) — chỉ các sự kiện nhạy cảm (xem `app/audit.py`).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AccessEvent(Base):
    __tablename__ = "access_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), index=True)
    action: Mapped[str] = mapped_column(String(32), index=True)  # download | export | run_checks…
    company_code: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp(), index=True
    )

    def __repr__(self) -> str:
        return f"<AccessEvent {self.username} {self.action} {self.company_code}>"
