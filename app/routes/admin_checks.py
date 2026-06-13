"""Admin routes — soạn & quản lý kiểm tra mở rộng (SQL/Python) từ NL (/admin/checks/*)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import APIRouter, Body, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import SessionUser, require_admin
from app.checks.spec_gen import SpecGenError, draft_and_validate
from app.checks.sql_runner import (
    ALLOWED_SCOPES,
    ALLOWED_SUBJECT_TABLES,
    CheckRunError,
    run_check,
    validate_check_definition,
)
from app.database import get_db
from app.models import Company, DeclarationLine, Norm, NvlBalance, SpBalance
from app.models.check_definition import CheckDefinition, CheckStatus, next_check_code
from app.version import VERSION, version_string

log = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")
templates.env.globals["app_version_string"] = version_string()
templates.env.globals["app_version"] = VERSION

router = APIRouter(prefix="/admin/checks")

_KIND_LABELS = {"sql": "SQL", "python": "Python"}
_SCOPE_LABELS = {"nvl": "NVL (nguyên vật liệu)", "tp": "TP (thành phẩm)", "m16": "Định mức (M16)"}
_SEVERITY_LABELS = {"critical": "Nghiêm trọng", "warning": "Cảnh báo", "info": "Thông tin"}


def _example_prompts() -> list[str]:
    return [
        "Tìm các mã nguyên vật liệu có tồn kho cuối kỳ âm",
        "Mã NVL nhập khẩu nhưng không xuất hiện trong định mức M16",
        "Tờ khai xuất có đơn giá bằng 0 hoặc bỏ trống",
        "Thành phẩm có xuất khẩu vượt quá lượng nhập kho cộng tồn đầu",
    ]


def _default_ref(db: Session) -> tuple[str, int]:
    """DN + năm tham chiếu mặc định cho dry-run authoring (DN có dữ liệu, năm mới nhất)."""
    row = db.execute(
        select(NvlBalance.company_id, func.max(NvlBalance.period_year))
        .group_by(NvlBalance.company_id)
        .order_by(func.max(NvlBalance.period_year).desc())
    ).first()
    if row:
        company = db.get(Company, row[0])
        if company:
            return company.code, int(row[1])
    company = db.scalar(select(Company).order_by(Company.code))
    return (company.code if company else ""), 2024


def _companies_with_years(db: Session) -> list[dict]:
    """DN + danh sách năm có dữ liệu Tầng 1 (cho picker tham chiếu)."""
    out = []
    for c in db.scalars(select(Company).order_by(Company.code)).all():
        years: set[int] = set()
        for model in (NvlBalance, SpBalance, Norm, DeclarationLine):
            years |= set(db.scalars(
                select(model.period_year).where(model.company_id == c.id).distinct()
            ).all())
        out.append({"code": c.code, "name": c.name or "", "years": sorted(years, reverse=True)})
    return out


@router.get("", response_class=HTMLResponse)
def checks_list(
    request: Request,
    user: SessionUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    rows = db.scalars(select(CheckDefinition).order_by(CheckDefinition.id)).all()
    return templates.TemplateResponse(
        request, "admin_checks.html",
        {"user": user, "checks": rows, "kind_labels": _KIND_LABELS, "CheckStatus": CheckStatus},
    )


@router.get("/new", response_class=HTMLResponse)
def checks_new_form(
    request: Request,
    user: SessionUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    ref_code, ref_year = _default_ref(db)
    return templates.TemplateResponse(
        request, "admin_checks_new.html",
        {
            "user": user, "error": None, "nl_prompt": "",
            "examples": _example_prompts(),
            "companies": _companies_with_years(db),
            "ref_company": ref_code, "ref_year": ref_year,
        },
    )


@router.post("/draft", response_model=None)
def checks_draft(
    request: Request,
    nl_prompt: str = Form(...),
    ref_company: str = Form(...),
    ref_year: int = Form(...),
    user: SessionUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Soạn check từ NL (agentic loop) → trang preview. Đồng bộ (có spinner ở client)."""
    from app.ai.config import get_setting

    def _new_with_error(msg: str, status: int = 400) -> HTMLResponse:
        return templates.TemplateResponse(
            request, "admin_checks_new.html",
            {
                "user": user, "error": msg, "nl_prompt": nl_prompt,
                "examples": _example_prompts(), "companies": _companies_with_years(db),
                "ref_company": ref_company, "ref_year": ref_year,
            },
            status_code=status,
        )

    if not (get_setting("enabled") and get_setting("api_key")):
        return _new_with_error("AI assistant đang tắt hoặc chưa cấu hình. Bật trong /admin/ai.", 503)

    company = db.scalar(select(Company).where(Company.code == ref_company))
    if company is None:
        return _new_with_error(f"Không tìm thấy DN tham chiếu '{ref_company}'.")

    try:
        result = draft_and_validate(
            db, company.id, ref_year, nl_prompt.strip(), ref_company_code=ref_company,
        )
    except SpecGenError as e:
        return _new_with_error(str(e))
    except Exception as e:  # noqa: BLE001
        log.exception("checks_draft unexpected error")
        return _new_with_error(f"Lỗi không mong đợi: {e}", 500)

    return templates.TemplateResponse(
        request, "admin_checks_preview.html",
        {
            "user": user, "r": result,
            "plan_json": json.dumps(result.plan, ensure_ascii=False),
            "self_review_json": json.dumps(result.self_review, ensure_ascii=False),
            "kind_labels": _KIND_LABELS, "scope_labels": _SCOPE_LABELS,
            "severity_labels": _SEVERITY_LABELS,
        },
    )


@router.post("", response_model=None)
def checks_create(
    request: Request,
    nl_prompt: str = Form(""),
    kind: str = Form(...),
    title: str = Form(...),
    description: str = Form(""),
    base_severity: str = Form("warning"),
    scope: str = Form("nvl"),
    subject_table: str = Form(""),
    subject_col: str = Form(""),
    sql_snippet: str = Form(""),
    detail_query: str = Form(""),
    code_snippet: str = Form(""),
    analysis: str = Form(""),
    plan_json: str = Form("[]"),
    self_review_json: str = Form("{}"),
    user: SessionUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Lưu check (status=DRAFT) từ kết quả preview."""
    subject_table = subject_table.strip() or None
    subject_col = subject_col.strip() or None
    err = validate_check_definition(
        kind=kind, sql=sql_snippet, code=code_snippet,
        subject_table=subject_table, scope=scope,
    )
    if err:
        raise HTTPException(status_code=400, detail=f"Check không hợp lệ: {err}")

    def _loads(raw: str, default):
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return default

    from app.auth_users import get_user_by_username
    user_row = get_user_by_username(db, user.name)

    cd = CheckDefinition(
        code=next_check_code(db),
        kind=kind.strip().lower(),
        title=title.strip(),
        description=description.strip(),
        group=99,
        default_severity=base_severity if base_severity in _SEVERITY_LABELS else "warning",
        spec={},
        scope=scope if scope in ALLOWED_SCOPES else "nvl",
        subject_table=subject_table if subject_table in ALLOWED_SUBJECT_TABLES else None,
        subject_col=subject_col,
        sql_snippet=sql_snippet.strip() or None,
        detail_query=detail_query.strip() or None,
        code_snippet=code_snippet.strip() or None,
        nl_prompt=nl_prompt.strip() or None,
        analysis=analysis.strip() or None,
        plan=_loads(plan_json, []),
        self_review=_loads(self_review_json, {}),
        status=CheckStatus.DRAFT,
        created_by=user_row.id if user_row else None,
    )
    db.add(cd)
    db.commit()
    return RedirectResponse(url=f"/admin/checks/{cd.id}", status_code=303)


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
    companies = db.scalars(select(Company).order_by(Company.code)).all()
    return templates.TemplateResponse(
        request, "admin_checks_detail.html",
        {
            "user": user, "check": cd,
            "kind_labels": _KIND_LABELS, "scope_labels": _SCOPE_LABELS,
            "severity_labels": _SEVERITY_LABELS,
            "CheckStatus": CheckStatus, "companies": companies,
        },
    )


@router.post("/{check_id}/preview", response_class=JSONResponse)
def checks_preview(
    check_id: int,
    payload: dict = Body(...),
    user: SessionUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> JSONResponse:
    """Chạy thử check trên (DN, năm) — không ghi findings."""
    cd = db.get(CheckDefinition, check_id)
    if cd is None:
        raise HTTPException(status_code=404, detail="Check không tồn tại")
    company = db.scalar(select(Company).where(Company.code == (payload.get("company_code") or "").strip()))
    if company is None:
        return JSONResponse({"findings": None, "count": 0, "error": "Không tìm thấy DN"})
    try:
        findings = run_check(cd, db, company.id, int(payload.get("year")))
    except CheckRunError as exc:
        return JSONResponse({"findings": None, "count": 0, "error": str(exc)})
    except Exception as exc:  # noqa: BLE001
        log.exception("preview run failed for %s", cd.code)
        return JSONResponse({"findings": None, "count": 0, "error": str(exc)})
    finally:
        db.rollback()  # đảm bảo không ghi Finding nào (chỉ chạy thử)
    return JSONResponse({
        "findings": [
            {"title": f.title, "severity": f.severity, "subject_key": f.subject_key,
             "detail": (f.details or {}).get("detail")}
            for f in findings[:200]
        ],
        "count": len(findings), "error": None,
    })


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
