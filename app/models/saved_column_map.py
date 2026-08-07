"""Map cột đã cán bộ xác nhận, lưu theo `(DN, slot, vân tay form)` (WS1, ADR #18).

Khi một file có vân tay form khớp dòng đã lưu của CHÍNH DN đó, các cột trong map
resolve `officer-confirmed` → `verified` (không hỏi lại). Vân tay CẤU TRÚC không
chứa mã DN nên tái dùng chéo NĂM trong cùng DN; keyed theo `company_id` nên DN khác
cùng shape KHÔNG kế thừa xác nhận.

Lưu TOÀN map (`field → chỉ số cột`) + evidence source mỗi cột lúc xác nhận + ai/khi
nào, để tái dựng đủ (không chỉ cột lệch).
"""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SavedColumnMap(Base):
    __tablename__ = "saved_column_maps"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False,
    )
    slot: Mapped[str] = mapped_column(String(8), nullable=False)
    form_signature: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    # JSON: field → chỉ số cột (0-indexed). Toàn map, không chỉ cột lệch.
    column_map: Mapped[str] = mapped_column(Text, nullable=False)
    # JSON: field → nguồn bằng chứng lúc xác nhận (header-matched/balance-checked/…).
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    # JSON list: trường cán bộ XÁC NHẬN không có trong file (#112). Lời của cán bộ,
    # không phải suy đoán của máy — và là thứ cho cảnh báo "thiếu trường bắt buộc"
    # một đường đóng thay vì nhắc mãi. Bất biến: giao với `column_map` luôn rỗng.
    # NULL = chưa ai xác nhận vắng trường nào (đúng nguyên trạng của hàng cũ).
    absent_fields: Mapped[str | None] = mapped_column(Text, nullable=True)
    confirmed_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True,
    )
    confirmed_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp(),
    )

    __table_args__ = (
        UniqueConstraint(
            "company_id", "slot", "form_signature", name="uq_saved_column_maps_key",
        ),
    )

    @property
    def column_map_obj(self) -> dict[str, int]:
        try:
            return json.loads(self.column_map) if self.column_map else {}
        except (ValueError, TypeError):
            return {}

    @property
    def absent_fields_obj(self) -> list[str]:
        try:
            value = json.loads(self.absent_fields) if self.absent_fields else []
        except (ValueError, TypeError):
            return []
        return [f for f in value if isinstance(f, str)] if isinstance(value, list) else []

    @property
    def evidence_obj(self) -> dict[str, str]:
        try:
            return json.loads(self.evidence) if self.evidence else {}
        except (ValueError, TypeError):
            return {}

    def __repr__(self) -> str:
        return (
            f"<SavedColumnMap {self.company_id}/{self.slot}/{self.form_signature[:8]}>"
        )
