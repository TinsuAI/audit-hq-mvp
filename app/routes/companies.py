"""Routes for browsing companies and their findings (Tầng 2 viewer)."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import require_user
from app.checks.registry import SEVERITY_BADGE, SEVERITY_LABEL_VI, SPECS, Severity
from app.database import get_db
from app.models import Company, Finding

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")

# Filters available in templates
templates.env.globals["SEVERITY_BADGE"] = {s.value: SEVERITY_BADGE[s] for s in Severity}
templates.env.globals["SEVERITY_LABEL"] = {s.value: SEVERITY_LABEL_VI[s] for s in Severity}
templates.env.globals["SPECS"] = {code: spec for code, spec in SPECS.items()}

_SEVERITY_ORDER = {Severity.CRITICAL.value: 0, Severity.WARNING.value: 1, Severity.INFO.value: 2}

router = APIRouter()


@router.get("/companies", response_class=HTMLResponse)
def list_companies(
    request: Request,
    user: str = Depends(require_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    companies = db.scalars(select(Company).order_by(Company.code)).all()
    summary = []
    for c in companies:
        counts_rows = db.execute(
            select(Finding.period_year, Finding.severity, func.count())
            .where(Finding.company_id == c.id)
            .group_by(Finding.period_year, Finding.severity)
        ).all()
        years: dict[int, dict[str, int]] = defaultdict(lambda: {"critical": 0, "warning": 0, "info": 0})
        for year, sev, n in counts_rows:
            if sev in years[year]:
                years[year][sev] = n
        summary.append({
            "company": c,
            "years": sorted(years.items()),
        })
    return templates.TemplateResponse(
        request,
        "companies_list.html",
        {"user": user, "summary": summary},
    )


@router.get("/companies/{code}", response_class=HTMLResponse)
def company_detail(
    code: str,
    request: Request,
    year: int | None = Query(default=None),
    user: str = Depends(require_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    company = db.scalar(select(Company).where(Company.code == code))
    if company is None:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy DN {code}")

    years = sorted(
        db.scalars(
            select(Finding.period_year).where(Finding.company_id == company.id).distinct()
        ).all(),
        reverse=True,
    )
    selected_year = year if year is not None else (years[0] if years else None)

    findings: list[Finding] = []
    if selected_year is not None:
        findings = db.scalars(
            select(Finding)
            .where(Finding.company_id == company.id, Finding.period_year == selected_year)
            .order_by(Finding.check_code, Finding.subject_key)
        ).all()

    grouped: dict[str, list[Finding]] = defaultdict(list)
    severity_totals = {"critical": 0, "warning": 0, "info": 0}
    for f in findings:
        grouped[f.check_code].append(f)
        if f.severity in severity_totals:
            severity_totals[f.severity] += 1

    ordered_groups = sorted(
        grouped.items(),
        key=lambda kv: (
            min(_SEVERITY_ORDER.get(f.severity, 99) for f in kv[1]),
            kv[0],
        ),
    )

    return templates.TemplateResponse(
        request,
        "company_detail.html",
        {
            "user": user,
            "company": company,
            "years": years,
            "selected_year": selected_year,
            "ordered_groups": ordered_groups,
            "severity_totals": severity_totals,
            "total_findings": len(findings),
        },
    )
