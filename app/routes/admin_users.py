"""Admin routes — quản lý tài khoản người dùng.

Chỉ admin được vào. Officer chỉ xem dữ liệu + dùng AI assistant.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import SessionUser, require_admin
from app.auth_users import count_admins, create_user, set_password
from app.database import get_db
from app.models import ROLE_ADMIN, VALID_ROLES, Company, User
from app.version import VERSION, version_string

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")
templates.env.globals["app_version_string"] = version_string()
templates.env.globals["app_version"] = VERSION

router = APIRouter(prefix="/admin/users")


@router.get("", response_class=HTMLResponse)
def users_list(
    request: Request,
    saved: str | None = None,
    error: str | None = None,
    user: SessionUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    users = db.scalars(select(User).order_by(User.role, User.username)).all()
    return templates.TemplateResponse(
        request,
        "admin_users.html",
        {
            "user": user,
            "users": users,
            "valid_roles": sorted(VALID_ROLES),
            "saved": saved,
            "error": error,
        },
    )


@router.post("/create", response_model=None)
def users_create(
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    user: SessionUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    try:
        create_user(db, username=username.strip(), password=password, role=role)
        db.commit()
    except ValueError as e:
        from urllib.parse import quote
        return RedirectResponse(f"/admin/users?error={quote(str(e))}", status_code=303)
    return RedirectResponse(f"/admin/users?saved={username.strip()}", status_code=303)


@router.post("/{user_id}/change-password", response_model=None)
def users_change_password(
    user_id: int,
    new_password: str = Form(...),
    user: SessionUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Người dùng không tồn tại")
    if len(new_password) < 8:
        from urllib.parse import quote
        return RedirectResponse(
            f"/admin/users?error={quote('Mật khẩu phải ít nhất 8 ký tự')}", status_code=303
        )
    set_password(db, target, new_password)
    db.commit()
    return RedirectResponse(f"/admin/users?saved=password-{target.username}", status_code=303)


@router.get("/{user_id}/scope", response_class=HTMLResponse)
def user_scope_form(
    user_id: int,
    request: Request,
    saved: str | None = None,
    user: SessionUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Trang phân công DN cho 1 officer — checkbox toàn bộ DN, tick = được phép."""
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Người dùng không tồn tại")
    companies = db.scalars(select(Company).order_by(Company.code)).all()
    assigned_ids = {c.id for c in target.companies}
    return templates.TemplateResponse(
        request,
        "admin_user_scope.html",
        {
            "user": user,
            "target": target,
            "companies": companies,
            "assigned_ids": assigned_ids,
            "is_admin_target": target.role == ROLE_ADMIN,
            "saved": saved,
        },
    )


@router.post("/{user_id}/scope", response_model=None)
def user_scope_save(
    user_id: int,
    company_ids: list[int] = Form(default=[]),
    user: SessionUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Lưu danh sách DN được phân công (thay toàn bộ — không tick = gỡ phân công)."""
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Người dùng không tồn tại")
    selected = set(company_ids)
    companies = (
        db.scalars(select(Company).where(Company.id.in_(selected))).all() if selected else []
    )
    target.companies = list(companies)
    db.commit()
    return RedirectResponse(f"/admin/users/{user_id}/scope?saved=1", status_code=303)


@router.post("/{user_id}/delete", response_model=None)
def users_delete(
    user_id: int,
    user: SessionUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Người dùng không tồn tại")
    if target.username == user.name:
        from urllib.parse import quote
        return RedirectResponse(
            f"/admin/users?error={quote('Không thể xóa tài khoản đang đăng nhập')}",
            status_code=303,
        )
    if target.role == "admin" and count_admins(db) <= 1:
        from urllib.parse import quote
        return RedirectResponse(
            "/admin/users?error="
            + quote("Phải có ít nhất 1 admin. Cấp quyền admin cho người dùng khác trước."),
            status_code=303,
        )
    db.delete(target)
    db.commit()
    return RedirectResponse(f"/admin/users?saved=deleted-{target.username}", status_code=303)
