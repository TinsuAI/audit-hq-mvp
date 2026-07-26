"""Routes for browsing companies and their findings (Tầng 2 viewer)."""

from __future__ import annotations

import json as _json
import re
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote_plus

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.app_settings import get_combos_enabled
from app.audit import (
    ACTION_DOWNLOAD,
    ACTION_EXPORT,
    ACTION_RUN_CHECKS,
    log_access,
)
from app.auth import SessionUser, require_user
from app.books import (
    BOOK_LABELS,
    book_label,
    book_summary,
    company_books,
    is_multi_book,
    normalize_book,
)
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
    CompanyPeriod,
    CompanyYearScore,
    DataFile,
    DataFileStatus,
    DeclarationLine,
    Finding,
    Norm,
    NvlBalance,
    SpBalance,
)
from app.models.data_file import SETTLEMENT_SLOTS, SLOT_LABEL_VI, SLOT_ORDER
from app.pipeline.export import build_export
from app.pipeline.ingest import IngestPlanError
from app.pipeline.ingest import ingest as run_ingest
from app.pipeline.period import load_period_windows
from app.pipeline.validate import diagnose_upload
from app.scoping import allowed_company_ids, can_access_company_id, get_company_or_404
from app.settings import settings
from app.slugs import slugify_name, unique_slug
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
# Nhãn sổ quyết toán (book) — dùng ở company_detail (split line) + finding_detail (field).
templates.env.globals["book_label"] = book_label

# Trang DN chỉ xem trước vài dòng mỗi kiểm tra; xem đủ thì mở riêng từng kiểm tra.
_PREVIEW_PER_GROUP = 15
_PAGE_SIZE = 100

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

# Nhãn cho trang quản lý tài liệu (ma trận năm × loại file BCQT).
templates.env.globals["SLOT_LABEL_VI"] = SLOT_LABEL_VI
templates.env.globals["SLOT_ORDER"] = list(SLOT_ORDER)
# Trục lifecycle (ADR #18): uploaded → analyzed → parsed (+ error). Cờ review
# (verified/needs_review) là trục RIÊNG, render bằng badge khác. "warning" giữ lại
# làm nhãn dự phòng cho dòng registry cũ (không code path nào ghi mới).
DATA_FILE_STATUS_LABEL = {
    "pending": "Đã tải lên",
    "analyzed": "Đã phân tích",
    "ok": "Đã nạp",
    "warning": "Cảnh báo",
    "error": "Lỗi",
}
DATA_FILE_STATUS_BADGE = {
    "pending": "muted",
    "analyzed": "info",
    "ok": "info",
    "warning": "warning",
    "error": "critical",
}
templates.env.globals["DATA_FILE_STATUS_LABEL"] = DATA_FILE_STATUS_LABEL
templates.env.globals["DATA_FILE_STATUS_BADGE"] = DATA_FILE_STATUS_BADGE


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
    # Officer chỉ thấy DN được phân công; admin (allowed=None) thấy tất cả.
    allowed = allowed_company_ids(db, user)
    stmt = select(Company)
    if allowed is not None:
        stmt = stmt.where(Company.id.in_(allowed))
    companies = db.scalars(stmt).all()
    # Điểm hiển thị = max(company_year_scores), KHÔNG đọc cache company.risk_score.
    # Cache có thể "drift" khỏi điểm theo năm (đổi rule/chạy lẻ không recompute) →
    # đọc thẳng từ CYS để list luôn khớp trang chi tiết.
    max_scores = dict(
        db.execute(
            select(CompanyYearScore.company_id, func.max(CompanyYearScore.score))
            .group_by(CompanyYearScore.company_id)
        ).all()
    )
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
            "score": max_scores.get(c.id) or 0,
            "years": sorted(years.items(), reverse=True),
        })
    summary.sort(key=lambda s: (-s["score"], s["company"].code))

    # Thang hạng cho thẻ giải thích — đọc ngưỡng runtime (admin có thể chỉnh),
    # không hardcode trong template để khỏi lệch khi đổi ngưỡng.
    from app.app_settings import get_tiers
    from app.checks.denominators import RULE_SCOPE
    tier_ladder = []
    lo = 0
    for upper, label, css in get_tiers(db):
        tier_ladder.append({"lo": lo, "hi": upper, "label": label, "css": css})
        lo = upper + 1

    return templates.TemplateResponse(
        request,
        "companies_list.html",
        {
            "user": user,
            "summary": summary,
            "n_rules": len(RULE_SCOPE),
            "tier_ladder": tier_ladder,
        },
    )


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


# Cột KHOÁ (mã hàng) mỗi slot — evidence_refs của mọi finding trên slot lọc theo cột
# này. Đổi map cột khoá trên file đã `parsed` → chạy lại MỌI check đọc slot (không chỉ
# check đọc cột khoá) để không để C2.1/C2.2 lại finding treo (ADR #18).
_SLOT_KEY_FIELD = {"m15": "material_code", "m15a": "product_code", "m16": "material_code"}


def _group_options_by_family(options: list[dict], specs: dict) -> list[dict]:
    """Gom option chọn-test theo họ (C1/C2/…) + tiêu đề nhóm §4 đề án.

    COMBO_* và X.* (mở rộng) gom về nhóm riêng, xếp cuối. Trả list
    `{"title", "options"}` đã sắp theo số nhóm rồi mã họ.
    """
    from app.catalog_full import GROUP_NAMES

    buckets: dict[str, dict] = {}
    for opt in options:
        code = opt["code"]
        if code.startswith("COMBO_"):
            key, title, order = "COMBO", "Phát hiện kết hợp", (100, "")
        elif code.startswith("X."):
            key, title, order = "X", "Kiểm tra mở rộng", (99, "")
        else:
            spec = specs.get(code)
            group = spec.group if spec else 0
            fam = code.split(".")[0]
            name = GROUP_NAMES.get(group, "Khác")
            key, title, order = fam, f"{fam} · {name}", (group, fam)
        bucket = buckets.setdefault(key, {"title": title, "order": order, "options": []})
        bucket["options"].append(opt)
    ordered = sorted(buckets.values(), key=lambda b: b["order"])
    return [{"title": b["title"], "options": b["options"]} for b in ordered]


# Magic-byte chữ ký Excel — chặn file đổi đuôi (vd .txt → .xlsx) trước khi lưu.
_XLSX_MAGIC = b"PK\x03\x04"        # OOXML = zip container
_XLS_MAGIC = b"\xd0\xcf\x11\xe0"   # BIFF/OLE2 compound document


def _looks_like_excel(head: bytes, ext: str) -> bool:
    if ext == ".xlsx":
        return head.startswith(_XLSX_MAGIC)
    if ext == ".xls":
        return head.startswith(_XLS_MAGIC)
    return False


def _write_upload_stream(upload: UploadFile, dest: Path, expected_ext: str | None = None) -> int:
    """Ghi 1 upload ra `dest` theo chunk, enforce giới hạn dung lượng. KHÔNG đụng
    file khác — caller tự quyết việc thay/giữ file cũ (an toàn, không glob mù).

    `expected_ext` (.xls/.xlsx) → kiểm magic-byte chunk đầu, chặn file đổi đuôi.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    first = True
    with dest.open("wb") as f:
        while chunk := upload.file.read(1024 * 1024):
            if first:
                first = False
                if expected_ext and not _looks_like_excel(chunk[:8], expected_ext):
                    f.close()
                    dest.unlink(missing_ok=True)
                    raise HTTPException(
                        status_code=400,
                        detail=f"Nội dung file không đúng định dạng {expected_ext} "
                               "(có thể bị đổi đuôi). Hãy tải lên đúng file Excel.",
                    )
            written += len(chunk)
            if written > MAX_UPLOAD_BYTES:
                f.close()
                dest.unlink(missing_ok=True)
                limit_mb = MAX_UPLOAD_BYTES // 1024 // 1024
                raise HTTPException(status_code=413, detail=f"File quá lớn (>{limit_mb}MB)")
            f.write(chunk)
    return written


def _save_upload(upload: UploadFile, dest: Path, slot: str) -> int:
    """Lưu upload vào slot canonical (multi-slot form): thay file CÙNG SLOT đã có.

    Dọn theo phân loại slot (`_classify_slot`) thay vì glob prefix — glob cũ
    `M15*` còn xoá nhầm `M15a*` (cùng slot khác nhau trong BCQT/)."""
    from app.pipeline.data_files import _classify_slot

    subdir = dest.parent.name
    for p in list(dest.parent.glob("*")):
        if (
            p.is_file()
            and p.suffix.lower() in {".xls", ".xlsx"}
            and _classify_slot(subdir, p.name) == slot
        ):
            p.unlink(missing_ok=True)
    return _write_upload_stream(upload, dest, expected_ext=dest.suffix.lower())


@router.get("/companies/new", response_class=HTMLResponse)
def new_company_form(
    request: Request,
    error: str | None = Query(default=None),
    user: SessionUser = Depends(require_user),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "new_company.html", {"user": user, "error": error, "form": {}}
    )


def _next_company_code(db: Session) -> str:
    """Tự sinh mã DN kế tiếp dạng DN_NNN (khoá nội bộ cho URL + thư mục file).

    Người dùng không phải nhập mã — định danh thật là Tên DN + MST.
    """
    nums = []
    for c in db.scalars(select(Company.code).where(Company.code.like("DN\\_%", escape="\\"))).all():
        m = re.match(r"^DN_(\d+)$", c)
        if m:
            nums.append(int(m.group(1)))
    return f"DN_{(max(nums) + 1) if nums else 1:03d}"


@router.post("/companies", response_model=None)
def create_company(
    request: Request,
    name: str = Form(""),
    tax_id: str = Form(""),
    address: str = Form(""),
    industry: str = Form(""),
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> HTMLResponse | RedirectResponse:
    name = name.strip()
    tax_id = tax_id.strip() or None
    address = address.strip() or None
    industry = industry.strip() or None

    form_state = {
        "name": name, "tax_id": tax_id or "",
        "address": address or "", "industry": industry or "",
    }

    def _err(msg: str) -> HTMLResponse:
        return templates.TemplateResponse(
            request, "new_company.html",
            {"user": user, "error": msg, "form": form_state},
            status_code=400,
        )

    if not name:
        return _err("Vui lòng nhập Tên doanh nghiệp.")

    # Demo mode: force (Demo) suffix vào tên — tránh nhầm với DN thật.
    display_name = name
    if DEMO_SUFFIX not in display_name:
        display_name = f"{display_name} {DEMO_SUFFIX}"

    code = _next_company_code(db)  # mã lưu trữ tự sinh (khoá file/AI), không nhận từ form
    slug = unique_slug(db, slugify_name(name))  # định danh URL có nghĩa từ tên
    company = Company(
        code=code, slug=slug, name=display_name, tax_id=tax_id, address=address,
        industry=industry, risk_score=0,
    )
    db.add(company)
    db.flush()

    # Tự phân công người tạo cho DN mới — nếu là officer, tạo xong vẫn thấy được
    # (admin thấy mọi DN nên không cần, nhưng gán cũng vô hại).
    from app.auth_users import get_user_by_username
    creator = get_user_by_username(db, user.name)
    if creator is not None and company not in creator.companies:
        creator.companies.append(company)
    db.commit()

    return RedirectResponse(url=f"/companies/{slug}/documents", status_code=303)


@router.get("/companies/{code}/edit", response_class=HTMLResponse)
def edit_company_form(
    code: str,
    request: Request,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    company = get_company_or_404(db, code, user)
    form_state = {
        "code": company.code,
        "name": company.name or "",
        "tax_id": company.tax_id or "",
        "address": company.address or "",
        "industry": company.industry or "",
    }
    return templates.TemplateResponse(
        request, "edit_company.html",
        {"user": user, "company": company, "form": form_state, "error": None},
    )


@router.post("/companies/{code}/edit", response_model=None)
def update_company(
    code: str,
    request: Request,
    name: str = Form(""),
    tax_id: str = Form(""),
    address: str = Form(""),
    industry: str = Form(""),
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    company = get_company_or_404(db, code, user)

    # Mã DN cố định (dùng làm thư mục lưu file) — không nhận từ form.
    name = name.strip()
    display_name = name or company.code
    if DEMO_SUFFIX not in display_name:  # giữ hậu tố (Demo) nhất quán với lúc tạo
        display_name = f"{display_name} {DEMO_SUFFIX}"

    company.name = display_name
    company.tax_id = tax_id.strip() or None
    company.address = address.strip() or None
    company.industry = industry.strip() or None
    db.commit()

    return RedirectResponse(url=f"/companies/{code}", status_code=303)


@router.get("/companies/{code}/upload", response_class=HTMLResponse)
def upload_form(
    code: str,
    request: Request,
    year: int | None = Query(default=None),
    error: str | None = Query(default=None),
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    company = get_company_or_404(db, code, user)
    from datetime import date
    selected = year or date.today().year
    return templates.TemplateResponse(
        request, "upload_data.html",
        {
            "user": user,
            "company": company,
            "year": selected,
            "year_options": _year_options(selected),
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
    company = get_company_or_404(db, code, user)
    if not (YEAR_MIN <= year <= YEAR_MAX):
        raise HTTPException(status_code=400, detail=f"Năm phải trong khoảng {YEAR_MIN}-{YEAR_MAX}")

    base = Path(settings.raw_data_path) / company.code / str(year)
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
        _save_upload(upload, dest, slot)
        saved_any = True

    if not saved_any:
        return RedirectResponse(
            url=f"/companies/{code}/upload?year={year}&error=Ch%C6%B0a+ch%E1%BB%8Dn+file+n%C3%A0o",
            status_code=303,
        )

    # Cập nhật registry file ngay sau khi lưu (kể cả khi sắp báo lỗi chẩn đoán).
    from app.pipeline.data_files import (
        record_parse_result,
        should_stop_for_review,
        sync_data_files,
        year_review_gate,
    )
    sync_data_files(db, company)

    # CHẨN ĐOÁN trước khi nạp — chống misparse thầm lặng (file HQ sai mẫu/lệch cột).
    diagnosis = diagnose_upload(company.code, year, Path(settings.raw_data_path))
    if diagnosis.has_errors:
        from app.ai.config import get_setting
        from app.pipeline.ingest import IngestStats
        record_parse_result(
            db, company, year, IngestStats(company_code=company.code, period_year=year), diagnosis,
        )
        try:
            ai_enabled = bool(get_setting("enabled")) and bool(get_setting("api_key"))
        except Exception:  # noqa: BLE001 — AI optional, đừng để lỗi config chặn upload
            ai_enabled = False
        return templates.TemplateResponse(
            request, "upload_data.html",
            {
                "user": user, "company": company, "year": year,
                "year_options": _year_options(year),
                "year_min": YEAR_MIN, "year_max": YEAR_MAX, "error": None,
                "diagnosis": diagnosis, "ai_enabled": ai_enabled,
            },
            status_code=422,
        )

    # Cổng review (ADR #18): dry-run parse trước để tính bằng chứng + review mỗi cột,
    # CHƯA ghi dòng. Mọi cột `verified` → tự advance sang parsed (đường whitelist chảy
    # suốt); có cột `needs_review` → DỪNG ở `analyzed`, cán bộ bấm "Nạp dữ liệu" để
    # tiếp (cảnh báo, không chặn — check vẫn chạy sau khi parsed).
    raw_path = Path(settings.raw_data_path)
    try:
        analyze_stats = run_ingest(company.code, year, raw_root=raw_path, dry_run=True)
    except FileNotFoundError as e:
        raise HTTPException(status_code=400, detail=f"Discover lỗi: {e}") from e
    except Exception as e:  # noqa: BLE001 — show parser errors back to user
        raise HTTPException(status_code=500, detail=f"Phân tích file lỗi: {type(e).__name__}: {e}") from e
    record_parse_result(db, company, year, analyze_stats, diagnosis, committed=False)

    gate = year_review_gate(db, company, year)
    if should_stop_for_review(gate):
        return RedirectResponse(
            url=(
                f"/companies/{code}/documents?msg=%C4%90%C3%A3+t%E1%BA%A3i+l%C3%AAn+%26"
                f"+ph%C3%A2n+t%C3%ADch+n%C4%83m+{year}+%E2%80%94+c%E1%BA%A7n+x%C3%A1c"
                f"+nh%E1%BA%ADn+c%E1%BB%99t+tr%C6%B0%E1%BB%9Bc+khi+n%E1%BA%A1p"
            ),
            status_code=303,
        )

    # Tự advance: NẠP dữ liệu (commit). KHÔNG tự chạy kiểm tra (bước riêng).
    try:
        stats = run_ingest(company.code, year, raw_root=raw_path)
    except IngestPlanError as e:
        # Kế hoạch nạp bị từ chối (gán sổ nửa vời / thiếu file đã đăng ký) — việc cán bộ
        # phải xử lý ở trang tài liệu, không phải lỗi hệ thống. File đã tải lên + đăng ký;
        # kế hoạch bị từ chối TRƯỚC lệnh xoá nên dữ liệu cũ nguyên vẹn.
        return RedirectResponse(
            url=f"/companies/{code}/documents?error="
            + quote_plus(f"Đã tải lên, CHƯA nạp dữ liệu. {e}"),
            status_code=303,
        )
    except Exception as e:  # noqa: BLE001 — show parser errors back to user
        raise HTTPException(status_code=500, detail=f"Nạp dữ liệu lỗi: {type(e).__name__}: {e}") from e

    record_parse_result(db, company, year, stats, diagnosis)
    return RedirectResponse(
        url=f"/companies/{code}/documents?msg=%C4%90%C3%A3+t%E1%BA%A3i+l%C3%AAn+%26+n%E1%BA%A1p+d%E1%BB%AF+li%E1%BB%87u+n%C4%83m+{year}",
        status_code=303,
    )


@router.post("/companies/{code}/diagnose-ai", response_model=None)
def diagnose_ai(
    code: str,
    request: Request,
    year: int = Form(...),
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Nhờ AI chẩn đoán cấu trúc file khi nạp lỗi (escalation của validate)."""
    company = get_company_or_404(db, code, user)

    from app.ai.config import get_setting
    from app.ai.limits import check_daily_budget, check_rate_limit

    if not (get_setting("enabled") and get_setting("api_key")):
        raise HTTPException(status_code=503, detail="AI assistant đang tắt. Bật trong /admin/ai.")
    check_rate_limit(user.name, db)
    check_daily_budget(db)

    raw_root = Path(settings.raw_data_path)
    diagnosis = diagnose_upload(company.code, year, raw_root)
    try:
        from app.ai.ingest_doctor import diagnose_with_ai
        ai_result = diagnose_with_ai(company.code, year, raw_root)
    except Exception as e:  # noqa: BLE001 — AI lỗi không được làm sập trang
        ai_result = f"Không gọi được AI: {type(e).__name__}: {e}"

    return templates.TemplateResponse(
        request, "upload_data.html",
        {
            "user": user, "company": company, "year": year,
            "year_options": _year_options(year),
            "year_min": YEAR_MIN, "year_max": YEAR_MAX, "error": None,
            "diagnosis": diagnosis, "ai_enabled": True, "ai_result": ai_result,
        },
    )


# ---------------------------------------------------------------------------
# Quản lý tài liệu (documents) — ma trận năm × loại file BCQT
# ---------------------------------------------------------------------------


def _human_size(n: int | None) -> str:
    if not n:
        return "—"
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def _data_years(db: Session, company_id: int) -> set[int]:
    """Năm có dữ liệu Tầng 1 đã nạp (gộp 4 bảng)."""
    years: set[int] = set()
    for model in (NvlBalance, SpBalance, Norm, DeclarationLine):
        years |= set(
            db.scalars(
                select(model.period_year).where(model.company_id == company_id).distinct()
            ).all()
        )
    return years


# Mỗi loại tài liệu BCQT ↔ 1 bảng Tầng 1 (để đếm "đã nạp mấy loại").
_SLOT_MODELS = {
    "m15": NvlBalance,
    "m15a": SpBalance,
    "m16": Norm,
    "bcct": DeclarationLine,
}


def _slot_row_counts(db: Session, company_id: int, year: int) -> dict[str, int]:
    """Số dòng Tầng 1 đã nạp theo TỪNG loại tài liệu cho (DN, năm)."""
    return {
        slot: db.scalar(
            select(func.count()).select_from(model).where(
                model.company_id == company_id, model.period_year == year
            )
        ) or 0
        for slot, model in _SLOT_MODELS.items()
    }


def _year_options(selected: int | None = None) -> list[int]:
    """Danh sách năm gần đây cho dropdown chọn năm (gồm năm đang chọn nếu lệch range)."""
    from datetime import date
    this_year = date.today().year
    opts = [y for y in range(this_year, this_year - 9, -1) if YEAR_MIN <= y <= YEAR_MAX]
    if selected and selected not in opts and YEAR_MIN <= selected <= YEAR_MAX:
        opts = sorted(set(opts) | {selected}, reverse=True)
    return opts


def _doc_year_status(
    has_files: bool,
    has_data: bool,
    total_rows: int,
    loaded_types: int = 0,
    total_types: int = len(SLOT_ORDER),
) -> tuple[str, str]:
    """Một nhãn trạng thái DUY NHẤT cho 1 năm.

    'Đã nạp' (trơn) CHỈ khi đủ cả `total_types` loại tài liệu. Nạp thiếu loại →
    'Đã nạp một phần · X/Y loại' để không hiểu nhầm nạp 1 loại = đã xong cả năm."""
    if has_data:
        if has_files:
            if loaded_types >= total_types:
                return f"Đã nạp · {total_rows:,} dòng", "ok"
            return (
                f"Đã nạp một phần · {loaded_types}/{total_types} loại · {total_rows:,} dòng",
                "warn",
            )
        return "Đã nạp trước đó · file gốc không còn lưu", "warn"
    if has_files:
        return "Có file · chưa nạp", "pending"
    return "Chưa có dữ liệu", "empty"


def _resolve_within_root(rel_path: str) -> Path:
    """Resolve stored_path tuyệt đối, đảm bảo nằm trong raw_data_path (chống traversal)."""
    raw_root = Path(settings.raw_data_path).resolve()
    abs_path = (raw_root / rel_path).resolve()
    if raw_root not in abs_path.parents and abs_path != raw_root:
        raise HTTPException(status_code=400, detail="Đường dẫn file không hợp lệ")
    return abs_path


@router.get("/companies/{code}/documents", response_class=HTMLResponse)
def company_documents(
    code: str,
    request: Request,
    msg: str | None = Query(default=None),
    error: str | None = Query(default=None),
    add: int | None = Query(default=None),
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    company = get_company_or_404(db, code, user)

    from app.pipeline.data_files import (
        files_by_year_slot,
        review_gate_for_files,
        sync_data_files,
    )

    # Reconcile registry với filesystem (bắt file demo có sẵn / xoá ngoài app).
    sync_data_files(db, company)
    matrix = files_by_year_slot(db, company)

    data_years = _data_years(db, company.id)
    finding_years = set(
        db.scalars(
            select(Finding.period_year).where(Finding.company_id == company.id).distinct()
        ).all()
    )
    score_rows = db.scalars(
        select(CompanyYearScore).where(CompanyYearScore.company_id == company.id)
    ).all()
    scores = {r.period_year: r for r in score_rows}
    period_rows = {
        r.period_year: r
        for r in db.scalars(
            select(CompanyPeriod).where(CompanyPeriod.company_id == company.id)
        ).all()
    }

    years = set(matrix) | data_years | finding_years | set(period_rows)
    # "+ Thêm năm" → hiển thị năm trống (chưa có gì) để upload vào.
    added_empty = add if (add and YEAR_MIN <= add <= YEAR_MAX and add not in years) else None
    if added_empty:
        years.add(added_empty)
    years = sorted(years, reverse=True)

    year_rows = []
    for i, y in enumerate(years):
        slots = {slot: matrix.get(y, {}).get(slot, []) for slot in SLOT_ORDER}
        has_files = any(slots.values())
        # Cổng review (ADR #18): cột `needs_review` + check bị ảnh hưởng — banner cảnh
        # báo, KHÔNG chặn (trục review độc lập lifecycle; file có thể parsed + cần xác nhận).
        review_gate = review_gate_for_files(
            f for slot_files in slots.values() for f in slot_files
        )
        has_data = y in data_years
        slot_counts = _slot_row_counts(db, company.id, y) if has_data else {}
        total_rows = sum(slot_counts.values())
        loaded_types = sum(1 for n in slot_counts.values() if n > 0)
        status_label, status_kind = _doc_year_status(
            has_files, has_data, total_rows, loaded_types
        )
        from datetime import date as _d

        cp = period_rows.get(y)
        pf_disp = cp.period_from if (cp and cp.period_from) else _d(y, 1, 1)
        pt_disp = cp.period_to if (cp and cp.period_to) else _d(y, 12, 31)
        period_custom = (pf_disp, pt_disp) != (_d(y, 1, 1), _d(y, 12, 31))
        year_rows.append({
            "year": y,
            "slots": slots,
            "has_files": has_files,
            "review_gate": review_gate,
            "has_data": has_data,
            "total_rows": total_rows,
            "status_label": status_label,
            "status_kind": status_kind,
            "checks_run": y in scores or y in finding_years,
            "score": scores[y].score if y in scores else None,
            "tier": scores[y].tier if y in scores else None,
            "period_from": pf_disp,
            "period_to": pt_disp,
            "period_manual": cp.is_manual if cp else False,
            "period_custom": period_custom,
            # Mở sẵn: năm vừa thêm, hoặc năm mới nhất nếu không thêm.
            "open": (y == added_empty) if added_empty else (i == 0),
        })

    # Năm có thể thêm: vài năm gần đây chưa có trong danh sách.
    from datetime import date
    this_year = date.today().year
    present = set(years)
    add_years = [
        y for y in range(this_year, this_year - 8, -1)
        if YEAR_MIN <= y <= YEAR_MAX and y not in present
    ]

    return templates.TemplateResponse(
        request,
        "company_documents.html",
        {
            "user": user,
            "company": company,
            "year_rows": year_rows,
            "add_years": add_years,
            "year_min": YEAR_MIN,
            "year_max": YEAR_MAX,
            "human_size": _human_size,
            "msg": msg,
            "error": error,
        },
    )


@router.post("/companies/{code}/documents/upload", response_model=None)
def documents_upload_cell(
    code: str,
    year: int = Form(...),
    slot: str = Form(...),
    file: UploadFile | None = File(default=None),
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Tải lên 1 ô (năm × loại). m15/m15a/m16 thay thế (1 file/ô); bcct cộng thêm."""
    company = get_company_or_404(db, code, user)
    if slot not in _UPLOAD_SLOTS:
        raise HTTPException(status_code=400, detail=f"Loại tài liệu không hợp lệ: {slot}")
    if not (YEAR_MIN <= year <= YEAR_MAX):
        raise HTTPException(status_code=400, detail=f"Năm phải trong khoảng {YEAR_MIN}-{YEAR_MAX}")

    def _redirect(params: str) -> RedirectResponse:
        return RedirectResponse(url=f"/companies/{code}/documents?{params}", status_code=303)

    if not file or not file.filename:
        return _redirect("error=Ch%C6%B0a+ch%E1%BB%8Dn+file")
    ext = Path(file.filename).suffix.lower()
    if ext not in {".xls", ".xlsx"}:
        return _redirect("error=Ch%E1%BB%89+ch%E1%BA%A5p+nh%E1%BA%ADn+.xls+/+.xlsx")

    raw_root = Path(settings.raw_data_path)
    subdir, stem = _UPLOAD_SLOTS[slot]
    dest_dir = raw_root / company.code / str(year) / subdir
    dest_dir.mkdir(parents=True, exist_ok=True)

    from app.pipeline.data_files import _classify_slot, sync_data_files

    if slot == "bcct":
        # Nhiều file/ô — giữ tên gốc đã làm sạch (thay nếu trùng tên).
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(file.filename).name).strip("_")
        dest = dest_dir / (safe_name or f"BCCT_{year}{ext}")
    else:
        # 1 file/ô — xoá file cùng slot đã có trên đĩa rồi ghi tên canonical.
        for p in list(dest_dir.glob("*")):
            if (
                p.is_file()
                and p.suffix.lower() in {".xls", ".xlsx"}
                and _classify_slot(subdir, p.name) == slot
            ):
                p.unlink(missing_ok=True)
        dest = dest_dir / f"{stem}_{year}{ext}"

    try:
        _write_upload_stream(file, dest, expected_ext=ext)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Lưu file lỗi: {e}") from e

    sync_data_files(db, company)
    # Gắn người tải cho dòng vừa tạo. Tên file lưu là tên canonical trên đĩa
    # (đảm bảo discover nhận diện đúng slot) — sync giữ tên này nhất quán.
    rel = str(dest.relative_to(raw_root))
    from app.auth_users import get_user_by_username
    row = db.scalar(select(DataFile).where(DataFile.company_id == company.id, DataFile.stored_path == rel))
    if row is not None:
        ur = get_user_by_username(db, user.name)
        row.uploaded_by = ur.id if ur else None
        db.commit()

    label = SLOT_LABEL_VI.get(slot, slot).split(" — ")[0]
    return _redirect(f"msg={label}+{year}+%C4%91%C3%A3+t%E1%BA%A3i+l%C3%AAn")


@router.post("/companies/{code}/documents/file/{file_id}/delete", response_model=None)
def documents_delete_file(
    code: str,
    file_id: int,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    company = get_company_or_404(db, code, user)
    row = db.get(DataFile, file_id)
    if row is None or row.company_id != company.id:
        raise HTTPException(status_code=404, detail="Không tìm thấy file")
    abs_path = _resolve_within_root(row.stored_path)
    abs_path.unlink(missing_ok=True)
    db.delete(row)
    db.commit()
    return RedirectResponse(
        url=f"/companies/{code}/documents?msg=%C4%90%C3%A3+xo%C3%A1+file",
        status_code=303,
    )


@router.get("/companies/{code}/documents/file/{file_id}/download")
def documents_download_file(
    code: str,
    file_id: int,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    company = get_company_or_404(db, code, user)
    row = db.get(DataFile, file_id)
    if row is None or row.company_id != company.id:
        raise HTTPException(status_code=404, detail="Không tìm thấy file")
    abs_path = _resolve_within_root(row.stored_path)
    if not abs_path.is_file():
        raise HTTPException(status_code=404, detail="File không còn trên đĩa")
    log_access(db, username=user.name, action=ACTION_DOWNLOAD,
               company_code=company.code, detail=row.original_filename)
    return FileResponse(
        path=abs_path,
        filename=row.original_filename,
        media_type="application/vnd.ms-excel",
    )


PREVIEW_ROWS = 100
PREVIEW_COLS = 40
# Grid preview nhúng trong màn xác nhận cột (WS1) — ít dòng để đối chiếu chỉ số cột.
REVIEW_PREVIEW_ROWS = 15


def _excel_col_letters(n: int) -> list[str]:
    """['A','B',…,'AA',…] cho n cột — nhãn cột kiểu Excel cho header preview."""
    out = []
    for i in range(n):
        s, x = "", i
        while True:
            s = chr(ord("A") + x % 26) + s
            x = x // 26 - 1
            if x < 0:
                break
        out.append(s)
    return out


def _extract_sheet_preview(
    abs_path: Path, sheet: int = 0,
    max_rows: int = PREVIEW_ROWS, max_cols: int = PREVIEW_COLS,
) -> dict:
    """Đọc thô (không qua adapter) `max_rows × max_cols` ô đầu của một sheet Excel.

    Trả dict cho template: sheet_names, selected_sheet, columns (nhãn A/B/…), rows,
    truncated_rows/cols, error. Dùng chung cho trang xem file + grid nhúng màn review.
    """
    import pandas as pd

    out: dict = {
        "sheet_names": [], "selected_sheet": 0, "columns": [], "rows": [],
        "truncated_rows": False, "truncated_cols": False, "error": None,
    }
    try:
        xls = pd.ExcelFile(abs_path)
        out["sheet_names"] = list(xls.sheet_names)
        sel = sheet if 0 <= sheet < len(out["sheet_names"]) else 0
        out["selected_sheet"] = sel
        df = pd.read_excel(xls, sheet_name=sel, header=None, nrows=max_rows + 1, dtype=object)
        out["truncated_rows"] = len(df) > max_rows
        df = df.iloc[:max_rows]
        out["truncated_cols"] = df.shape[1] > max_cols
        df = df.iloc[:, :max_cols]
        out["columns"] = _excel_col_letters(df.shape[1])
        out["rows"] = [
            ["" if pd.isna(v) else str(v) for v in r]
            for r in df.itertuples(index=False, name=None)
        ]
    except Exception as e:  # noqa: BLE001 — file hỏng/sai định dạng → báo nhẹ, không 500
        out["error"] = f"{type(e).__name__}: {e}"
    return out


@router.get("/companies/{code}/documents/file/{file_id}/preview", response_class=HTMLResponse)
def documents_preview_file(
    code: str,
    request: Request,
    file_id: int,
    sheet: int = Query(default=0, ge=0),
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Xem nhanh nội dung file Excel đã tải lên (raw, tối đa 100 dòng × 40 cột).

    Đọc thẳng file gốc (không qua adapter) để kiểm layout trước/độc lập với nạp."""
    company = get_company_or_404(db, code, user)
    row = db.get(DataFile, file_id)
    if row is None or row.company_id != company.id:
        raise HTTPException(status_code=404, detail="Không tìm thấy file")
    abs_path = _resolve_within_root(row.stored_path)
    if not abs_path.is_file():
        raise HTTPException(status_code=404, detail="File không còn trên đĩa")

    pv = _extract_sheet_preview(abs_path, sheet)

    return templates.TemplateResponse(
        request,
        "document_preview.html",
        {
            "user": user,
            "company": company,
            "file": row,
            "slot_label": SLOT_LABEL_VI.get(row.slot, row.slot),
            "sheet_names": pv["sheet_names"],
            "selected_sheet": pv["selected_sheet"],
            "columns": pv["columns"],
            "rows": pv["rows"],
            "truncated_rows": pv["truncated_rows"],
            "truncated_cols": pv["truncated_cols"],
            "preview_rows": PREVIEW_ROWS,
            "preview_cols": PREVIEW_COLS,
            "human_size": _human_size,
            "error": pv["error"],
        },
    )


@router.get("/companies/{code}/documents/file/{file_id}/review", response_class=HTMLResponse)
def documents_review_file(
    code: str,
    request: Request,
    file_id: int,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Màn review map cột (WS1-3b, ADR #18): xem map đề xuất + badge evidence mỗi cột,
    sửa chỉ số cột của field `needs_review`, xác nhận (POST) → advance `analyzed→parsed`.
    """
    company = get_company_or_404(db, code, user)
    row = db.get(DataFile, file_id)
    if row is None or row.company_id != company.id:
        raise HTTPException(status_code=404, detail="Không tìm thấy file")

    detail = row.parse_detail_obj
    columns = detail.get("columns", [])
    column_map = detail.get("column_map", {})
    form_signature = detail.get("form_signature")

    from app.checks.registry import checks_reading

    # Đính check bị ảnh hưởng cho mỗi cột (banner ở màn này) — cùng nguồn với cổng review.
    view_cols = []
    for c in columns:
        field = c.get("field", "")
        view_cols.append({
            **c,
            "col_index": column_map.get(field),
            "checks": checks_reading(row.slot, field),
        })

    # Grid preview nhúng: nội dung THẬT của file (dòng/cột đầu) để đối chiếu chỉ số cột —
    # bảng chỉ-số-không thì cán bộ không biết cột 8 là gì. Annotate mỗi cột grid bằng
    # field đã map (tô màu) + cột needs_review (vàng). Số cột grid phủ đủ chỉ số đã map.
    mapped_idx = [i for i in column_map.values() if isinstance(i, int)]
    grid_cols = min(max((max(mapped_idx) + 2 if mapped_idx else 0), 8), PREVIEW_COLS)
    abs_path = _resolve_within_root(row.stored_path)
    preview = (
        _extract_sheet_preview(abs_path, 0, REVIEW_PREVIEW_ROWS, grid_cols)
        if abs_path.is_file() else None
    )
    col_annot = {
        c["col_index"]: {"label": c["label"], "needs": c.get("review") == "needs_review"}
        for c in view_cols
        if isinstance(c.get("col_index"), int)
    }

    # Selector chọn sổ quyết toán — chỉ file settlement (m15/m15a/m16), tờ khai không có
    # (toàn pháp nhân). Datalist gợi ý sổ ĐÃ có của DN năm này (ADR #19 Revision — upload).
    is_settlement = row.slot in SETTLEMENT_SLOTS
    book_options = company_books(db, company.id, row.period_year) if is_settlement else []

    return templates.TemplateResponse(
        request,
        "document_review.html",
        {
            "user": user,
            "company": company,
            "file": row,
            "slot_label": SLOT_LABEL_VI.get(row.slot, row.slot),
            "columns": view_cols,
            "form_signature": form_signature,
            "can_confirm": bool(form_signature and column_map),
            "human_size": _human_size,
            "preview": preview,
            "col_annot": col_annot,
            "is_settlement": is_settlement,
            "book_options": book_options,
            "book_known": BOOK_LABELS,
        },
    )


@router.post("/companies/{code}/documents/file/{file_id}/review", response_model=None)
async def documents_confirm_review(
    code: str,
    request: Request,
    file_id: int,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Xác nhận map cột: ghi saved-map (#6) rồi re-ingest (commit) → file advance
    `analyzed→parsed`, cột trong map resolve `officer-confirmed` → `verified`.

    Chuỗi advance: ``save_column_map`` (+ commit) → ``run_ingest`` → ``record_parse_result``
    (committed=True). ``record_parse_result`` gọi ``resolve_officer_confirmed`` nên các cột
    vừa lưu map lên `officer-confirmed`, cổng review clear.
    """
    company = get_company_or_404(db, code, user)
    row = db.get(DataFile, file_id)
    if row is None or row.company_id != company.id:
        raise HTTPException(status_code=404, detail="Không tìm thấy file")

    slot = row.slot
    year = row.period_year
    # File đã `parsed` TRƯỚC lần sửa này → dòng Tầng 1 + finding đã tồn tại; sửa map
    # phải chạy lại các check bị ảnh hưởng inline (scoped, ADR #18). File `analyzed`
    # (lần confirm đầu) chưa có finding — không auto chạy check (bước riêng).
    was_parsed = row.parse_status == DataFileStatus.OK
    detail = row.parse_detail_obj
    form_signature = detail.get("form_signature")
    base_map = detail.get("column_map", {})
    columns = detail.get("columns", [])

    def _redirect(params: str) -> RedirectResponse:
        return RedirectResponse(url=f"/companies/{code}/documents?{params}", status_code=303)

    if not form_signature or not base_map:
        return _redirect(
            "error=" + quote_plus("File này không có thông tin map cột để xác nhận.")
        )

    # Map đầy đủ = cột officer sửa (field `needs_review`) chồng lên map đề xuất. Ô thiếu /
    # không hợp lệ giữ giá trị đề xuất để map không khuyết cột.
    form = await request.form()
    column_map: dict[str, int] = {}
    for field, default_idx in base_map.items():
        raw = form.get(f"col_{field}")
        try:
            column_map[field] = int(raw) if raw not in (None, "") else int(default_idx)
        except (TypeError, ValueError):
            column_map[field] = int(default_idx)

    # Cột đổi map so với map đã commit (base_map = map đang lưu ở parse_detail, đã sinh
    # ra dòng hiện tại). Chỉ có ý nghĩa khi file đã `parsed` → scoped re-run.
    changed_fields = {
        f for f, idx in column_map.items() if int(base_map.get(f, idx)) != int(idx)
    }

    # Sổ quyết toán (book) — chỉ file settlement mang book; tờ khai luôn toàn pháp nhân.
    # Set NGAY trên row (cùng session) → commit dưới → run_ingest đọc data_files.book,
    # gom balances theo sổ (ADR #19 Revision — upload). Rỗng → None (một sổ).
    book_changed = False
    if slot in SETTLEMENT_SLOTS:
        new_book = normalize_book(form.get("book"))
        book_changed = (row.book or None) != new_book
        row.book = new_book

    evidence = {c["field"]: c.get("evidence") for c in columns if c.get("field")}

    from app.auth_users import get_user_by_username
    from app.pipeline.data_files import record_parse_result, sync_data_files
    from app.pipeline.saved_map import save_column_map

    ur = get_user_by_username(db, user.name)
    save_column_map(
        db, company.id, slot, form_signature, column_map,
        evidence=evidence, confirmed_by=ur.id if ur else None,
    )
    db.commit()

    # Re-ingest thật (commit dòng) — record_parse_result đọc saved-map vừa ghi để nâng
    # các cột lên officer-confirmed → verified → cổng review clear, file thành parsed.
    raw_root = Path(settings.raw_data_path)
    diagnosis = diagnose_upload(company.code, year, raw_root)
    if diagnosis.has_errors:
        from app.pipeline.ingest import IngestStats
        sync_data_files(db, company)
        record_parse_result(
            db, company, year,
            IngestStats(company_code=company.code, period_year=year), diagnosis,
        )
        return _redirect(
            "error=" + quote_plus("Đã lưu map nhưng nạp lỗi — xem chi tiết ở trang tải lên.")
        )
    try:
        stats = run_ingest(company.code, year, raw_root=raw_root)
    except IngestPlanError as e:
        # Selector sổ là per-file: gán xong file này thì file kia còn trống — bước BẮT BUỘC
        # đi qua khi dựng pháp nhân nhiều sổ, không phải lỗi hệ thống. Sổ vừa gán đã commit
        # ở trên nên cán bộ gán tiếp file sau; kế hoạch bị từ chối TRƯỚC lệnh xoá nên dòng
        # của lượt nạp trước còn nguyên.
        sync_data_files(db, company)
        return _redirect(
            "error=" + quote_plus(f"Đã lưu sổ cho file này, CHƯA nạp dữ liệu. {e}")
        )
    except Exception as e:  # noqa: BLE001 — show parser errors back to user
        raise HTTPException(status_code=500, detail=f"Nạp dữ liệu lỗi: {type(e).__name__}: {e}") from e

    sync_data_files(db, company)
    record_parse_result(db, company, year, stats, diagnosis)

    # File đã `parsed` + có cột đổi map → chạy lại CHỈ check đọc cột đã đổi (scoped,
    # ADR #18). Finding tham chiếu Tầng 1 qua evidence_refs (table + filter theo mã
    # hàng), KHÔNG theo id dòng → dòng thay khi re-ingest không làm treo finding của
    # check KHÔNG chạy lại (khoá lọc = mã hàng vẫn đúng vì cột mã không đổi). Nếu cột
    # KHOÁ (mã) đổi thì khoá lọc đổi → mở rộng ra mọi check đọc slot (gồm C2.1/C2.2).
    label = SLOT_LABEL_VI.get(slot, slot).split(" — ")[0]
    # Re-run check sau re-ingest (ADR #18 Revision — WS2, async qua job): cột đổi map →
    # scoped theo check đọc cột đó; ĐỔI SỔ (book) trên file đã parsed → gom nội-sổ +
    # union cross-layer đổi trên diện rộng → chạy lại TOÀN BỘ năm (only=None).
    affected: set[str] = set()
    if was_parsed and changed_fields:
        from app.checks.registry import checks_reading, checks_reading_slot

        for f in changed_fields:
            affected.update(checks_reading(slot, f))
        if _SLOT_KEY_FIELD.get(slot) in changed_fields:
            affected.update(checks_reading_slot(slot))
    run_full = was_parsed and book_changed
    if was_parsed and (affected or run_full):
        # confirm + re-ingest (áp map/book, file→`parsed`) GIỮ đồng bộ ở trên; chỉ phần
        # re-run enqueue → worker 1-thread serialize ghi, triệt tranh chấp SQLite.
        if ur is not None:
            from app.jobs import enqueue_job
            from app.models.job import JobKind
            payload: dict = {"company_code": company.code, "year": year}
            if not run_full:
                payload["only"] = sorted(affected)
            job = enqueue_job(
                db, kind=JobKind.RUN_CHECKS, payload=payload,
                created_by=ur.id, company_id=company.id, period_year=year,
            )
            log_access(
                db, username=user.name, action=ACTION_RUN_CHECKS,
                company_code=company.code,
                detail=(
                    f"year={year} "
                    f"only={'ALL' if run_full else ','.join(sorted(affected))} (confirm-review)"
                ),
            )
            return RedirectResponse(url=f"/jobs/{job.id}", status_code=303)
        # Fallback hiếm (session user không map được row): chạy inline để không bỏ sót.
        from app.pipeline.run_checks import run_checks
        run_checks(company.code, year, only=None if run_full else affected)

    return _redirect(
        "msg=" + quote_plus(f"Đã xác nhận cột {label} năm {year} & nạp dữ liệu")
    )


@router.post("/companies/{code}/documents/ingest", response_model=None)
def documents_ingest_year(
    code: str,
    year: int = Form(...),
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Nạp lại dữ liệu cho 1 năm từ file đã tải lên (không cần upload lại)."""
    company = get_company_or_404(db, code, user)

    from app.pipeline.data_files import record_parse_result, sync_data_files

    raw_root = Path(settings.raw_data_path)
    diagnosis = diagnose_upload(company.code, year, raw_root)
    if diagnosis.has_errors:
        from app.pipeline.ingest import IngestStats
        sync_data_files(db, company)
        record_parse_result(
            db, company, year, IngestStats(company_code=company.code, period_year=year), diagnosis,
        )
        return RedirectResponse(
            url=f"/companies/{code}/documents?error=N%E1%BA%A1p+l%E1%BB%97i%2C+xem+chi+ti%E1%BA%BFt+%E1%BB%9F+trang+t%E1%BA%A3i+l%C3%AAn",
            status_code=303,
        )
    try:
        stats = run_ingest(company.code, year, raw_root=raw_root)
    except IngestPlanError as e:
        # Gán sổ nửa vời / thiếu file đã đăng ký: việc cán bộ phải xử lý, không phải lỗi
        # hệ thống. Từ chối xảy ra TRƯỚC lệnh xoá nên dữ liệu của lượt nạp trước còn nguyên.
        sync_data_files(db, company)
        return RedirectResponse(
            url=f"/companies/{code}/documents?error=" + quote_plus(str(e)),
            status_code=303,
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Nạp dữ liệu lỗi: {type(e).__name__}: {e}") from e

    sync_data_files(db, company)
    record_parse_result(db, company, year, stats, diagnosis)
    return RedirectResponse(
        url=f"/companies/{code}/documents?msg=%C4%90%C3%A3+n%E1%BA%A1p+d%E1%BB%AF+li%E1%BB%87u+n%C4%83m+{year}",
        status_code=303,
    )


@router.post("/companies/{code}/documents/period", response_model=None)
def documents_set_period(
    code: str,
    year: int = Form(...),
    period_from: str = Form(default=""),
    period_to: str = Form(default=""),
    reset: str = Form(default=""),
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Sửa kỳ báo cáo (từ ngày / đến ngày) cho 1 năm. Lưu `is_manual=True`; re-ingest
    tôn trọng, không ghi đè. `reset=1` → về mặc định (`is_manual=False`), ingest sau tự suy."""
    from datetime import date

    company = get_company_or_404(db, code, user)
    row = db.scalar(
        select(CompanyPeriod).where(
            CompanyPeriod.company_id == company.id, CompanyPeriod.period_year == year
        )
    )

    def _redirect(**params: str) -> RedirectResponse:
        from urllib.parse import urlencode

        qs = urlencode(params)
        return RedirectResponse(url=f"/companies/{code}/documents?{qs}", status_code=303)

    if reset:
        if row is not None:
            row.is_manual = False
            db.commit()
        return _redirect(msg=f"Đã đặt kỳ năm {year} về mặc định — nạp lại dữ liệu để áp dụng")

    try:
        pf = date.fromisoformat(period_from)
        pt = date.fromisoformat(period_to)
    except ValueError:
        return _redirect(error="Ngày không hợp lệ (định dạng YYYY-MM-DD)")
    if pf > pt:
        return _redirect(error="Từ ngày phải nhỏ hơn hoặc bằng đến ngày")

    if row is None:
        row = CompanyPeriod(company_id=company.id, period_year=year)
        db.add(row)
    row.period_from = pf
    row.period_to = pt
    row.is_manual = True
    db.commit()
    return _redirect(
        msg=f"Đã lưu kỳ năm {year} — bấm Nạp dữ liệu rồi Chạy kiểm tra để áp dụng"
    )


@router.post("/companies/{code}/run-checks", response_model=None)
def rerun_checks(
    code: str,
    year: int | None = Form(default=None),
    check: list[str] = Form(default=[]),
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Enqueue job chạy checks.

    - Không gửi `year` → BATCH_RUN mọi năm có dữ liệu (UI default 2026-05-26).
    - Có `year`, không `check` → RUN_CHECKS full năm đó.
    - Có `year` + `check` (lặp được) → RUN_CHECKS `only=` tập con (chạy test lẻ,
      ADR #18 Revision — WS2). `check` bị bỏ qua khi chạy batch (mọi năm).
    """
    from app.auth_users import get_user_by_username
    from app.jobs import enqueue_job
    from app.models.job import JobKind

    company = get_company_or_404(db, code, user)

    user_row = get_user_by_username(db, user.name)
    if user_row is None:
        raise HTTPException(status_code=403, detail="Session user không tồn tại")

    only = [c for c in check if c]
    if year is None:
        job = enqueue_job(
            db,
            kind=JobKind.BATCH_RUN,
            payload={"company_code": company.code},
            created_by=user_row.id,
            company_id=company.id,
            period_year=None,
        )
        detail = "batch"
    else:
        payload: dict = {"company_code": company.code, "year": year}
        if only:
            payload["only"] = only
        job = enqueue_job(
            db,
            kind=JobKind.RUN_CHECKS,
            payload=payload,
            created_by=user_row.id,
            company_id=company.id,
            period_year=year,
        )
        detail = f"year={year}" + (f" only={','.join(only)}" if only else "")
    log_access(db, username=user.name, action=ACTION_RUN_CHECKS, company_code=company.code,
               detail=detail)
    return RedirectResponse(url=f"/jobs/{job.id}", status_code=303)


@router.post("/companies/{code}/overview", response_model=None)
def generate_overview(
    code: str,
    year: int = Form(...),
    check: str = Form(...),
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Sinh AI tổng quan cho 1 kiểm tra (DN, năm). Endpoint `def` THUẦN — chạy trong
    threadpool FastAPI, KHÔNG qua job worker 1-thread (gọi LLM 5s sẽ chặn hàng đợi
    check). On-demand, đồng bộ trong request (ADR #18 Revision — WS3)."""
    from app.ai.config import get_setting
    from app.ai.limits import check_daily_budget, check_rate_limit
    from app.ai.overview import generate_check_overview
    from app.audit import ACTION_AI_OVERVIEW

    company = get_company_or_404(db, code, user)

    def _back(**params: str) -> RedirectResponse:
        from urllib.parse import urlencode

        qs = urlencode({"year": year, **params})
        return RedirectResponse(
            url=f"/companies/{company.slug or company.code}?{qs}#group-{check}",
            status_code=303,
        )

    if not get_setting("enabled"):
        return _back(error="AI assistant đang tắt. Bật trong /admin/ai.")
    if not get_setting("api_key"):
        return _back(error="Chưa cấu hình API key AI. Cấu hình ở /admin/ai.")
    try:
        check_rate_limit(user.name, db)
        check_daily_budget(db)
    except HTTPException as e:
        return _back(error=str(e.detail))

    try:
        generate_check_overview(
            db, company=company, period_year=year, check_code=check
        )
    except Exception as e:  # noqa: BLE001 — show LLM/provider errors back to user
        db.rollback()
        return _back(error=f"Sinh tổng quan lỗi: {type(e).__name__}: {str(e)[:200]}")

    log_access(db, username=user.name, action=ACTION_AI_OVERVIEW,
               company_code=company.code, detail=f"year={year} check={check}")
    return _back(msg=f"Đã tạo tổng quan {check} năm {year}")


@router.get("/companies/{code}", response_class=HTMLResponse)
def company_detail(
    code: str,
    request: Request,
    year: int | None = Query(default=None),
    ingested: int = Query(default=0),
    check: str | None = Query(default=None),
    book: str | None = Query(default=None),
    page: int = Query(default=1),
    msg: str | None = Query(default=None),
    error: str | None = Query(default=None),
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    company = get_company_or_404(db, code, user)

    finding_years = set(
        db.scalars(
            select(Finding.period_year).where(Finding.company_id == company.id).distinct()
        ).all()
    )
    # Năm CÓ DỮ LIỆU đã nạp (kể cả chưa chạy kiểm tra) — gộp 4 bảng Tầng 1.
    data_years: set[int] = set()
    for model in (NvlBalance, SpBalance, Norm, DeclarationLine):
        data_years |= set(
            db.scalars(
                select(model.period_year).where(model.company_id == company.id).distinct()
            ).all()
        )
    years = sorted(finding_years | data_years, reverse=True)
    selected_year = year if year is not None else (years[0] if years else None)
    period_windows = load_period_windows(db, company.id)

    # Pháp nhân nhiều sổ (004 EPE/GC): strip tổng quan theo sổ + gate chrome theo sổ
    # (ADR #19 Revision — UI). Một sổ (002/006) → book_strip=None, multi_book=False.
    book_strip = book_summary(db, company.id, selected_year) if selected_year is not None else None
    multi_book = book_strip is not None
    books_list = company_books(db, company.id, selected_year) if multi_book else []

    # Lọc theo sổ (?book=) — VIEW-FILTER thuần: chỉ thu hẹp danh sách finding (đếm +
    # dòng + nhóm). `book=chung` → Finding.book IS NULL (phát hiện liên sổ). KHÔNG gộp
    # Chung vào một sổ. Điểm năm / strip / export / run GIỮ toàn pháp nhân.
    book_selected: str | None = None      # giá trị query để giữ ở link + highlight
    book_filter: str | None = None        # None=tất cả · "__chung__" · mã sổ
    if multi_book and book:
        b = book.strip()
        if b.lower() == "chung":
            book_selected, book_filter = "chung", "__chung__"
        elif b in books_list:
            book_selected, book_filter = b, b
        # mã lạ → bỏ qua (coi như tất cả)

    def _book_clause() -> tuple:
        if book_filter == "__chung__":
            return (Finding.book.is_(None),)
        if book_filter:
            return (Finding.book == book_filter,)
        return ()

    # Đếm bằng SQL, KHÔNG nạp hết Finding vào bộ nhớ: một DN thật đã sinh 11.003
    # phát hiện cho một kỳ, render hết ra một trang là 18,7 MB HTML.
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    severity_totals = {"critical": 0, "warning": 0, "info": 0}
    combo_findings: list[Finding] = []
    # Gate combo theo setting SỐNG (ADR #18 Revision — WS2): OFF → ẩn cả render, kể cả
    # khi còn COMBO_* cũ trong DB (lazy). Flip giữa chừng ẩn/hiện ngay.
    combos_on = get_combos_enabled(db)
    if selected_year is not None:
        for ccode, sev, n in db.execute(
            select(Finding.check_code, Finding.severity, func.count())
            .where(
                Finding.company_id == company.id,
                Finding.period_year == selected_year,
                *_book_clause(),
            )
            .group_by(Finding.check_code, Finding.severity)
        ).all():
            if ccode.startswith("COMBO_"):
                continue
            counts[ccode][sev] += n
            if sev in severity_totals:
                severity_totals[sev] += n
        if combos_on:
            # Combo book=NULL → lọc "Chung"/"tất cả" giữ, lọc một sổ (EPE/GC) loại.
            combo_findings = db.scalars(
                select(Finding)
                .where(
                    Finding.company_id == company.id,
                    Finding.period_year == selected_year,
                    Finding.check_code.startswith("COMBO_"),
                    *_book_clause(),
                )
                .order_by(Finding.subject_key)
            ).all()

    total_findings = sum(sum(s.values()) for s in counts.values())

    # Dòng split per-check "Sổ: EPE 8 · Liên sổ 2" — chỉ pháp nhân nhiều sổ, chỉ bucket
    # >0, sổ trước rồi Liên sổ (book=NULL) cuối. Tính trên TOÀN pháp nhân (không theo lọc).
    book_splits: dict[str, list[tuple[str, int]]] = {}
    if multi_book and selected_year is not None:
        raw_splits: dict[str, dict[str | None, int]] = defaultdict(dict)
        for ccode, bk, n in db.execute(
            select(Finding.check_code, Finding.book, func.count())
            .where(
                Finding.company_id == company.id,
                Finding.period_year == selected_year,
                ~Finding.check_code.startswith("COMBO_"),
            )
            .group_by(Finding.check_code, Finding.book)
        ).all():
            raw_splits[ccode][bk] = n
        for ccode, bkmap in raw_splits.items():
            ordered = [(bcode, bkmap[bcode]) for bcode in books_list if bkmap.get(bcode)]
            if bkmap.get(None):
                ordered.append(("Liên sổ", bkmap[None]))
            book_splits[ccode] = ordered

    def _rank(ccode: str) -> tuple[int, str]:
        sevs = counts[ccode]
        return (min(_SEVERITY_ORDER.get(s, 99) for s in sevs), ccode)

    codes = sorted(counts, key=_rank)
    # Xem sâu một kiểm tra: phân trang thay vì đổ cả nghìn dòng.
    focus = check if check in counts else None
    page = max(1, page)

    def _rows(ccode: str, limit: int, offset: int = 0) -> list[Finding]:
        return db.scalars(
            select(Finding)
            .where(
                Finding.company_id == company.id,
                Finding.period_year == selected_year,
                Finding.check_code == ccode,
                *_book_clause(),
            )
            .order_by(Finding.severity, Finding.subject_key)
            .limit(limit)
            .offset(offset)
        ).all()

    # (mã, dòng hiển thị, tổng, đếm theo mức) — template chỉ nhận phần cần vẽ.
    ordered_groups: list[tuple[str, list[Finding], int, dict[str, int]]] = []
    if focus:
        total = sum(counts[focus].values())
        ordered_groups.append(
            (focus, _rows(focus, _PAGE_SIZE, (page - 1) * _PAGE_SIZE), total, dict(counts[focus]))
        )
    else:
        for ccode in codes:
            total = sum(counts[ccode].values())
            ordered_groups.append(
                (ccode, _rows(ccode, _PREVIEW_PER_GROUP), total, dict(counts[ccode]))
            )

    # Lọc trúng sổ sạch (0 phát hiện, có mã NVL) → empty-state riêng, tách khỏi
    # "chưa nạp dữ liệu"/"chưa chạy kiểm tra". Chung rỗng → thông điệp liên-sổ riêng.
    book_empty: dict | None = None
    if multi_book and book_filter and not ordered_groups and not combo_findings:
        if book_filter == "__chung__":
            book_empty = {"kind": "chung"}
        else:
            nvl_codes = next(
                (c["nvl_codes"] for c in book_strip["books"] if c["code"] == book_filter), 0
            )
            book_empty = {"kind": "clean", "label": book_label(book_filter), "nvl_codes": nvl_codes}

    year_score = None
    if selected_year is not None:
        year_score = db.scalar(
            select(CompanyYearScore).where(
                CompanyYearScore.company_id == company.id,
                CompanyYearScore.period_year == selected_year,
            )
        )

    all_specs = get_all_specs(db)

    # Danh sách mã có finding — cho panel "Xuất các test đã chọn" (WS2-3). Gồm mọi
    # mã regular (không phụ thuộc focus) + combo (mã như mọi check khi export).
    export_options: list[dict] = []
    for ccode in codes:
        spec = all_specs.get(ccode) or SPECS.get(ccode)
        export_options.append({
            "code": ccode, "title": spec.title if spec else ccode,
            "total": sum(counts[ccode].values()),
        })
    combo_counts: dict[str, int] = defaultdict(int)
    for f in combo_findings:
        combo_counts[f.check_code] += 1
    for ccode in sorted(combo_counts):
        spec = COMBO_SPECS.get(ccode)
        export_options.append({
            "code": ccode, "title": spec.title if spec else ccode,
            "total": combo_counts[ccode],
        })

    # Toàn danh mục check (built-in + dynamic đã công bố) — cho modal "Chọn test chạy".
    # Khác export_options (chỉ mã ĐÃ có finding): chạy thì chọn từ danh mục đầy đủ.
    run_options = [{"code": c, "title": s.title} for c, s in sorted(all_specs.items())]

    # Gom theo họ C1/C2/… (tiêu đề nhóm §4) cho cả hai modal.
    run_groups = _group_options_by_family(run_options, all_specs)
    export_groups = _group_options_by_family(export_options, all_specs)

    # WS3: AI tổng quan + staleness cho các nhóm đang render (chỉ check thật, không
    # combo). Chỉ nạp khi AI bật — nút "Tạo tổng quan" ẩn khi tắt.
    from app.ai.config import get_setting
    from app.ai.overview import load_overviews_with_staleness

    ai_enabled = bool(get_setting("enabled")) and bool(get_setting("api_key"))
    overviews: dict[str, dict] = {}
    if selected_year is not None:
        displayed_codes = [g[0] for g in ordered_groups]
        overviews = load_overviews_with_staleness(
            db, company.id, selected_year, displayed_codes
        )

    # Trạng thái tách upload/kiểm tra: có dữ liệu năm này chưa? đã chạy kiểm tra chưa?
    # checks_run phải TOÀN pháp nhân (không theo bộ lọc ?book=) — lọc sổ sạch không
    # được lật về "chưa chạy kiểm tra". finding_years/year_score đều full-entity.
    has_data = selected_year in data_years if selected_year is not None else False
    checks_run = year_score is not None or (selected_year in finding_years)

    return templates.TemplateResponse(
        request,
        "company_detail.html",
        {
            "user": user,
            "company": company,
            "years": years,
            "selected_year": selected_year,
            "period_windows": period_windows,
            "ordered_groups": ordered_groups,
            "export_options": export_options,
            "run_options": run_options,
            "run_groups": run_groups,
            "export_groups": export_groups,
            "combo_findings": combo_findings,
            "severity_totals": severity_totals,
            "total_findings": total_findings,
            "book_strip": book_strip,
            "multi_book": multi_book,
            "book_splits": book_splits,
            "books_list": books_list,
            "book_selected": book_selected,
            "book_empty": book_empty,
            "focus_check": focus,
            "page": page,
            "page_size": _PAGE_SIZE,
            "preview_per_group": _PREVIEW_PER_GROUP,
            "year_score": year_score,
            "all_specs": all_specs,
            "has_data": has_data,
            "checks_run": checks_run,
            "just_ingested": bool(ingested),
            "overviews": overviews,
            "ai_enabled": ai_enabled,
            "flash_msg": msg,
            "flash_error": error,
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
    check: list[str] = Query(default=[]),
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> Response:
    """Xuất Excel kiến nghị. `check` (lặp được) → chỉ xuất các test đã chọn; không
    chọn = xuất toàn bộ (ADR #18 Revision — WS2)."""
    company = get_company_or_404(db, code, user)
    only = {c for c in check if c} or None
    payload = build_export(db, company, year, only=only)
    log_access(db, username=user.name, action=ACTION_EXPORT,
               company_code=company.code,
               detail=f"year={year}" + (f" only={','.join(sorted(only))}" if only else ""))
    scope = "" if not only else "_" + "-".join(sorted(only)).replace(".", "").replace("*", "")
    filename = f"audit-hq_{company.slug or company.code}_{year}{scope}_kien-nghi-kiem-tra.xlsx"
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
        v = float(value)
        # Bỏ .0 cho số nguyên.
        if v.is_integer():
            return f"{int(v):,}"
        # Số "bình thường": 2 chữ số thập phân.
        if abs(v) >= 0.01:
            return f"{v:,.2f}"
        # Số rất nhỏ (vd định mức tiêu hao ~0.0018 kg/sp): 2 chữ số sẽ thành 0.00 →
        # dùng định dạng số-có-nghĩa để không mất giá trị thật.
        return f"{v:.6g}"
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
    company = get_company_or_404(db, code, user)

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

    # Bằng chứng cách đọc file (ADR #15) — hiện phía trên bảng để không "hộp đen".
    prov_file = db.scalar(
        select(DataFile).where(
            DataFile.company_id == company.id,
            DataFile.period_year == year,
            DataFile.slot == table,
            DataFile.parse_layout.isnot(None),
        )
    )

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
            "parse_layout": prov_file.parse_layout if prov_file else None,
            "parse_detail": prov_file.parse_detail_obj if prov_file else {},
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
    company = get_company_or_404(db, code, user)

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
            "period_windows": load_period_windows(db, company.id),
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
    if not can_access_company_id(db, user, finding.company_id):
        raise HTTPException(status_code=404, detail="Không tìm thấy phát hiện")
    company = db.get(Company, finding.company_id)
    is_combo = finding.check_code.startswith("COMBO_")
    spec = COMBO_SPECS.get(finding.check_code) if is_combo else SPECS.get(finding.check_code)
    # Field "Sổ quyết toán" chỉ cho pháp nhân nhiều sổ (một sổ → book vô nghĩa).
    show_book = is_multi_book(db, finding.company_id, finding.period_year)

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
            "show_book": show_book,
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
    if not can_access_company_id(db, user, finding.company_id):
        raise HTTPException(status_code=404, detail="Không tìm thấy phát hiện")

    finding.status = status
    finding.notes = notes.strip() or None
    db.flush()
    # Đổi trạng thái (vd "Loại trừ") → tính lại điểm năm đó NGAY từ findings hiện có
    # (không chạy lại kiểm tra). Finding rejected sẽ rớt khỏi điểm tức thì.
    from app.pipeline.recompute import recompute_company_year
    recompute_company_year(db, finding.company_id, finding.period_year)
    db.commit()

    company = db.get(Company, finding.company_id)
    url_id = (company.slug or company.code) if company else None
    if not url_id:
        return RedirectResponse(url="/companies", status_code=303)
    return RedirectResponse(
        url=f"/companies/{url_id}?year={finding.period_year}#finding-{finding_id}",
        status_code=303,
    )
