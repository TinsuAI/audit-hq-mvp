"""User model — multi-user + role-based access.

Hiện hỗ trợ 2 role:
- `admin`: Trọng Tín / Tinsu — toàn quyền /admin/*, tạo DN, upload, cấu hình AI.
- `officer`: cán bộ Hải quan — chỉ xem dữ liệu + dùng AI assistant.

Password lưu dưới dạng `pbkdf2_sha256$iterations$salt_b64$hash_b64` (xem app/auth_users.py).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

ROLE_ADMIN = "admin"
ROLE_OFFICER = "officer"
VALID_ROLES = {ROLE_ADMIN, ROLE_OFFICER}


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default=ROLE_OFFICER)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.current_timestamp()
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    def __repr__(self) -> str:
        return f"<User {self.username} role={self.role}>"
