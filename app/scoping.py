"""Phân quyền theo DN — một ranh giới chung cho UI lẫn AI.

Mô hình (pilot, 2 role):
- `admin`: thấy & thao tác MỌI DN → `allowed_*` trả về `None` (sentinel "không giới hạn").
- `officer`: chỉ DN được phân công (bảng `user_companies`).

Quy ước an toàn: DN ngoài phạm vi → **404** (không phải 403) để không lộ cả sự tồn
tại của DN. Dùng `get_company_or_404` ở mọi route theo `{code}`.
"""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.auth import SessionUser
from app.models import Company, User, user_companies


def allowed_company_ids(db: Session, user: SessionUser) -> set[int] | None:
    """Tập `company.id` user được phép. `None` = không giới hạn (admin)."""
    if user.is_admin:
        return None
    urow = db.scalar(select(User).where(User.username == user.name))
    if urow is None:
        return set()
    return {
        cid for (cid,) in db.execute(
            select(user_companies.c.company_id).where(user_companies.c.user_id == urow.id)
        ).all()
    }


def allowed_company_codes(db: Session, user: SessionUser) -> set[str] | None:
    """Tập mã DN user được phép. `None` = không giới hạn (admin)."""
    if user.is_admin:
        return None
    urow = db.scalar(select(User).where(User.username == user.name))
    if urow is None:
        return set()
    return {
        code for (code,) in db.execute(
            select(Company.code)
            .join(user_companies, user_companies.c.company_id == Company.id)
            .where(user_companies.c.user_id == urow.id)
        ).all()
    }


def can_access_company_id(db: Session, user: SessionUser, company_id: int) -> bool:
    """Officer có quyền trên `company_id` không? Admin luôn True."""
    if user.is_admin:
        return True
    urow = db.scalar(select(User).where(User.username == user.name))
    if urow is None:
        return False
    return bool(
        db.scalar(
            select(
                exists().where(
                    user_companies.c.user_id == urow.id,
                    user_companies.c.company_id == company_id,
                )
            )
        )
    )


def get_company_or_404(db: Session, ident: str, user: SessionUser) -> Company:
    """Resolve DN theo slug HOẶC code + enforce phạm vi. 404 nếu không tồn tại/ngoài phạm vi.

    URL người dùng dùng `slug` (có nghĩa); link nội bộ cũ/AI/jobs/log dùng `code`
    (DN_xxx) — chấp nhận cả hai để không gãy. Ưu tiên khớp slug.
    """
    company = db.scalar(select(Company).where(Company.slug == ident))
    if company is None:
        company = db.scalar(select(Company).where(Company.code == ident))
    if company is None:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy DN {ident}")
    if not can_access_company_id(db, user, company.id):
        # 404 cố ý — không tiết lộ DN ngoài phạm vi có tồn tại.
        raise HTTPException(status_code=404, detail=f"Không tìm thấy DN {ident}")
    return company
