"""Admin — nhật ký truy cập (egress dữ liệu + hành động trên DN). Chỉ admin."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import ACTION_LABEL_VI
from app.auth import SessionUser, require_admin
from app.database import get_db
from app.models import AccessEvent
from app.version import VERSION, version_string

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")
templates.env.globals["app_version_string"] = version_string()
templates.env.globals["app_version"] = VERSION
templates.env.globals["ACTION_LABEL_VI"] = ACTION_LABEL_VI

router = APIRouter(prefix="/admin/audit")

_LIMIT = 200


@router.get("", response_class=HTMLResponse)
def audit_list(
    request: Request,
    company: str | None = Query(default=None),
    action: str | None = Query(default=None),
    user: SessionUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    stmt = select(AccessEvent).order_by(AccessEvent.id.desc())
    if company:
        stmt = stmt.where(AccessEvent.company_code == company)
    if action:
        stmt = stmt.where(AccessEvent.action == action)
    events = db.scalars(stmt.limit(_LIMIT)).all()
    return templates.TemplateResponse(
        request,
        "admin_audit.html",
        {
            "user": user,
            "events": events,
            "limit": _LIMIT,
            "company": company or "",
            "action": action or "",
            "action_labels": ACTION_LABEL_VI,
        },
    )
