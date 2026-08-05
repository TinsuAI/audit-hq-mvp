"""Route `/danh-muc-kiem-tra` — hiển thị toàn bộ 50 kiểm tra theo §4 đề án.

Đối lập với `/admin/checks` (quản lý check dynamic + xem 16 built-in đã chạy),
trang này là view-only public cho cán bộ HQ biết catalog tổng thể: cái nào
đã MVP, cái nào WIP, cái nào chờ điều kiện bổ sung.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.auth import SessionUser, require_user
from app.catalog_full import (
    GROUP_NAMES,
    SEVERITY_ICON,
    STATUS_ICON,
    STATUS_LABEL,
    grouped_by_phase,
    summary_counts,
)
from app.version import VERSION, version_string

router = APIRouter()

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")
templates.env.globals["app_version"] = VERSION
templates.env.globals["app_version_string"] = version_string()


@router.get("/danh-muc-kiem-tra", response_class=HTMLResponse)
def catalog_index(
    request: Request,
    user: SessionUser = Depends(require_user),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "catalog_full.html",
        {
            "user": user,
            "counts": summary_counts(),
            "phases": grouped_by_phase(),
            "group_names": GROUP_NAMES,
            "status_label": STATUS_LABEL,
            "status_icon": STATUS_ICON,
            "severity_icon": SEVERITY_ICON,
        },
    )
