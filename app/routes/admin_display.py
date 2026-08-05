"""Trang `/admin/hien-thi` — quy ước hiển thị số trên toàn hệ thống."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.app_settings import (
    DEFAULT_NUMBER_FORMAT,
    NUMBER_FORMAT_LABELS,
    ValidationError,
    get_number_format,
    set_number_format,
)
from app.auth import SessionUser, require_admin
from app.database import get_db
from app.formatting import fmt_money, fmt_pct, fmt_qty
from app.version import VERSION, version_string

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")
templates.env.globals["app_version"] = VERSION
templates.env.globals["app_version_string"] = version_string()

router = APIRouter(prefix="/admin/hien-thi")

# Ba mẫu số trên màn hình: số lượng hàng, tỷ lệ, tiền.
_SAMPLES = (1234.56, 12.4, 1250000000)


def _preview(style: str) -> list[dict[str, str]]:
    qty, pct, money = _SAMPLES
    return [
        {"label": "Số lượng", "value": fmt_qty(qty, "kg", style=style)},
        {"label": "Tỷ lệ chênh lệch", "value": fmt_pct(pct, style=style)},
        {"label": "Trị giá", "value": fmt_money(money, style=style)},
    ]


def _render(
    request: Request,
    user: SessionUser,
    current: str,
    *,
    error: str | None = None,
    saved: bool = False,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "admin_display.html",
        {
            "user": user,
            "current": current,
            "options": [
                {"value": v, "label": label, "preview": _preview(v)}
                for v, label in NUMBER_FORMAT_LABELS.items()
            ],
            "default_format": DEFAULT_NUMBER_FORMAT,
            "error": error,
            "saved": saved,
        },
    )


@router.get("", response_class=HTMLResponse)
def edit_form(
    request: Request,
    saved: int = 0,
    user: SessionUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    return _render(request, user, get_number_format(db), saved=bool(saved))


@router.post("")
def save(
    request: Request,
    number_format: str = Form(...),
    user: SessionUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        set_number_format(number_format, updated_by=str(user), db=db)
    except ValidationError as exc:
        return _render(request, user, get_number_format(db), error=str(exc))
    return RedirectResponse(url="/admin/hien-thi?saved=1", status_code=303)
