"""Routes for browsing companies and their findings (Tầng 2 viewer)."""

from __future__ import annotations

import json as _json
import re
from collections import defaultdict
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import SessionUser, require_user
from app.checks.combos import COMBO_SPECS
from app.checks.registry import SEVERITY_BADGE, SEVERITY_LABEL_VI, SPECS, Severity, get_all_specs
from app.checks.scoring import tier_css_for, tier_for
from app.database import get_db
from app.items.aggregations import (
    bcct_lines_for_item,
    bom_edges_for_nvl,
    bom_edges_for_tp,
    detect_item_kind,
    item_years,
    nvl_yearly_summary,
    sp_yearly_summary,
)
from app.items.charts import sankey_layout, sparkline_points, waterfall_layout
from app.items.operations import classify_operation, operation_label
from app.models import (
    Company,
    CompanyYearScore,
    DeclarationLine,
    Finding,
    Norm,
    NvlBalance,
    SpBalance,
)
from app.pipeline.export import build_export
from app.pipeline.ingest import ingest as run_ingest
from app.pipeline.run_checks import run_checks as run_check_pipeline
from app.settings import settings
from app.version import VERSION, version_string

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")

# Filters available in templates
templates.env.globals["SEVERITY_BADGE"] = {s.value: SEVERITY_BADGE[s] for s in Severity}
templates.env.globals["SEVERITY_LABEL"] = {s.value: SEVERITY_LABEL_VI[s] for s in Severity}
templates.env.globals["SPECS"] = {code: spec for code, spec in SPECS.items()}
templates.env.globals["COMBO_SPECS"] = COMBO_SPECS
templates.env.globals["tier_css_for"] = tier_css_for
templates.env.globals["tier_for"] = tier_for

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
templates.env.globals["app_version"] = VERSION
templates.env.globals["app_version_string"] = version_string()


def _timeline_payload(lines: list) -> list[dict]:
    """Serialize BCCT lines to a minimal payload for the timeline chart."""
    out: list[dict] = []
    for ln in lines:
        if ln.declaration_date is None:
            continue
        out.append({
            "date": ln.declaration_date.isoformat(),
            "qty": float(ln.quantity or 0),
            "op": classify_operation(ln.customs_code),
            "customs_code": ln.customs_code or "",
            "declaration_no": ln.declaration_no,
            "partner": ln.partner or "",
        })
    return out


def _heatmap_payload(yearly: list[dict], kind: str) -> list[dict]:
    """Year × metric series for the cross-year heatmap."""
    metrics_nvl = [
        ("BCCT nhập", "bcct_import_qty"),
        ("BCCT xuất", "bcct_export_qty"),
        ("M15 nhập", "import_qty"),
        ("Đưa vào SX", "production_out_qty"),
        ("Tồn cuối", "closing_qty"),
    ]
    metrics_tp = [
        ("BCCT xuất", "bcct_export_qty"),
        ("M15a nhập kho", "intake_qty"),
        ("M15a xuất", "export_qty"),
        ("Tồn cuối", "closing_qty"),
    ]
    metrics = metrics_tp if kind == "tp" else metrics_nvl
    return [
        {
            "name": label,
            "data": [{"x": str(r["year"]), "y": float(r.get(field, 0) or 0)} for r in yearly],
        }
        for label, field in metrics
    ]


templates.env.filters["tojson_timeline"] = lambda lines: _json.dumps(_timeline_payload(lines))
templates.env.filters["tojson_heatmap"] = lambda yearly, kind: _json.dumps(
    _heatmap_payload(yearly, kind)
)

router = APIRouter()


@router.get("/companies", response_class=HTMLResponse)
def list_companies(
    request: Request,
    user: SessionUser = Depends(require_user),
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


CODE_RE = re.compile(r"^[A-Z][A-Z0-9_-]{1,30}$")
DEMO_SUFFIX = "(Demo)"
YEAR_MIN, YEAR_MAX = 2015, 2030
MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # 100MB per file

# Mỗi slot → (subdir, fixed filename stem). Stem để tên match discover() patterns.
_UPLOAD_SLOTS = {
    "m15": ("BCQT", "M15_NVL"),
    "m15a": ("BCQT", "M15a_SP"),
    "m16": ("DINH_MUC", "BCDM_TT39"),
    "bcct": ("HANG_CHI_TIET", "BCCT"),
}


def _save_upload(upload: UploadFile, dest: Path) -> int:
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Wipe other files in cùng subdir cùng slot (tránh discover pick file cũ).
    for sibling in dest.parent.glob(f"{dest.stem.split('_')[0]}*{dest.suffix}"):
        if sibling != dest:
            try:
                sibling.unlink()
            except OSError:
                pass
    written = 0
    with dest.open("wb") as f:
        while chunk := upload.file.read(1024 * 1024):
            written += len(chunk)
            if written > MAX_UPLOAD_BYTES:
                f.close()
                dest.unlink(missing_ok=True)
                limit_mb = MAX_UPLOAD_BYTES // 1024 // 1024
                raise HTTPException(status_code=413, detail=f"File quá lớn (>{limit_mb}MB)")
            f.write(chunk)
    return written


@router.get("/companies/new", response_class=HTMLResponse)
def new_company_form(
    request: Request,
    error: str | None = Query(default=None),
    user: SessionUser = Depends(require_user),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "new_company.html", {"user": user, "error": error, "form": {}}
    )


@router.post("/companies", response_model=None)
def create_company(
    request: Request,
    code: str = Form(...),
    name: str = Form(""),
    tax_id: str = Form(""),
    address: str = Form(""),
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> HTMLResponse | RedirectResponse:
    code = code.strip().upper()
    name = name.strip()
    tax_id = tax_id.strip() or None
    address = address.strip() or None

    form_state = {"code": code, "name": name, "tax_id": tax_id or "", "address": address or ""}

    def _err(msg: str) -> HTMLResponse:
        return templates.TemplateResponse(
            request, "new_company.html",
            {"user": user, "error": msg, "form": form_state},
            status_code=400,
        )

    if not CODE_RE.match(code):
        return _err("Mã DN không hợp lệ. Chỉ dùng chữ HOA + số + _ - (bắt đầu bằng chữ, tối đa 31 ký tự).")
    if db.scalar(select(Company).where(Company.code == code)) is not None:
        return _err(f"Mã DN '{code}' đã tồn tại.")

    # Demo mode: force (Demo) suffix vào tên — tránh nhầm với DN thật.
    display_name = name or code
    if DEMO_SUFFIX not in display_name:
        display_name = f"{display_name} {DEMO_SUFFIX}"

    company = Company(code=code, name=display_name, tax_id=tax_id, address=address, risk_score=0)
    db.add(company)
    db.commit()

    return RedirectResponse(url=f"/companies/{code}/upload", status_code=303)


@router.get("/companies/{code}/upload", response_class=HTMLResponse)
def upload_form(
    code: str,
    request: Request,
    year: int | None = Query(default=None),
    error: str | None = Query(default=None),
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    company = db.scalar(select(Company).where(Company.code == code))
    if company is None:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy DN {code}")
    return templates.TemplateResponse(
        request, "upload_data.html",
        {
            "user": user,
            "company": company,
            "year": year or 2024,
            "year_min": YEAR_MIN,
            "year_max": YEAR_MAX,
            "error": error,
        },
    )


@router.post("/companies/{code}/upload", response_model=None)
def upload_data(
    code: str,
    request: Request,
    year: int = Form(...),
    m15: UploadFile | None = File(default=None),
    m15a: UploadFile | None = File(default=None),
    m16: UploadFile | None = File(default=None),
    bcct: UploadFile | None = File(default=None),
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    company = db.scalar(select(Company).where(Company.code == code))
    if company is None:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy DN {code}")
    if not (YEAR_MIN <= year <= YEAR_MAX):
        raise HTTPException(status_code=400, detail=f"Năm phải trong khoảng {YEAR_MIN}-{YEAR_MAX}")

    base = Path(settings.raw_data_path) / code / str(year)
    saved_any = False
    uploads = {"m15": m15, "m15a": m15a, "m16": m16, "bcct": bcct}
    for slot, upload in uploads.items():
        if not upload or not upload.filename:
            continue
        ext = Path(upload.filename).suffix.lower()
        if ext not in {".xls", ".xlsx"}:
            raise HTTPException(status_code=400, detail=f"{slot}: chỉ chấp nhận .xls / .xlsx (gặp {ext})")
        subdir, stem = _UPLOAD_SLOTS[slot]
        dest = base / subdir / f"{stem}_{year}{ext}"
        _save_upload(upload, dest)
        saved_any = True

    if not saved_any:
        return RedirectResponse(
            url=f"/companies/{code}/upload?year={year}&error=Ch%C6%B0a+ch%E1%BB%8Dn+file+n%C3%A0o",
            status_code=303,
        )

    # Ingest + run checks ngay (sync, vài giây với 16 check).
    try:
        run_ingest(code, year, raw_root=Path(settings.raw_data_path))
        run_check_pipeline(code, year)
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=f"Discover lỗi: {e}") from e
    except Exception as e:  # noqa: BLE001 — show parser/check errors back to user
        raise HTTPException(status_code=500, detail=f"Pipeline lỗi: {type(e).__name__}: {e}") from e

    return RedirectResponse(url=f"/companies/{code}?year={year}", status_code=303)


@router.post("/companies/{code}/run-checks", response_model=None)
def rerun_checks(
    code: str,
    year: int | None = Form(default=None),
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Enqueue job chạy checks.

    Nếu có `year` → RUN_CHECKS đơn lẻ (CLI/dev). Mặc định không gửi year →
    BATCH_RUN chạy tất cả năm có dữ liệu (UI default per design 2026-05-26).
    """
    from app.auth_users import get_user_by_username
    from app.jobs import enqueue_job
    from app.models.job import JobKind

    company = db.scalar(select(Company).where(Company.code == code))
    if company is None:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy DN {code}")

    user_row = get_user_by_username(db, user.name)
    if user_row is None:
        raise HTTPException(status_code=403, detail="Session user không tồn tại")

    if year is None:
        job = enqueue_job(
            db,
            kind=JobKind.BATCH_RUN,
            payload={"company_code": code},
            created_by=user_row.id,
            company_id=company.id,
            period_year=None,
        )
    else:
        job = enqueue_job(
            db,
            kind=JobKind.RUN_CHECKS,
            payload={"company_code": code, "year": year},
            created_by=user_row.id,
            company_id=company.id,
            period_year=year,
        )
    return RedirectResponse(url=f"/jobs/{job.id}", status_code=303)


@router.get("/companies/{code}", response_class=HTMLResponse)
def company_detail(
    code: str,
    request: Request,
    year: int | None = Query(default=None),
    user: SessionUser = Depends(require_user),
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

    year_score = None
    if selected_year is not None:
        year_score = db.scalar(
            select(CompanyYearScore).where(
                CompanyYearScore.company_id == company.id,
                CompanyYearScore.period_year == selected_year,
            )
        )

    all_specs = get_all_specs(db)

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
            "year_score": year_score,
            "all_specs": all_specs,
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
    user: SessionUser = Depends(require_user),
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
        # cls: num/date/code-cell/item-link/wrap/"" — quyết định alignment + format + clamp.
        # item-link: code-cell + link đến /companies/{code}/items/{value} page.
        "view_cols": [
            ("row_no", "STT", "num"),
            ("material_code", "Mã NVL", "item-link"),
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
            ("product_code", "Mã TP", "item-link"),
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
            ("product_code", "Mã SP", "item-link"),
            ("product_name", "Tên SP", "wrap"),
            ("product_unit", "ĐVT SP", ""),
            ("material_code", "Mã NVL", "item-link"),
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
            ("item_code", "Mã hàng", "item-link"),
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
    user: SessionUser = Depends(require_user),
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


_KIND_LABEL_VI = {
    "nvl": "Nguyên vật liệu",
    "tp": "Thành phẩm",
    "both": "Nguyên vật liệu & Thành phẩm",
    "unknown": "Chưa xác định loại",
}


@router.get("/companies/{code}/items/{item_code}", response_class=HTMLResponse)
def item_detail(
    code: str,
    item_code: str,
    request: Request,
    year: str | None = Query(default=None, description='Năm hoặc "all" để xem toàn bộ'),
    kind: str | None = Query(default=None, description="Override: nvl|tp khi mã trùng"),
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    company = db.scalar(select(Company).where(Company.code == code))
    if company is None:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy DN {code}")

    detected_kind = detect_item_kind(db, company.id, item_code)
    years = item_years(db, company.id, item_code)
    # Nếu cả BCQT lẫn BCCT đều rỗng → 404 thật.
    if detected_kind == "unknown" and not years:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy mã {item_code} ở DN {code}")

    # Resolve display kind: override → detected → fallback to nvl/tp ordering.
    effective_kind = kind if kind in ("nvl", "tp") else detected_kind
    if effective_kind == "both":
        effective_kind = "nvl"  # default tab when both; UI offers toggle.

    if year == "all":
        selected_year: int | None = None
    elif year is None:
        selected_year = years[-1] if years else None
    else:
        try:
            selected_year = int(year)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Năm không hợp lệ: {year}") from None

    # Build per-year summary (full series for sparkline + cross-year tables).
    if effective_kind == "tp":
        yearly = sp_yearly_summary(db, company.id, item_code)
        item_name_row = db.scalar(
            select(SpBalance).where(
                SpBalance.company_id == company.id,
                SpBalance.product_code == item_code,
            )
        )
    else:
        yearly = nvl_yearly_summary(db, company.id, item_code)
        item_name_row = db.scalar(
            select(NvlBalance).where(
                NvlBalance.company_id == company.id,
                NvlBalance.material_code == item_code,
            )
        )

    item_name = None
    unit = None
    if item_name_row is not None:
        item_name = getattr(item_name_row, "material_name", None) or getattr(
            item_name_row, "product_name", None
        )
        unit = item_name_row.unit

    selected_yearly = next((r for r in yearly if r["year"] == selected_year), None)

    # BCCT detail lines for selected year (limit 200 to keep page light).
    bcct_lines: list = []
    if selected_year is not None:
        all_lines = bcct_lines_for_item(db, company.id, item_code, year=selected_year)
        bcct_lines = all_lines[:200]

    # BOM edges per year for selected_year.
    bom_rows: list[dict] = []
    bom_sankey: list[tuple[str, float, str]] = []
    if selected_year is not None:
        if effective_kind == "tp":
            bom_rows = bom_edges_for_tp(db, company.id, item_code, year=selected_year)
            bom_sankey = [
                (b["material_code"], b["norm_qty"], b.get("material_name") or "")
                for b in bom_rows
            ]
        else:
            bom_rows = bom_edges_for_nvl(db, company.id, item_code, year=selected_year)
            bom_sankey = [
                (b["product_code"], b["norm_qty"], b.get("product_name") or "")
                for b in bom_rows
            ]

    # Findings keyed by subject_key = item_code in selected year.
    findings_rows: list[Finding] = []
    if selected_year is not None:
        findings_rows = list(
            db.scalars(
                select(Finding).where(
                    Finding.company_id == company.id,
                    Finding.period_year == selected_year,
                    Finding.subject_key == item_code,
                )
            ).all()
        )

    # Hero band totals across all years.
    total_import_qty = sum(r.get("bcct_import_qty", 0.0) for r in yearly)
    total_export_qty = sum(r.get("bcct_export_qty", 0.0) for r in yearly)
    total_production = (
        sum(r.get("production_out_qty", 0.0) for r in yearly)
        if effective_kind == "nvl"
        else 0.0
    )
    last_closing = yearly[-1]["closing_qty"] if yearly else 0.0
    prev_closing = yearly[-2]["closing_qty"] if len(yearly) >= 2 else None
    closing_delta_pct = None
    if prev_closing is not None and prev_closing != 0:
        closing_delta_pct = (last_closing - prev_closing) / abs(prev_closing) * 100

    # Chart layouts (server-rendered SVG).
    sparkline = sparkline_points([r["closing_qty"] for r in yearly]) if len(yearly) >= 2 else None
    waterfall = None
    if selected_yearly is not None:
        sy = selected_yearly
        if effective_kind == "tp":
            steps = [
                ("Đầu kỳ", sy["opening_qty"], "opening"),
                ("Nhập kho", sy["intake_qty"], "in"),
                ("Tự CN khác", -sy["repurpose_qty"], "out"),
                ("Xuất khẩu", -sy["export_qty"], "out"),
                ("Khác", -sy["other_out_qty"], "out"),
                ("Cuối kỳ", sy["closing_qty"], "closing"),
            ]
        else:
            steps = [
                ("Đầu kỳ", sy["opening_qty"], "opening"),
                ("Nhập", sy["import_qty"], "in"),
                ("Tái xuất", -sy["reexport_qty"], "out"),
                ("Tự CN", -sy["repurpose_qty"], "out"),
                ("Đưa vào SX", -sy["production_out_qty"], "out"),
                ("Khác", -sy["other_out_qty"], "out"),
                ("Cuối kỳ", sy["closing_qty"], "closing"),
            ]
        waterfall = waterfall_layout(steps)

    sankey = None
    if bom_sankey:
        sankey = sankey_layout(
            item_code,
            bom_sankey,
            direction="in" if effective_kind == "tp" else "out",
        )

    # BCCT-only items (no BCQT row anywhere) → warn banner.
    bcct_only = detected_kind == "unknown" and bool(years)
    # Mismatch counts for cross-year section.
    io_field = "export_match" if effective_kind == "tp" else "import_match"
    mismatch_years = [
        r["year"]
        for r in yearly
        if not r.get(io_field, True) or not r.get("balance_match", True)
    ]

    return templates.TemplateResponse(
        request,
        "item_detail.html",
        {
            "user": user,
            "company": company,
            "item_code": item_code,
            "item_name": item_name,
            "unit": unit,
            "kind": effective_kind,
            "detected_kind": detected_kind,
            "kind_label": _KIND_LABEL_VI.get(effective_kind, effective_kind),
            "years": years,
            "selected_year": selected_year,
            "yearly": yearly,
            "selected_yearly": selected_yearly,
            "bcct_lines": bcct_lines,
            "bom_rows": bom_rows,
            "bom_sankey": bom_sankey,
            "sparkline_layout": sparkline,
            "waterfall_layout": waterfall,
            "sankey_layout": sankey,
            "findings_rows": findings_rows,
            "total_import_qty": total_import_qty,
            "total_export_qty": total_export_qty,
            "total_production": total_production,
            "last_closing": last_closing,
            "closing_delta_pct": closing_delta_pct,
            "bcct_only": bcct_only,
            "mismatch_years": mismatch_years,
            "classify_operation": classify_operation,
            "operation_label": operation_label,
            "kinds_available": ["nvl", "tp"] if detected_kind == "both" else [],
        },
    )


@router.get("/findings/{finding_id}", response_class=HTMLResponse)
def finding_detail(
    finding_id: int,
    request: Request,
    user: SessionUser = Depends(require_user),
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
    user: SessionUser = Depends(require_user),
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
