from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.database import Base


class CheckStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    DISABLED = "disabled"


class CheckDefinition(Base):
    """Check mở rộng do admin soạn từ ngôn ngữ tự nhiên (qua AI), lưu DB.

    Code prefix `X.*` phân biệt với built-in `C1.*` — `X` = Extended.
    Logic là SQL hoặc Python tự do (`kind` = 'sql' | 'python') chạy read-only
    trên dữ liệu Tầng 1, scope theo (company, year). Cột `spec` (JSON) giữ lại
    cho tương thích ngược (DSL cũ) — check mới dùng `sql_snippet`/`code_snippet`.
    Chỉ status=published mới chạy trong pipeline.

    Truy nguồn: `subject_table` + `subject_col` để tự dựng evidence_refs về Tầng 1.
    Scoring: `scope` (nvl/tp/m16) chọn mẫu số rate-based.
    """

    __tablename__ = "check_definitions"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # 'sql' | 'python'
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    group: Mapped[int] = mapped_column(Integer, nullable=False, default=99)
    default_severity: Mapped[str] = mapped_column(String(16), nullable=False, default="warning")
    spec: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    # --- Check SQL/Python (mới) ---
    # Scope mẫu số rate-based: 'nvl' | 'tp' | 'm16'.
    scope: Mapped[str | None] = mapped_column(String(8), nullable=True)
    # Truy nguồn: bảng + cột subject để dựng evidence_refs về Tầng 1.
    subject_table: Mapped[str | None] = mapped_column(String(32), nullable=True)
    subject_col: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sql_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    detail_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    code_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Vết soạn từ NL (audit + dynamic few-shot) ---
    nl_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    analysis: Mapped[str | None] = mapped_column(Text, nullable=True)
    plan: Mapped[list | None] = mapped_column(JSON, nullable=True)
    self_review: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=CheckStatus.DRAFT, index=True,
    )
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True, index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )


def next_check_code(session: Session) -> str:
    """Trả về code X.N kế tiếp chưa được dùng (atomic trong transaction)."""
    from sqlalchemy import func as sqlfunc

    max_row = session.execute(
        select(CheckDefinition.code).where(
            CheckDefinition.code.like("X.%")
        ).order_by(CheckDefinition.id.desc()).limit(1)
    ).scalar()

    if max_row is None:
        return "X.1"
    try:
        n = int(max_row.split(".")[1])
        return f"X.{n + 1}"
    except (IndexError, ValueError):
        # Fallback: count + 1
        count = session.scalar(
            select(sqlfunc.count()).select_from(CheckDefinition).where(
                CheckDefinition.code.like("X.%")
            )
        ) or 0
        return f"X.{count + 1}"
