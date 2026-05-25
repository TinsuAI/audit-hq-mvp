"""Session-based authentication.

Cookie chứa {u: username, r: role}. Role lưu vào cookie tại login để tránh DB
hit mỗi request — admin đổi role trong DB → user phải re-login để áp dụng.

Trước Day 7 backlog: chỉ 1 cookie session global `auth_user/auth_password` env.
Sau: multi-user (xem app/auth_users.py + bảng users).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from fastapi import Depends, HTTPException, Request, status
from itsdangerous import BadSignature, URLSafeSerializer
from sqlalchemy.orm import Session

from app.auth_users import authenticate
from app.models import ROLE_ADMIN, ROLE_OFFICER
from app.settings import settings

_SESSION_KEY = "ahq_session"
_signer = URLSafeSerializer(settings.session_secret, salt="ahq-auth")


@dataclass(frozen=True)
class SessionUser:
    """Lightweight current-user object đính kèm vào request."""

    name: str
    role: str

    def __str__(self) -> str:  # template `{{ user }}` render tên cho thân thiện
        return self.name

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN

    @property
    def is_officer(self) -> bool:
        return self.role == ROLE_OFFICER


def make_session_cookie(user: SessionUser) -> str:
    return _signer.dumps({"u": user.name, "r": user.role})


def read_session(request: Request) -> SessionUser | None:
    raw = request.cookies.get(_SESSION_KEY)
    if not raw:
        return None
    try:
        data = _signer.loads(raw)
    except BadSignature:
        return None
    name = data.get("u")
    role = data.get("r") or ROLE_OFFICER  # fallback an toàn cho cookie cũ
    if not name:
        return None
    return SessionUser(name=name, role=role)


def login_with_credentials(db: Session, username: str, password: str) -> SessionUser | None:
    """Login flow — DB lookup, verify hash, cập nhật last_login_at."""
    user = authenticate(db, username, password)
    if user is None:
        return None
    user.last_login_at = datetime.utcnow()
    db.commit()
    return SessionUser(name=user.username, role=user.role)


def require_user(request: Request) -> SessionUser:
    user = read_session(request)
    if user is None:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"})
    return user


def require_admin(user: SessionUser = Depends(require_user)) -> SessionUser:
    """Dùng cho route /admin/*. 403 nếu không phải admin (KHÔNG redirect — đã login)."""
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Chức năng này chỉ dành cho quản trị viên.",
        )
    return user


SESSION_COOKIE_NAME = _SESSION_KEY
