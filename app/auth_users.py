"""User authentication helpers — password hashing + lookup.

Hash format: `pbkdf2_sha256$<iterations>$<salt_b64>$<hash_b64>` (Django-compat).
PBKDF2-SHA256 600k iterations theo khuyến nghị OWASP 2023+ cho SHA-256.

Stdlib only — không add dep mới (bcrypt/argon2-cffi) cho MVP 1 instance.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import VALID_ROLES, User

_ALGO = "pbkdf2_sha256"
_ITERATIONS = 600_000
_SALT_BYTES = 16
_HASH_BYTES = 32  # SHA-256 output


def hash_password(password: str) -> str:
    """Tạo hash mới cho password. Salt random mỗi lần."""
    if not password:
        raise ValueError("Password không được trống")
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, _ITERATIONS, dklen=_HASH_BYTES
    )
    return f"{_ALGO}${_ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time compare. False nếu format sai hoặc password rỗng."""
    if not password or not stored:
        return False
    try:
        algo, iters_str, salt_b64, hash_b64 = stored.split("$", 3)
    except ValueError:
        return False
    if algo != _ALGO:
        return False
    try:
        iters = int(iters_str)
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
    except (ValueError, base64.binascii.Error):
        return False
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, iters, dklen=len(expected)
    )
    return hmac.compare_digest(digest, expected)


def get_user_by_username(db: Session, username: str) -> User | None:
    if not username:
        return None
    return db.scalar(select(User).where(User.username == username))


def authenticate(db: Session, username: str, password: str) -> User | None:
    """Lookup + verify. Trả về User nếu pass, None nếu fail (cùng error path để
    tránh username enumeration qua timing).
    """
    user = get_user_by_username(db, username)
    if user is None:
        # Vẫn chạy verify với hash dummy để timing đều nhau.
        verify_password(password, "pbkdf2_sha256$1$AAAA$AAAA")
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def create_user(
    db: Session, username: str, password: str, role: str, *, must_change: bool = False
) -> User:
    """Tạo user mới. Raise ValueError nếu username trùng hoặc role không hợp lệ.

    `must_change=True` (tài khoản admin tạo qua giao diện) → buộc đổi mật khẩu ở
    lần đăng nhập đầu. Seed admin bootstrap để False (operator tự đổi qua cảnh báo).
    """
    username = username.strip()
    if not username:
        raise ValueError("Username không được trống")
    if role not in VALID_ROLES:
        raise ValueError(f"Role không hợp lệ: {role!r} (chọn từ {sorted(VALID_ROLES)})")
    if get_user_by_username(db, username):
        raise ValueError(f"Username {username!r} đã tồn tại")
    user = User(
        username=username, password_hash=hash_password(password), role=role,
        must_change_password=must_change,
    )
    db.add(user)
    db.flush()
    return user


def set_password(db: Session, user: User, new_password: str, *, must_change: bool = False) -> None:
    """Đặt mật khẩu mới. `must_change=True` (admin đặt lại) → buộc user đổi lần sau;
    `False` (user tự đổi) → gỡ cờ buộc đổi."""
    user.password_hash = hash_password(new_password)
    user.must_change_password = must_change
    db.flush()


def count_admins(db: Session) -> int:
    from sqlalchemy import func
    return db.scalar(select(func.count()).select_from(User).where(User.role == "admin")) or 0


def seed_default_admin(db: Session, username: str, password: str) -> User | None:
    """Tạo admin đầu tiên nếu bảng users trống. Idempotent.

    Username/password truyền từ env (`AUTH_USER` / `AUTH_PASSWORD`) — không
    sửa hashed password nếu admin đã tồn tại sẵn.
    """
    from sqlalchemy import func
    if db.scalar(select(func.count()).select_from(User)) > 0:
        return None
    if not username or not password:
        raise ValueError(
            "Bảng users trống và chưa cấu hình AUTH_USER/AUTH_PASSWORD để seed admin"
        )
    user = create_user(db, username=username, password=password, role="admin")
    db.commit()
    return user
