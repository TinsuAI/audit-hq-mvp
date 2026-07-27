"""AI assistant — settings + audit log.

3 bảng:
- `ai_settings`: key-value cho cấu hình runtime (base_url, api_key, model...).
  Value lưu JSON-serialized; helper layer dispatch theo key registry.
- `ai_conversations`: 1 dòng / cuộc trò chuyện. Liên kết với 1 user.
- `ai_messages`: từng turn (user / assistant / tool). Audit + cost tracking.

Settings persist ở DB để admin sửa qua /admin/ai mà không cần redeploy. Env vars
chỉ là default lần đầu seed (xem app/ai/config.py:seed_defaults).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AiSetting(Base):
    """Cấu hình AI assistant — 1 dòng / key."""

    __tablename__ = "ai_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    # JSON-serialized. Bool/int/float/dict đều stringify rồi parse lại khi read.
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    updated_by: Mapped[str] = mapped_column(String(64), nullable=False, default="system")

    def __repr__(self) -> str:
        return f"<AiSetting {self.key}>"


class AiConversation(Base):
    """Cuộc trò chuyện giữa 1 user và AI — gắn TỐI ĐA 1 doanh nghiệp (ADR #20)."""

    __tablename__ = "ai_conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    user: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp(), index=True
    )
    # URL trang user đang xem khi mở conversation lần đầu — giúp admin debug context.
    page_url_seed: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # AI tự đặt sau ~3 turn để admin nhìn vào list hiểu nội dung.
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # DN gắn với cuộc — nhãn LƯU, không suy lúc đọc (ADR #20). NULL = chưa gắn.
    # DN bị xoá → SET NULL: cuộc vẫn đọc được, chỉ mất nhãn.
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        Index("ix_ai_conversations_user_started", "user", "started_at"),
        Index("ix_ai_conversations_user_company_started", "user", "company_id", "started_at"),
    )


class AiUsage(Base):
    """Sổ chi phí AI — APPEND-ONLY, một dòng mỗi lời gọi LLM tính tiền (ADR #21).

    Tồn tại vì trần ngày cần đếm ĐỦ mọi loại lời gọi. Trước đó trần chỉ cộng
    `ai_messages.cost_usd`, còn chi phí sinh tổng quan nằm trên `check_overviews`
    — mà bảng đó upsert MỘT dòng mỗi (DN, năm, mã kiểm tra), nên sinh lại ba lần
    trong ngày chỉ còn chi phí lần cuối: đếm thiếu đúng lúc chi tiêu cao nhất.

    Telemetry trên `ai_messages`/`check_overviews` giữ nguyên (chi phí của chính
    dòng đó). Sổ này là thứ LƯU + CHẶN, không phải thứ hiển thị: nơi duy nhất
    đọc ra tiền vẫn là `/admin/ai` sau cờ `show_cost`.
    """

    __tablename__ = "ai_usage"

    KIND_CHAT = "chat"
    KIND_OVERVIEW = "overview"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # chat | overview
    # Tham chiếu tới thứ sinh ra chi phí: `conv:{id}` hoặc `overview:{dn}:{năm}:{mã}`.
    ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tokens_in: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    user: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp(), index=True
    )

    __table_args__ = (
        Index("ix_ai_usage_created_kind", "created_at", "kind"),
    )


class AiMessage(Base):
    """1 turn trong conversation. Role: user / assistant / tool."""

    __tablename__ = "ai_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("ai_conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # user|assistant|tool
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # Tool-related fields — null cho role user/assistant không gọi tool.
    tool_call_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tool_args_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Metadata cho assistant turn.
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tokens_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp(), index=True
    )
