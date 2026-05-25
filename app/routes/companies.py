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


def _resolve_evidence(db: Session, ref: dict) -> tuple[list[tuple[str, str, str]], list[list[tuple]]]:
    """Resolve 1 evidence_ref (table + filter) → (view_cols, rows_view).

    rows_view: list dòng, mỗi dòng là list (display_value, css_class) đã format.
    Dùng đồng nhất với company_data view, có wrap/format số/date.
    """
    table = ref.get("table")
    model = _EVIDENCE_MODELS.get(table)
    if model is None:
        return [], []
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
    return _format_model_rows(model, rows)


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
        # (field, label, cell_class). Chỉ các cột thực sự cần để rà cân đối M15.
        # cls: num/date/code-cell/wrap/"" — quyết định alignment + format + clamp.
        "view_cols": [
            ("row_no", "STT", "num"),
            ("material_code", "Mã NVL", "code-cell"),
            ("material_name", "Tên NVL", "wrap"),
            ("unit", "ĐVT", ""),
            ("opening_qty", "Tồn đầu", "num"),
            ("import_qty", "Nhập", "num"),
            ("production_out_qty", "Xuất SX", "num"),
            ("closing_qty", "Tồn cuối", "num"),
        ],
    },
    "m15a": {
        "model": SpBalance,
        "label": "Mẫu 15a — Cân đối TP",
        "code_field": "product_code",
        "code_label": "Mã TP",
        "view_cols": [
            ("row_no", "STT", "num"),
            ("product_code", "Mã TP", "code-cell"),
            ("product_name", "Tên TP", "wrap"),
            ("unit", "ĐVT", ""),
            ("opening_qty", "Tồn đầu", "num"),
            ("intake_qty", "Nhập kho SX", "num"),
            ("export_qty", "Xuất", "num"),
            ("closing_qty", "Tồn cuối", "num"),
        ],
    },
    "m16": {
        "model": Norm,
        "label": "Mẫu 16 — Định mức",
        "code_field": "material_code",
        "code_label": "Mã NVL",
        "view_cols": [
            ("product_code", "Mã SP", "code-cell"),
            ("product_name", "Tên SP", "wrap"),
            ("product_unit", "ĐVT SP", ""),
            ("material_code", "Mã NVL", "code-cell"),
            ("material_name", "Tên NVL", "wrap"),
            ("material_unit", "ĐVT NVL", ""),
            ("norm_qty", "Định mức", "num"),
        ],
    },
    "bcct": {
        "model": DeclarationLine,
        "label": "BCCT — Báo cáo hàng chi tiết",
        "code_field": "item_code",
        "code_label": "Mã hàng",
        "view_cols": [
            ("declaration_no", "Số TK", "code-cell"),
            ("declaration_date", "Ngày", "date"),
            ("customs_code", "Loại hình", "code-cell"),
            ("item_code", "Mã hàng", "code-cell"),
            ("item_name", "Tên hàng", "wrap"),
            ("hs_code", "Mã HS", "code-cell"),
            ("quantity", "SL", "num"),
            ("unit", "ĐVT", ""),
            ("value_total", "Trị giá (VND)", "num"),
            ("partner", "Đối tác", ""),
        ],
    },
}

# Map tablename → view_cols dùng cho evidence_blocks ở finding_detail.html
# (giữ đồng nhất với cột curated của company_data).
_VIEW_COLS_BY_TABLE = {
    "nvl_balances": _TABLE_CONFIG["m15"]["view_cols"],
    "sp_balances": _TABLE_CONFIG["m15a"]["view_cols"],
    "norms": _TABLE_CONFIG["m16"]["view_cols"],
    "declaration_lines": _TABLE_CONFIG["bcct"]["view_cols"],
    "findings": [
        ("check_code", "Mã check", "code-cell"),
        ("severity", "Mức", "code-cell"),
        ("subject_key", "Đối tượng", "code-cell"),
        ("title", "Tiêu đề", "wrap"),
        ("status", "Trạng thái", ""),
    ],
}


def _format_cell(value, cls: str):
    """Format value theo loại cột để gọn và dễ đọc."""
    if value is None:
        return ""
    if cls == "num" and isinstance(value, (int, float)) and not isinstance(value, bool):
        # Bỏ .0 cho số nguyên; số thập phân giữ tối đa 2 chữ số.
        if float(value).is_integer():
            return f"{int(value):,}"
        return f"{value:,.2f}"
    if cls == "date" and hasattr(value, "strftime"):
        return value.strftime("%d/%m/%Y")
    return value


def _format_model_rows(model, rows, full: bool = False):
    """Format ORM rows for display: pick curated cols (or all) and format values.

    Trả về (view_cols, rows_view). Dùng cho cả company_data và evidence_blocks.
    """
    tablename = model.__tablename__
    if full or tablename not in _VIEW_COLS_BY_TABLE:
        exclude = {"id", "company_id", "period_year", "source_file"}
        view_cols = [
            (c.name, c.name, "")
            for c in model.__table__.columns
            if c.name not in exclude
        ]
    else:
        view_cols = _VIEW_COLS_BY_TABLE[tablename]
    rows_view = [
        [(_format_cell(getattr(r, field, None), cls), cls) for field, _label, cls in view_cols]
        for r in rows
    ]
    return view_cols, rows_view


@router.get("/companies/{code}/data", response_class=HTMLResponse)
def company_data(
    code: str,
    request: Request,
    year: int = Query(...),
    table: str = Query("m15"),
    q: str = Query("", description="Lọc theo mã"),
    page: int = Query(1, ge=1),
    full: int = Query(0, description="1 = hiện toàn bộ cột DB"),
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

    view_cols, rows_view = _format_model_rows(model, rows, full=bool(full))

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
            "view_cols": view_cols,
            "rows": rows_view,
            "total": total,
            "page": page,
            "per_page": per_page,
            "q": q,
            "full": full,
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
        view_cols, rows_view = _resolve_evidence(db, ref)
        evidence_blocks.append({
            "ref": ref,
            "view_cols": view_cols,
            "rows": rows_view,
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
