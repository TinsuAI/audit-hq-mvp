"""Admin routes — quản lý catalog check động (/admin/checks/*)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

from fastapi import APIRouter, Body, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import SessionUser, require_admin
from app.checks.dynamic_runner import DynamicCheckRunner, SpecValidationError
from app.checks.spec_gen import SpecGenError, generate_spec
from app.database import get_db
from app.models.check_definition import CheckDefinition, CheckStatus, next_check_code
from app.version import VERSION, version_string

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")
templates.env.globals["app_version_string"] = version_string()
templates.env.globals["app_version"] = VERSION

router = APIRouter(prefix="/admin/checks")

_KIND_LABELS = {
    "threshold_compare": "So sánh ngưỡng",
    "presence_check": "Kiểm tra hiện diện",
    "aggregate_threshold": "Tổng hợp + ngưỡng",
    "cross_table_match": "Đối chiếu 2 bảng",
    "ratio_threshold": "Tỷ lệ + ngưỡng",
}


@router.get("", response_class=HTMLResponse)
def checks_list(
    request: Request,
    user: SessionUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    rows = db.scalars(
        select(CheckDefinition).order_by(CheckDefinition.id)
    ).all()
    return templates.TemplateResponse(
        request,
        "admin_checks.html",
        {
            "user": user,
            "checks": rows,
            "kind_labels": _KIND_LABELS,
            "CheckStatus": CheckStatus,
        },
    )


@router.get("/new", response_class=HTMLResponse)
def checks_new_form(
    request: Request,
    user: SessionUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "admin_checks_new.html",
        {
            "user": user,
            "kind_labels": _KIND_LABELS,
            "error": None,
            "form": {},
        },
    )


@router.post("", response_model=None)
def checks_create(
    request: Request,
    title: str = Form(...),
    description: str = Form(""),
    kind: str = Form(...),
    spec_json: str = Form(...),
    group: int = Form(99),
    default_severity: str = Form("warning"),
    user: SessionUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> HTMLResponse | RedirectResponse:
    try:
        spec = json.loads(spec_json)
    except json.JSONDecodeError as e:
        return _form_error(request, user, kind, {"title": title, "description": description,
                           "kind": kind, "spec_json": spec_json},
                           f"Spec JSON không hợp lệ: {e}")

    try:
        DynamicCheckRunner(code="X.0", spec=spec)
    except SpecValidationError as e:
        return _form_error(request, user, kind, {"title": title, "description": description,
                           "kind": kind, "spec_json": spec_json}, str(e))

    code = next_check_code(db)
    cd = CheckDefinition(
        code=code,
        kind=kind,
        title=title.strip(),
        description=description.strip(),
        group=group,
        default_severity=default_severity,
        spec=spec,
        status=CheckStatus.DRAFT,
    )
    db.add(cd)
    db.commit()
    return RedirectResponse(url=f"/admin/checks/{cd.id}", status_code=303)


@router.post("/generate-spec", response_class=JSONResponse)
def checks_generate_spec(
    payload: dict = Body(...),
    user: SessionUser = Depends(require_admin),
) -> JSONResponse:
    """Gọi AI sinh spec JSON từ mô tả nghiệp vụ.

    Body: {"description": str, "kind_hint": str | null}
    Returns: {"spec": dict | null, "error": str | null}
    """
    description = (payload.get("description") or "").strip()
    kind_hint = payload.get("kind_hint") or None

    try:
        spec = generate_spec(description, kind_hint=kind_hint)
        return JSONResponse({"spec": spec, "error": None})
    except SpecGenError as e:
        return JSONResponse({"spec": None, "error": str(e)})
    except Exception as e:
        log.exception("Unexpected error in generate_spec")
        return JSONResponse({"spec": None, "error": f"Lỗi không mong đợi: {e}"})


@router.get("/{check_id}", response_class=HTMLResponse)
def checks_detail(
    request: Request,
    check_id: int,
    user: SessionUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    cd = db.get(CheckDefinition, check_id)
    if cd is None:
        raise HTTPException(status_code=404, detail="Check không tồn tại")
    return templates.TemplateResponse(
        request,
        "admin_checks_detail.html",
        {
            "user": user,
            "check": cd,
            "spec_json": json.dumps(cd.spec, ensure_ascii=False, indent=2),
            "kind_labels": _KIND_LABELS,
            "CheckStatus": CheckStatus,
        },
    )


@router.post("/{check_id}/publish", response_model=None)
def checks_publish(
    check_id: int,
    user: SessionUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    cd = db.get(CheckDefinition, check_id)
    if cd is None:
        raise HTTPException(status_code=404, detail="Check không tồn tại")
    cd.status = CheckStatus.PUBLISHED
    db.commit()
    return RedirectResponse(url=f"/admin/checks/{check_id}", status_code=303)


@router.post("/{check_id}/disable", response_model=None)
def checks_disable(
    check_id: int,
    user: SessionUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    cd = db.get(CheckDefinition, check_id)
    if cd is None:
        raise HTTPException(status_code=404, detail="Check không tồn tại")
    cd.status = CheckStatus.DISABLED
    db.commit()
    return RedirectResponse(url=f"/admin/checks/{check_id}", status_code=303)


@router.post("/{check_id}/draft", response_model=None)
def checks_revert_draft(
    check_id: int,
    user: SessionUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    cd = db.get(CheckDefinition, check_id)
    if cd is None:
        raise HTTPException(status_code=404, detail="Check không tồn tại")
    cd.status = CheckStatus.DRAFT
    db.commit()
    return RedirectResponse(url=f"/admin/checks/{check_id}", status_code=303)


def _form_error(request: Request, user: SessionUser, kind: str, form: dict, error: str):
    return templates.TemplateResponse(
        request,
        "admin_checks_new.html",
        {
            "user": user,
            "kind_labels": _KIND_LABELS,
            "error": error,
            "form": form,
        },
        status_code=400,
    )
