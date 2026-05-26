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
    """Check động do admin tạo qua DSL khai báo, lưu DB.

    Code prefix `X.*` phân biệt với built-in `C1.*` — `X` = Extended.
    Spec JSON định nghĩa logic theo 1 trong 5 kind DSL.
    Chỉ status=published mới chạy trong pipeline.
    """

    __tablename__ = "check_definitions"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    group: Mapped[int] = mapped_column(Integer, nullable=False, default=99)
    default_severity: Mapped[str] = mapped_column(String(16), nullable=False, default="warning")
    spec: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
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
