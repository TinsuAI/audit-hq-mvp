"""Trang `/admin/risk-tiers` — chỉnh 5 ngưỡng hạng rủi ro."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.app_settings import (
    DEFAULT_RISK_TIER_UPPERS,
    RISK_TIER_CSS,
    RISK_TIER_LABELS,
    ValidationError,
    get_risk_tier_uppers,
    save_risk_tier_uppers,
)
from app.auth import SessionUser, require_admin
from app.database import get_db
from app.version import VERSION, version_string

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")
templates.env.globals["app_version"] = VERSION
templates.env.globals["app_version_string"] = version_string()

router = APIRouter(prefix="/admin/risk-tiers")


def _render(
    request: Request,
    user: SessionUser,
    uppers: tuple[int, ...],
    *,
    error: str | None = None,
    saved: bool = False,
) -> HTMLResponse:
    tiers = []
    lower = 0
    for i, upper in enumerate(uppers):
        tiers.append({
            "index": i + 1,
            "lower": lower,
            "upper": upper,
            "label": RISK_TIER_LABELS[i],
            "css": RISK_TIER_CSS[i],
            "is_last": i == len(uppers) - 1,
        })
        lower = upper
    is_default = tuple(uppers) == DEFAULT_RISK_TIER_UPPERS
    return templates.TemplateResponse(
        request,
        "admin_risk_tiers.html",
        {
            "user": user,
            "tiers": tiers,
            "uppers": list(uppers),
            "defaults": list(DEFAULT_RISK_TIER_UPPERS),
            "is_default": is_default,
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
    uppers = get_risk_tier_uppers(db)
    return _render(request, user, uppers, saved=bool(saved))


@router.post("")
def save(
    request: Request,
    upper_1: int = Form(...),
    upper_2: int = Form(...),
    upper_3: int = Form(...),
    upper_4: int = Form(...),
    upper_5: int = Form(...),
    user: SessionUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    uppers_in = [upper_1, upper_2, upper_3, upper_4, upper_5]
    try:
        save_risk_tier_uppers(uppers_in, updated_by=str(user), db=db)
    except ValidationError as exc:
        return _render(request, user, tuple(uppers_in), error=str(exc))
    return RedirectResponse(url="/admin/risk-tiers?saved=1", status_code=303)


@router.post("/reset")
def reset(
    user: SessionUser = Depends(require_admin),
    db: Session = Depends(get_db),
):
    save_risk_tier_uppers(list(DEFAULT_RISK_TIER_UPPERS), updated_by=str(user), db=db)
    return RedirectResponse(url="/admin/risk-tiers?saved=1", status_code=303)
