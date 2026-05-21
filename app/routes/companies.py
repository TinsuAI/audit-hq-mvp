"""Routes for browsing companies and their findings (Tầng 2 viewer)."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import require_user
from app.checks.combos import COMBO_SPECS
from app.checks.registry import SEVERITY_BADGE, SEVERITY_LABEL_VI, SPECS, Severity
from app.database import get_db
from app.models import Company, DeclarationLine, Finding, Norm, NvlBalance, SpBalance
from app.pipeline.export import build_export

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")

# Filters available in templates
templates.env.globals["SEVERITY_BADGE"] = {s.value: SEVERITY_BADGE[s] for s in Severity}
templates.env.globals["SEVERITY_LABEL"] = {s.value: SEVERITY_LABEL_VI[s] for s in Severity}
templates.env.globals["SPECS"] = {code: spec for code, spec in SPECS.items()}
templates.env.globals["COMBO_SPECS"] = COMBO_SPECS

_SEVERITY_ORDER = {Severity.CRITICAL.value: 0, Severity.WARNING.value: 1, Severity.INFO.value: 2}

ALLOWED_STATUSES = {"new", "confirmed", "rejected", "noted"}

STATUS_LABEL_VI = {
    "new": "Mới",
    "confirmed": "Xác nhận",
    "rejected": "Loại trừ",
    "noted": "Đã ghi chú",
}

templates.env.globals["STATUS_LABEL"] = STATUS_LABEL_VI
templates.env.globals["ALLOWED_STATUSES"] = sorted(ALLOWED_STATUSES)

router = APIRouter()


@router.get("/companies", response_class=HTMLResponse)
def list_companies(
    request: Request,
    user: str = Depends(require_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    companies = db.scalars(
        select(Company).order_by(Company.risk_score.desc(), Company.code)
    ).all()
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
            "years": sorted(years.items(), reverse=True),
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

    # Tách combo (meta-finding) khỏi findings thường để render riêng ở đầu trang.
    combo_findings = [f for f in findings if f.check_code.startswith("COMBO_")]
    regular_findings = [f for f in findings if not f.check_code.startswith("COMBO_")]

    grouped: dict[str, list[Finding]] = defaultdict(list)
    severity_totals = {"critical": 0, "warning": 0, "info": 0}
    for f in regular_findings:
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
            "combo_findings": combo_findings,
            "severity_totals": severity_totals,
            "total_findings": len(regular_findings),
        },
    )


_EVIDENCE_MODELS = {
    "nvl_balances": NvlBalance,
    "sp_balances": SpBalance,
    "norms": Norm,
    "declaration_lines": DeclarationLine,
    "findings": Finding,
}


def _resolve_evidence(db: Session, ref: dict) -> list[dict]:
    """Resolve 1 evidence_ref (table + filter) thành list dòng dữ liệu Tầng 1."""
    table = ref.get("table")
    model = _EVIDENCE_MODELS.get(table)
    if model is None:
        return []
    filt = ref.get("filter") or {}
    stmt = select(model)
    for key, value in filt.items():
        # Handle "key__in" syntax for IN clauses.
        if key.endswith("__in"):
            real_key = key[:-4]
            col = getattr(model, real_key, None)
            if col is None:
                continue
            stmt = stmt.where(col.in_(value))
        else:
            col = getattr(model, key, None)
            if col is None:
                continue
            stmt = stmt.where(col == value)
    rows = db.scalars(stmt.limit(50)).all()
    return [
        {c.name: getattr(r, c.name, None) for c in r.__table__.columns}
        for r in rows
    ]


@router.get("/companies/{code}/export")
def export_recommendations(
    code: str,
    year: int = Query(...),
    user: str = Depends(require_user),
    db: Session = Depends(get_db),
) -> Response:
    company = db.scalar(select(Company).where(Company.code == code))
    if company is None:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy DN {code}")
    payload = build_export(db, company, year)
    filename = f"audit-hq_{code}_{year}_kien-nghi-kiem-tra.xlsx"
    return Response(
        content=payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


_TABLE_CONFIG = {
    "m15": {
        "model": NvlBalance,
        "label": "Mẫu 15 — Cân đối NVL",
        "code_field": "material_code",
        "code_label": "Mã NVL",
    },
    "m15a": {
        "model": SpBalance,
        "label": "Mẫu 15a — Cân đối TP",
        "code_field": "product_code",
        "code_label": "Mã TP",
    },
    "m16": {
        "model": Norm,
        "label": "Mẫu 16 — Định mức",
        "code_field": "material_code",
        "code_label": "Mã NVL",
    },
    "bcct": {
        "model": DeclarationLine,
        "label": "BCCT — Báo cáo hàng chi tiết",
        "code_field": "item_code",
        "code_label": "Mã hàng",
    },
}


@router.get("/companies/{code}/data", response_class=HTMLResponse)
def company_data(
    code: str,
    request: Request,
    year: int = Query(...),
    table: str = Query("m15"),
    q: str = Query("", description="Lọc theo mã"),
    page: int = Query(1, ge=1),
    user: str = Depends(require_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    company = db.scalar(select(Company).where(Company.code == code))
    if company is None:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy DN {code}")

    config = _TABLE_CONFIG.get(table)
    if config is None:
        raise HTTPException(status_code=400, detail=f"Bảng không hợp lệ: {table}")

    model = config["model"]
    code_field = config["code_field"]
    per_page = 50

    stmt = select(model).where(model.company_id == company.id, model.period_year == year)
    if q:
        col = getattr(model, code_field)
        stmt = stmt.where(col.contains(q))
    stmt = stmt.order_by(getattr(model, code_field))

    total = db.scalar(
        select(func.count()).select_from(stmt.subquery())
    ) or 0
    rows = db.scalars(stmt.offset((page - 1) * per_page).limit(per_page)).all()

    rows_dict = [
        {c.name: getattr(r, c.name, None) for c in r.__table__.columns}
        for r in rows
    ]

    return templates.TemplateResponse(
        request,
        "company_data.html",
        {
            "user": user,
            "company": company,
            "year": year,
            "table_key": table,
            "table_label": config["label"],
            "code_label": config["code_label"],
            "code_field": code_field,
            "tables": list(_TABLE_CONFIG.items()),
            "rows": rows_dict,
            "total": total,
            "page": page,
            "per_page": per_page,
            "q": q,
        },
    )


@router.get("/findings/{finding_id}", response_class=HTMLResponse)
def finding_detail(
    finding_id: int,
    request: Request,
    user: str = Depends(require_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    finding = db.get(Finding, finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy phát hiện")
    company = db.get(Company, finding.company_id)
    is_combo = finding.check_code.startswith("COMBO_")
    spec = COMBO_SPECS.get(finding.check_code) if is_combo else SPECS.get(finding.check_code)

    evidence_blocks: list[dict] = []
    for ref in (finding.evidence_refs or []):
        evidence_blocks.append({
            "ref": ref,
            "rows": _resolve_evidence(db, ref),
        })

    return templates.TemplateResponse(
        request,
        "finding_detail.html",
        {
            "user": user,
            "finding": finding,
            "company": company,
            "spec": spec,
            "is_combo": is_combo,
            "evidence_blocks": evidence_blocks,
        },
    )


@router.post("/findings/{finding_id}/status")
def update_finding_status(
    finding_id: int,
    request: Request,
    status: str = Form(...),
    notes: str = Form(""),
    user: str = Depends(require_user),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    if status not in ALLOWED_STATUSES:
        raise HTTPException(status_code=400, detail=f"Trạng thái không hợp lệ: {status}")

    finding = db.get(Finding, finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy phát hiện")

    finding.status = status
    finding.notes = notes.strip() or None
    db.commit()

    company = db.get(Company, finding.company_id)
    code = company.code if company else None
    if not code:
        return RedirectResponse(url="/companies", status_code=303)
    return RedirectResponse(
        url=f"/companies/{code}?year={finding.period_year}#finding-{finding_id}",
        status_code=303,
    )
