"""Cấu hình ứng dụng — key/value JSON.

Tách biệt với `ai_settings` (chỉ dành cho AI). Dùng cho mọi config admin
chỉnh được runtime: ngưỡng hạng rủi ro, các giới hạn nghiệp vụ, v.v.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    # JSON-serialized.
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    updated_by: Mapped[str] = mapped_column(String(64), nullable=False, default="system")

    def __repr__(self) -> str:
        return f"<AppSetting {self.key}>"
