"""Routes for browsing companies and their findings (Tầng 2 viewer)."""

from __future__ import annotations

import json as _json
import re
import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict
from datetime import date
from pathlib import Path, PurePosixPath
from urllib.parse import quote_plus, urlencode

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.adapters.cell_reader import (
    CellReadError,
    SheetOutOfRange,
    UnsupportedFileFormat,
    detect_format,
)
from app.adapters.cell_window import cache_file_for, read_window, request_extract
from app.adapters.evidence import FIELD_LABEL_VI
from app.adapters.templates import column_groups
from app.ai.overview_stats import PERCENTILE_LABEL_VI
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
    book_lock,
    book_summary,
    company_books,
    is_multi_book,
    normalize_book,
)
from app.checks.combos import COMBO_SPECS
from app.checks.detail_labels import column_headers, describe_details, row_cells
from app.checks.registry import SEVERITY_BADGE, SEVERITY_LABEL_VI, SPECS, Severity, get_all_specs
from app.checks.scope import declaration_scope
from app.checks.scoring import score_coverage, tier_css_for, tier_for
from app.database import get_db
from app.formatting import JINJA_GLOBALS as FORMAT_GLOBALS
from app.formatting import fmt_date, fmt_price, fmt_qty
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
from app.models.data_file import (
    SETTLEMENT_SLOTS,
    SLOT_LABEL_VI,
    SLOT_ORDER,
    SLOT_SHORT_VI,
)
from app.pipeline.audit_scope import (
    AUDIT_YEARS,
    audit_window,
    declaration_spans,
    finding_scope_tag,
    scope_coverage,
)
from app.pipeline.data_screen import build_data_screen
from app.pipeline.export import build_export
from app.pipeline.findings_screen import not_evaluable_panel
from app.pipeline.ingest_status import ingest_status, mark_seen
from app.pipeline.period import (
    FISCAL_START_MONTHS,
    QUARTER_START_MONTHS,
    YEAR_MAX,
    YEAR_MIN,
    bump_data_version,
    duplicate_period_windows,
    fiscal_bounds,
    load_period_windows,
    period_window_conflict,
    period_window_errors,
)
from app.pipeline.staleness import results_stale, stale_result_years
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
# Độ phủ chấm điểm — mọi chỗ hiện điểm phải hiện kèm, xem `score_coverage`.
templates.env.globals["score_coverage"] = score_coverage
templates.env.globals["PERCENTILE_LABEL"] = PERCENTILE_LABEL_VI
# Nhãn sổ quyết toán (book) — dùng ở company_detail (split line) + finding_detail (field).
templates.env.globals["book_label"] = book_label
# Cột số của bảng phát hiện + nhãn tiếng Việt cho `finding.details`.
templates.env.globals["finding_columns"] = column_headers
templates.env.globals["finding_cells"] = row_cells
templates.env.globals.update(FORMAT_GLOBALS)

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
templates.env.globals["SLOT_SHORT_VI"] = SLOT_SHORT_VI
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
    # Độ phủ chấm điểm của DN = kỳ có độ phủ THẤP NHẤT. Điểm hiển thị là max theo năm,
    # nhưng độ phủ phải lấy trường hợp xấu nhất: một kỳ còn luật chưa đánh giá được là
    # đủ để không so ngang DN này với DN đã đánh giá trọn (xem `score_coverage`).
    coverage: dict[int, tuple[int, int]] = {}
    for cid, breakdown in db.execute(
        select(CompanyYearScore.company_id, CompanyYearScore.breakdown)
    ).all():
        done, total = score_coverage(breakdown)
        if not total:
            continue
        cur = coverage.get(cid)
        if cur is None or (done - total) < (cur[0] - cur[1]):
            coverage[cid] = (done, total)
    # Kỳ có kết quả cũ (phiên bản dữ liệu dời sau lần chạy) — nhãn cạnh cột điểm (#90).
    # KHÔNG lọc doanh nghiệp ra khỏi bảng xếp hạng: rơi khỏi bảng vì có người tải file
    # lên là cùng dạng sai lầm với việc bỏ luật khỏi thang điểm làm DN sạch hơn (#65).
    # Bất kỳ kỳ nào cũ cũng đủ để đánh dấu: điểm hiện là max theo năm, chạy lại kỳ cũ
    # có thể đổi chính giá trị max đó, nên thứ hạng cũng chưa chắc.
    stale_years = stale_result_years(db, [c.id for c in companies])

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
        done, total = coverage.get(c.id, (0, 0))
        summary.append({
            "company": c,
            "score": max_scores.get(c.id) or 0,
            "years": sorted(years.items(), reverse=True),
            "coverage_done": done,
            "coverage_total": total,
            "full_coverage": bool(total) and done >= total,
            "stale_years": stale_years.get(c.id, ()),
            "results_stale": bool(stale_years.get(c.id)),
        })
    # Xếp hạng tách NHÓM: DN đã đánh giá trọn phạm vi đứng trước, DN còn luật chưa đánh
    # giá được xuống nhóm sau. Điểm của hai nhóm KHÔNG so ngang được — điểm là trung
    # bình trên các luật chấm được, nên kỳ thiếu độ phủ có thể ra điểm THẤP hơn chỉ vì
    # luật đang gánh điểm bị gỡ (đo trên pilot: DN 10/2025 3→1). Xếp chung một cột thì
    # DN thiếu dữ liệu trồi lên đầu danh sách "sạch".
    summary.sort(key=lambda s: (not s["full_coverage"], -s["score"], s["company"].code))

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
# Năm đầu nộp BCQT có thể sớm hơn cửa sổ dữ liệu đã nạp (YEAR_MIN), nên nới cận dưới.
BCQT_YEAR_MIN = 2000

# Niên độ kế toán cho màn cài đặt DN — cả 12 tháng (owner chốt 06/08/2026, #66). Bốn
# mốc đầu quý là mốc luật cho phép; tháng khác vẫn chọn được, kèm cảnh báo không chặn.
def _fiscal_month_label(month: int) -> str:
    pf, pt = fiscal_bounds(2025, month)
    span = f"{pf.strftime('%d/%m')} – {pt.strftime('%d/%m')}"
    if month == 1:
        return f"{span} (dương lịch)"
    label = f"{span} năm sau"
    return label if month in QUARTER_START_MONTHS else f"{label} — ngoài mốc đầu quý"


FISCAL_MONTH_OPTIONS = [(m, _fiscal_month_label(m)) for m in FISCAL_START_MONTHS]
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


def _bcct_filename(original: str, year: int, ext: str) -> str:
    """Tên trên đĩa cho 1 file BCCT — giữ tên gốc đã làm sạch.

    Ô BCCT nhận NHIỀU file (một kỳ có thể gồm nhiều file rời, vd F1/F3 của 006), nên
    không dùng được tên canonical `BCCT_<năm>`: file thứ hai sẽ đè file thứ nhất. Giữ
    tên gốc thì cán bộ đối chiếu được với file trên máy mình, và tải lại đúng tên cũ
    là sửa đúng file đó.
    """
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(original).name).strip("_")
    return safe or f"BCCT_{year}{ext}"


def _existing_slot_files(dest_dir: Path, slot: str) -> list[Path]:
    """File Excel đã nằm trong thư mục và thuộc CÙNG slot.

    Phân loại theo `_classify_slot` thay vì glob prefix — glob cũ `M15*` còn xoá
    nhầm `M15a*` (hai slot khác nhau trong BCQT/). Cũng là căn cứ để biết một lượt
    tải lên là THAY file hay thêm file (#90).
    """
    from app.pipeline.data_files import _classify_slot

    if not dest_dir.is_dir():
        return []
    return [
        p
        for p in dest_dir.glob("*")
        if p.is_file()
        and p.suffix.lower() in {".xls", ".xlsx"}
        and _classify_slot(dest_dir.name, p.name) == slot
    ]


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
    error: str | None = Query(default=None),
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
        "first_bcqt_year": company.first_bcqt_year or "",
        "fiscal_start_month": company.fiscal_start_month or 1,
        "audit_decision_date": (
            company.audit_decision_date.isoformat() if company.audit_decision_date else ""
        ),
    }
    return templates.TemplateResponse(
        request, "edit_company.html",
        {
            "user": user, "company": company, "form": form_state, "error": None,
            "bcqt_year_min": BCQT_YEAR_MIN, "bcqt_year_max": YEAR_MAX,
            "fiscal_options": FISCAL_MONTH_OPTIONS,
        },
    )


@router.post("/companies/{code}/edit", response_model=None)
def update_company(
    code: str,
    request: Request,
    name: str = Form(""),
    tax_id: str = Form(""),
    address: str = Form(""),
    industry: str = Form(""),
    first_bcqt_year: str = Form(""),
    fiscal_start_month: str = Form("1"),
    audit_decision_date: str = Form(""),
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> Response:
    company = get_company_or_404(db, code, user)

    # Trống = "chưa biết" (NULL), không phải 0 — T6 đọc NULL để coi kỳ sớm nhất là
    # chưa đánh giá được. Nhập sai thì trả form kèm lỗi, không ghi đè giá trị cũ.
    raw_year = first_bcqt_year.strip()
    parsed_year: int | None = None
    if raw_year:
        try:
            parsed_year = int(raw_year)
        except ValueError:
            parsed_year = None
        if parsed_year is None or not (BCQT_YEAR_MIN <= parsed_year <= YEAR_MAX):
            form_state = {
                "code": company.code,
                "name": name.strip(),
                "tax_id": tax_id.strip(),
                "address": address.strip(),
                "industry": industry.strip(),
                "first_bcqt_year": raw_year,
                "fiscal_start_month": fiscal_start_month,
                "audit_decision_date": audit_decision_date.strip(),
            }
            return templates.TemplateResponse(
                request, "edit_company.html",
                {
                    "user": user, "company": company, "form": form_state,
                    "error": f"Năm đầu nộp BCQT phải trong khoảng {BCQT_YEAR_MIN}-{YEAR_MAX}.",
                    "bcqt_year_min": BCQT_YEAR_MIN, "bcqt_year_max": YEAR_MAX,
                    "fiscal_options": FISCAL_MONTH_OPTIONS,
                },
                status_code=400,
            )

    try:
        month = int(fiscal_start_month)
    except ValueError:
        month = 0
    if month not in FISCAL_START_MONTHS:
        return RedirectResponse(
            url=f"/companies/{code}/edit?error="
            + quote_plus("Tháng bắt đầu niên độ chỉ nhận giá trị từ 1 đến 12"),
            status_code=303,
        )
    # Tháng ngoài đầu quý được LƯU nhưng phải nói rõ là ngoài mốc luật (owner chốt
    # 06/08/2026): điểm a khoản 1 Điều 12 Luật Kế toán 88/2015 chỉ cho 01/01, 01/04,
    # 01/07, 01/10. Cán bộ chịu trách nhiệm về kỳ, phần mềm không chặn.
    fiscal_notice = (
        ""
        if month in QUARTER_START_MONTHS
        else (
            f" Lưu ý: niên độ bắt đầu tháng {month} nằm ngoài bốn mốc đầu quý mà "
            "điểm a khoản 1 Điều 12 Luật Kế toán 88/2015 cho phép."
        )
    )

    from datetime import date as _date

    decision_date = None
    if audit_decision_date.strip():
        try:
            decision_date = _date.fromisoformat(audit_decision_date.strip())
        except ValueError:
            return RedirectResponse(
                url=f"/companies/{code}/edit?error="
                + quote_plus("Ngày quyết định kiểm tra không hợp lệ (định dạng YYYY-MM-DD)"),
                status_code=303,
            )

    # Mã DN cố định (dùng làm thư mục lưu file) — không nhận từ form.
    name = name.strip()
    display_name = name or company.code
    if DEMO_SUFFIX not in display_name:  # giữ hậu tố (Demo) nhất quán với lúc tạo
        display_name = f"{display_name} {DEMO_SUFFIX}"

    company.name = display_name
    company.tax_id = tax_id.strip() or None
    company.address = address.strip() or None
    company.industry = industry.strip() or None
    company.first_bcqt_year = parsed_year
    # Đổi niên độ KHÔNG viết lại cửa sổ kỳ đã lưu: `company_periods` đã có là nguồn
    # sự thật cho kỳ đó (kể cả bản tự suy), niên độ chỉ là mặc định cho kỳ chưa có.
    company.fiscal_start_month = month
    # Phạm vi KTSTQ là VIEW: chỉ lưu mốc ngày, KHÔNG dời `data_version`, không xếp job
    # chạy lại — đổi ngày chỉ đổi cách hiển thị (ADR #23 T4).
    company.audit_decision_date = decision_date
    db.commit()

    if fiscal_notice:
        return RedirectResponse(
            url=f"/companies/{code}?msg=" + quote_plus("Đã lưu." + fiscal_notice),
            status_code=303,
        )
    return RedirectResponse(url=f"/companies/{code}", status_code=303)


def _enqueue_ingest(
    db: Session,
    user: SessionUser,
    company: Company,
    year: int,
    *,
    gate: bool,
    then_run_checks: dict | None = None,
):
    """Xếp job nạp dữ liệu cho (DN, năm) và trả Job vừa tạo.

    Mọi đường nạp (tải lên, nạp lại, xác nhận cột) đi qua đây — đọc file là việc
    hàng phút, request không giữ nổi (Cloudflare cắt ở 100 giây).
    """
    from app.auth_users import get_user_by_username
    from app.jobs import enqueue_job
    from app.models.job import JobKind

    ur = get_user_by_username(db, user.name)
    if ur is None:
        raise HTTPException(
            status_code=403,
            detail="Tài khoản của phiên đăng nhập này không còn tồn tại. Hãy đăng nhập lại.",
        )
    payload: dict = {
        "company_code": company.code,
        "year": year,
        "gate": gate,
        "created_by": ur.id,
    }
    if then_run_checks is not None:
        payload["then_run_checks"] = then_run_checks
    return enqueue_job(
        db, kind=JobKind.INGEST, payload=payload,
        created_by=ur.id, company_id=company.id, period_year=year,
    )


def _back_to_period(company: Company, year: int) -> RedirectResponse:
    """Về đúng dòng kỳ vừa xếp lượt nạp, KHÔNG sang `/jobs/{id}` (#89).

    Dòng kỳ tự chuyển sang trạng thái đang chờ / đang chạy và tự cập nhật; trang
    hàng đợi còn nguyên nhưng lùi về vai trò màn quản trị.
    """
    slug = company.slug or company.code
    return RedirectResponse(url=f"/companies/{slug}/documents#ky-{year}", status_code=303)


def _ai_available() -> bool:
    """Trợ lý AI có bật và có khoá hay không — quyết định hiện nút nhờ AI chẩn đoán."""
    from app.ai.config import get_setting

    try:
        return bool(get_setting("enabled") and get_setting("api_key"))
    except Exception:  # noqa: BLE001 — cấu hình AI hỏng không được chặn màn dữ liệu
        return False


def _slot_destination(base: Path, slot: str, original: str, year: int, ext: str) -> Path:
    """Đường dẫn canonical của một file trong slot. Tên phải để `_classify_slot` suy
    lại đúng slot đó — registry lấy loại từ CHỖ ĐẶT + TÊN, không từ ý định của route."""
    subdir, stem = _UPLOAD_SLOTS[slot]
    if slot == "bcct":
        return base / subdir / _bcct_filename(original, year, ext)
    return base / subdir / f"{stem}_{year}{ext}"


def _place_in_slot(src: Path, dest: Path, slot: str) -> bool:
    """Đưa file đã lưu vào đúng slot; trả True nếu lượt này THAY file đã có.

    m15/m15a/m16 mỗi biểu một bản → xoá file cùng slot đã có. bcct CỘNG DỒN: một kỳ
    có thể gồm nhiều file rời (F1/F2/F3 của 006), xoá ở đây là buộc cán bộ gộp tay và
    bản gộp tay đã mất 28,5 tỷ ở 2.076 ô công thức.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    # So sánh theo THỰC THỂ, không theo cách viết đường dẫn: `data/` ở môi trường thật
    # là symlink, nên cùng một file có hai cách viết. Nhầm ở đây thì vòng dưới xoá đúng
    # file đang chuẩn bị chuyển đi.
    same = src.exists() and dest.exists() and src.samefile(dest)
    replaced = dest.exists() and not same
    if slot != "bcct":
        for p in _existing_slot_files(dest.parent, slot):
            if not p.samefile(src):
                p.unlink(missing_ok=True)
                replaced = True
    if not same:
        src.replace(dest)
    return replaced


@router.get("/companies/{code}/upload", response_model=None)
def upload_form(
    code: str,
    year: int | None = Query(default=None),
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Địa chỉ cũ của trang tải lên bốn ô — nay dẫn về màn dữ liệu (#88).

    Trang bốn ô + ô chọn năm đã bỏ: ô chọn năm là chỗ nộp nhầm file kỳ này vào kỳ
    khác, và dòng kỳ ở màn dữ liệu chính là năm. Giữ chuyển hướng để liên kết đã lưu
    không hỏng.
    """
    company = get_company_or_404(db, code, user)
    slug = company.slug or company.code
    anchor = f"#ky-{year}" if year and YEAR_MIN <= year <= YEAR_MAX else ""
    return RedirectResponse(url=f"/companies/{slug}/documents{anchor}", status_code=303)


@router.post("/companies/{code}/upload", response_model=None)
def upload_drop_zone(
    code: str,
    year: int = Form(...),
    files: list[UploadFile] = File(default=[]),
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Ô thả file của một kỳ: nhận mọi file, GỢI Ý loại cho từng file (#88).

    Không xếp việc nạp. Cán bộ còn phải sửa loại và gán sổ trước khi nạp — nạp ngay
    ở đây là cướp mất chính bước mà vé này dựng ra.

    Mỗi file lưu vào thư mục chờ trước rồi mới xếp chỗ: có thế mới biết kích thước
    thật để quyết định có mở nội dung hay không, và file cũ cùng slot chỉ bị xoá sau
    khi file mới đã ghi xong (kiểm magic-byte có thể ném ở giữa chừng).
    """
    from app.pipeline.data_files import sync_data_files
    from app.pipeline.file_intake import BASIS_NAME, propose, slot_from_name, staging_dir

    company = get_company_or_404(db, code, user)
    if not (YEAR_MIN <= year <= YEAR_MAX):
        raise HTTPException(status_code=400, detail=f"Năm phải trong khoảng {YEAR_MIN}-{YEAR_MAX}")

    slug = company.slug or company.code
    raw_root = Path(settings.raw_data_path)
    base = raw_root / company.code / str(year)
    staging = staging_dir(raw_root, company.code, year)

    def _back(**params: str) -> RedirectResponse:
        from urllib.parse import urlencode

        qs = f"?{urlencode(params)}" if params else ""
        return RedirectResponse(
            url=f"/companies/{slug}/documents{qs}#ky-{year}", status_code=303
        )

    placed: list[tuple[str, str]] = []   # (đường dẫn tương đối, căn cứ)
    waiting: list[str] = []
    replaced_any = False
    for upload in files or []:
        if not upload or not upload.filename:
            continue
        ext = Path(upload.filename).suffix.lower()
        if ext not in {".xls", ".xlsx"}:
            raise HTTPException(
                status_code=400,
                detail=f"{upload.filename}: chỉ chấp nhận .xls / .xlsx (gặp {ext})",
            )
        staged = staging / _bcct_filename(upload.filename, year, ext)
        size = _write_upload_stream(upload, staged, expected_ext=ext)

        # Khớp tên là TỨC THÌ — không mở file khi tên đã phân giải được.
        slot = slot_from_name(upload.filename)
        basis = BASIS_NAME
        if slot is None:
            proposal = propose(staged, year=year, size_bytes=size)
            slot, basis = proposal.slot, proposal.basis
        if slot is None:
            waiting.append(staged.name)
            continue
        dest = _slot_destination(base, slot, upload.filename, year, ext)
        replaced_any = _place_in_slot(staged, dest, slot) or replaced_any
        placed.append((str(dest.relative_to(raw_root)), basis or ""))

    if not placed and not waiting:
        return _back(error="Chưa chọn file nào")

    if staging.is_dir() and not any(staging.iterdir()):
        staging.rmdir()

    sync_data_files(db, company)

    from app.auth_users import get_user_by_username

    ur = get_user_by_username(db, user.name)
    for rel, basis in placed:
        # Một workbook đăng ký cho nhiều biểu là NHIỀU dòng cùng `stored_path` — căn
        # cứ gán loại đúng cho cả nhóm.
        for row in db.scalars(select(DataFile).where(
            DataFile.company_id == company.id, DataFile.stored_path == rel
        )).all():
            row.slot_basis = basis
            row.uploaded_by = ur.id if ur else None
    if replaced_any:
        # THAY file = dòng đã nạp là của bộ file trước → dời phiên bản dữ liệu (#90).
        bump_data_version(db, company.id, year)
    db.commit()

    if waiting:
        return _back(error=(
            f"{len(waiting)} file chưa suy được loại: " + ", ".join(waiting)
            + ". Chọn loại cho từng file rồi nạp."
        ))
    return _back()


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
        raise HTTPException(status_code=503, detail="Trợ lý AI đang tắt. Bật trong /admin/ai.")
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
        request, "upload_diagnosis.html",
        {
            "user": user, "company": company, "year": year, "error": None,
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


def _resolve_within_root(rel_path: str) -> Path:
    """Resolve stored_path tuyệt đối, đảm bảo nằm trong raw_data_path (chống traversal)."""
    raw_root = Path(settings.raw_data_path).resolve()
    abs_path = (raw_root / rel_path).resolve()
    if raw_root not in abs_path.parents and abs_path != raw_root:
        raise HTTPException(status_code=400, detail="Đường dẫn file không hợp lệ")
    return abs_path


def _user_id_or_none(db: Session, user: SessionUser) -> int | None:
    """Id của tài khoản đang đăng nhập, `None` khi bản ghi đã bị xoá.

    Dùng cho việc ghi nhận "đã xem" (#100): đó là việc phụ của một lần vào trang,
    không đáng chặn cả trang bằng 403 như `_enqueue_ingest` phải làm.
    """
    from app.auth_users import get_user_by_username

    row = get_user_by_username(db, user.name)
    return row.id if row is not None else None


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

    from app.pipeline.data_files import sync_data_files

    # Reconcile registry với filesystem (bắt file demo có sẵn / xoá ngoài app).
    sync_data_files(db, company)

    # Mọi con số và mọi câu vướng mắc dựng ở `build_data_screen` → `period_readiness`.
    # Route KHÔNG tự đếm lại: hai đường đếm là hai đường lệch được nhau (ADR #24).
    screen = build_data_screen(db, company, add=add)

    # Trạng thái lượt nạp là TRỤC RIÊNG của #89, dựng ngoài `build_data_screen`: màn
    # dữ liệu nói kỳ đang thiếu gì, còn đây nói lượt nạp gần nhất đang ở đâu.
    ai_enabled = _ai_available()
    ingests = {
        p.year: ingest_status(db, company, p.year, ai_enabled=ai_enabled)
        for p in screen.periods
    }
    # Kết quả lượt nạp in ngay ở dòng kỳ dưới đây, nên nó hết là "chưa xem" (#100).
    mark_seen(db, ingests.values(), user_id=_user_id_or_none(db, user))

    return templates.TemplateResponse(
        request,
        "company_documents.html",
        {
            "user": user,
            "company": company,
            "screen": screen,
            "ingests": ingests,
            "human_size": _human_size,
            "fiscal_options": FISCAL_MONTH_OPTIONS,
            "bcqt_year_min": BCQT_YEAR_MIN,
            "bcqt_year_max": YEAR_MAX,
            "msg": msg,
            "error": error,
        },
    )


@router.post("/companies/{code}/documents/company", response_model=None)
def documents_set_company_fields(
    code: str,
    first_bcqt_year: str = Form(default=""),
    fiscal_start_month: str = Form(default="1"),
    audit_decision_date: str = Form(default=""),
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Sửa ba thuộc tính mức DN NGAY TRÊN màn dữ liệu (ADR #24 mục 3).

    Route riêng, KHÔNG mượn `update_company`: form đó nhận cả tên/MST và lấy tên
    rỗng làm tên mới, nên gửi từ đây sẽ ghi đè tên doanh nghiệp bằng mã.

    Không dời `data_version` và không viết lại cửa sổ kỳ đã lưu: niên độ chỉ là mặc
    định cho kỳ CHƯA có bản ghi, còn phạm vi KTSTQ là view tính lúc render (ADR #23).
    """
    from datetime import date as _date

    company = get_company_or_404(db, code, user)

    def _redirect(**params: str) -> RedirectResponse:
        qs = f"?{urlencode(params)}" if params else ""
        return RedirectResponse(url=f"/companies/{code}/documents{qs}", status_code=303)

    # Trống = "chưa biết" (NULL), không phải 0 — kỳ sớm nhất đọc NULL để biết mình
    # chưa đánh giá được. Nhập sai thì giữ nguyên giá trị cũ, không ghi đè bằng rác.
    raw_year = first_bcqt_year.strip()
    parsed_year: int | None = None
    if raw_year:
        try:
            parsed_year = int(raw_year)
        except ValueError:
            parsed_year = None
        if parsed_year is None or not (BCQT_YEAR_MIN <= parsed_year <= YEAR_MAX):
            return _redirect(
                error=f"Năm đầu nộp báo cáo quyết toán phải trong khoảng "
                f"{BCQT_YEAR_MIN}–{YEAR_MAX}."
            )

    try:
        month = int(fiscal_start_month)
    except ValueError:
        month = 0
    if month not in FISCAL_START_MONTHS:
        return _redirect(error="Tháng bắt đầu niên độ chỉ nhận giá trị từ 1 đến 12.")

    decision_date = None
    if audit_decision_date.strip():
        try:
            decision_date = _date.fromisoformat(audit_decision_date.strip())
        except ValueError:
            return _redirect(
                error="Ngày quyết định kiểm tra sau thông quan không hợp lệ "
                "(định dạng YYYY-MM-DD)."
            )

    company.first_bcqt_year = parsed_year
    company.fiscal_start_month = month
    company.audit_decision_date = decision_date
    db.commit()

    # Bốn mốc đầu quý là mốc luật; tháng khác vẫn lưu được nhưng phải nói rõ.
    notice = (
        ""
        if month in QUARTER_START_MONTHS
        else (
            f" Lưu ý: niên độ bắt đầu tháng {month} nằm ngoài bốn mốc đầu quý mà "
            "điểm a khoản 1 Điều 12 Luật Kế toán 88/2015 cho phép."
        )
    )
    return _redirect(msg="Đã lưu thuộc tính doanh nghiệp." + notice)


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

    from app.pipeline.data_files import sync_data_files

    if slot == "bcct":
        # Nhiều file/ô — giữ tên gốc đã làm sạch (thay nếu trùng tên).
        dest = dest_dir / _bcct_filename(file.filename, year, ext)
        replaced = dest.exists()
    else:
        # 1 file/ô — xoá file cùng slot đã có trên đĩa rồi ghi tên canonical.
        previous = _existing_slot_files(dest_dir, slot)
        for p in previous:
            p.unlink(missing_ok=True)
        dest = dest_dir / f"{stem}_{year}{ext}"
        replaced = bool(previous)

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
        from app.pipeline.file_intake import BASIS_OFFICER

        ur = get_user_by_username(db, user.name)
        row.uploaded_by = ur.id if ur else None
        # Nút này gắn với một loại đã biết — cán bộ chọn ô nào là chọn loại đó (#88).
        row.slot_basis = BASIS_OFFICER
        db.commit()

    # THAY file (không phải thêm) = bộ file của kỳ đã đổi trong khi dòng đã nạp là của
    # bộ trước → dời phiên bản dữ liệu (#90). Thêm file mới KHÔNG dời: dòng đã nạp vẫn
    # đúng với các file sinh ra chúng, và trục bộ file của `readiness` đã bắt ca đó.
    if replaced:
        bump_data_version(db, company.id, year)
        db.commit()

    label = SLOT_SHORT_VI.get(slot, slot)
    return _redirect(f"msg={label}+{year}+%C4%91%C3%A3+t%E1%BA%A3i+l%C3%AAn")


def _documents_redirect(company: Company, year: int, **params: str) -> RedirectResponse:
    """Về màn dữ liệu, neo đúng dòng kỳ vừa thao tác."""
    slug = company.slug or company.code
    qs = f"?{urlencode(params)}" if params else ""
    return RedirectResponse(url=f"/companies/{slug}/documents{qs}#ky-{year}", status_code=303)


def _period_file_path(company: Company, year: int, rel: str) -> Path:
    """Đường dẫn tuyệt đối của một file THUỘC kỳ đó, hoặc 400.

    Nhận đường dẫn tương đối vì file đang chờ chọn loại chưa có trong registry: nó
    nằm ngoài ba thư mục biểu nên `sync_data_files` không thấy, và `data_files.slot`
    không nhận rỗng. Đường dẫn tự do phải chặn thoát thư mục ngay tại đây.
    """
    raw_root = Path(settings.raw_data_path)
    target = raw_root / rel
    period_dir = (raw_root / company.code / str(year)).resolve()
    if (
        not target.resolve().is_relative_to(period_dir)
        or not target.is_file()
        or target.suffix.lower() not in {".xls", ".xlsx"}
    ):
        raise HTTPException(status_code=400, detail="Đường dẫn file không hợp lệ.")
    # Trả đường dẫn CHƯA resolve: mọi chỗ khác (registry, `_slot_destination`) làm việc
    # trong không gian chưa resolve, mà `data/` ở môi trường thật là symlink.
    return target


@router.post("/companies/{code}/documents/file-type", response_model=None)
def documents_set_file_type(
    code: str,
    year: int = Form(...),
    path: str = Form(...),
    slot: str = Form(...),
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Cán bộ sửa loại của một file — căn cứ gán loại thành "cán bộ chọn" (#88).

    Dùng chung cho file đã trong registry và file còn chờ chọn loại: cả hai đều được
    ĐẶT LẠI CHỖ trên đĩa rồi đồng bộ, vì loại của một file là hệ quả của chỗ đặt và
    tên, không phải một cột ghi đè được.
    """
    from app.pipeline.data_files import sync_data_files
    from app.pipeline.file_intake import BASIS_OFFICER, STAGING_SUBDIR

    company = get_company_or_404(db, code, user)
    if slot not in _UPLOAD_SLOTS:
        raise HTTPException(status_code=400, detail=f"Loại tài liệu không hợp lệ: {slot}")
    if not (YEAR_MIN <= year <= YEAR_MAX):
        raise HTTPException(status_code=400, detail=f"Năm phải trong khoảng {YEAR_MIN}-{YEAR_MAX}")

    src = _period_file_path(company, year, path)
    raw_root = Path(settings.raw_data_path)
    dest = _slot_destination(
        raw_root / company.code / str(year), slot, src.name, year, src.suffix.lower()
    )
    staging = src.parent
    replaced = _place_in_slot(src, dest, slot)
    if staging.name == STAGING_SUBDIR and staging.is_dir() and not any(staging.iterdir()):
        staging.rmdir()

    sync_data_files(db, company)
    rel = str(dest.relative_to(raw_root))
    for row in db.scalars(select(DataFile).where(
        DataFile.company_id == company.id, DataFile.stored_path == rel
    )).all():
        row.slot_basis = BASIS_OFFICER
    if replaced:
        bump_data_version(db, company.id, year)
    db.commit()

    label = SLOT_LABEL_VI.get(slot, slot).split(" — ")[0]
    return _documents_redirect(company, year, msg=f"Đã đặt {dest.name} thành {label}.")


@router.post("/companies/{code}/documents/file-book", response_model=None)
def documents_set_file_book(
    code: str,
    year: int = Form(...),
    path: str = Form(...),
    book: str = Form(default=""),
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Gán sổ quyết toán cho một file quyết toán, ngay trên dòng kỳ (#88).

    Sửa được cả sau này, cho file đã nằm sẵn trong hệ thống — DN nạp bằng dòng lệnh
    trước đây vẫn nạp lại được qua web. Một workbook đăng ký cho nhiều biểu là nhiều
    dòng cùng `stored_path`: gán sổ cho CẢ nhóm, để lại một dòng không sổ là đúng ca
    mà cổng kế hoạch nạp chặn.
    """
    company = get_company_or_404(db, code, user)
    target = _period_file_path(company, year, path)
    rel = str(target.relative_to(Path(settings.raw_data_path)))
    rows = db.scalars(select(DataFile).where(
        DataFile.company_id == company.id,
        DataFile.stored_path == rel,
        DataFile.slot.in_(SETTLEMENT_SLOTS),
    )).all()
    if not rows:
        raise HTTPException(status_code=400, detail="File này không phải file quyết toán.")

    new_book = normalize_book(book)
    changed = any((r.book or None) != new_book for r in rows)
    for row in rows:
        row.book = new_book
    if changed and any(r.parse_status == DataFileStatus.OK for r in rows):
        # Dòng đã nạp mang sổ cũ — bộ file không còn khớp dữ liệu, kỳ phải báo nạp lại.
        bump_data_version(db, company.id, year)
    db.commit()
    return _documents_redirect(
        company, year,
        msg=f"Đã gán {book_label(new_book)} cho {target.name}." if new_book
        else f"Đã bỏ nhãn sổ của {target.name}.",
    )


@router.post("/companies/{code}/documents/file/{file_id}/delete", response_model=None)
def documents_delete_file(
    code: str,
    file_id: int,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Xoá MỘT FILE THẬT, tức mọi đăng ký loại của nó.

    Registry đánh khoá theo (đường dẫn, loại): một workbook phục vụ ba biểu quyết
    toán là ba dòng cùng `stored_path`. Xoá một dòng rồi bỏ file khỏi đĩa để lại hai
    dòng trỏ vào chỗ trống — chúng chỉ biến mất ở lượt đồng bộ sau, nên cho tới lúc
    đó màn hình vẫn kể tên file đã xoá.
    """
    company = get_company_or_404(db, code, user)
    row = db.get(DataFile, file_id)
    if row is None or row.company_id != company.id:
        raise HTTPException(status_code=404, detail="Không tìm thấy file")
    abs_path = _resolve_within_root(row.stored_path)
    abs_path.unlink(missing_ok=True)
    # Một workbook phục vụ nhiều biểu là NHIỀU bản ghi cùng `stored_path` (#87): xoá
    # một bản ghi mà để lại các bản ghi anh em thì chúng trỏ vào đường dẫn vừa unlink.
    year = row.period_year
    siblings = db.scalars(
        select(DataFile).where(
            DataFile.company_id == company.id,
            DataFile.stored_path == row.stored_path,
        )
    ).all()
    for sibling in siblings:
        db.delete(sibling)
    # Bộ file của kỳ đã đổi mà dòng Tầng 1 vẫn là của bộ trước: dời phiên bản dữ liệu
    # trong CÙNG transaction với lượt xoá (#90). Không xoá dòng đã nạp (bảng Tầng 1
    # không có tham chiếu file nguồn) và KHÔNG tự chạy lại kiểm tra — chạy lại xoá rồi
    # dựng lại `Finding`, đưa `status`/`notes` cán bộ đã đánh về "mới" (ADR #24).
    bump_data_version(db, company.id, year)
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


# Ba hạn mức dưới đây CHỈ CÒN áp cho lưới 15 dòng nhúng trong màn xác nhận cột.
# Trang xem file thôi dùng đường đọc này từ #91: nó lấy ô qua điểm cuối cửa sổ, vốn
# không có trần dòng, trần cột lẫn trần kích thước file.
PREVIEW_ROWS = 100
PREVIEW_COLS = 40
# Grid preview nhúng trong màn xác nhận cột (WS1) — ít dòng để đối chiếu chỉ số cột.
REVIEW_PREVIEW_ROWS = 15
# Trên NGƯỠNG này thì KHÔNG dựng lưới nhúng. Mở workbook bằng openpyxl/pandas phải
# nạp bảng chuỗi dùng chung của cả file: đo trên BCCT 68MB của 006 mất 28-30 giây lúc
# máy rảnh và 125 giây khi worker đang nạp file khác — quá 100 giây Cloudflare cho phép,
# nên trang chết đúng vào lúc cán bộ cần nó nhất. Danh sách trang tính vẫn hiện (đọc
# thẳng từ zip, 0,00 giây), chỉ mất phần lưới ô.
PREVIEW_MAX_BYTES = 25 * 1024 * 1024


def _sheet_names_fast(path: Path) -> list[str] | None:
    """Tên các trang tính, đọc thẳng `xl/workbook.xml` trong file .xlsx — 0,00 giây.

    Trả None nếu không phải .xlsx đọc được (file .xls cũ, file hỏng) — người gọi lùi
    về đường pandas, vốn chỉ đắt với file lớn mà .xls thì không lớn.
    """
    if path.suffix.lower() != ".xlsx":
        return None
    try:
        with zipfile.ZipFile(path) as z:
            root = ET.fromstring(z.read("xl/workbook.xml"))
    except (OSError, zipfile.BadZipFile, ET.ParseError, KeyError):
        return None
    names = [
        el.get("name") for el in root.iter()
        if el.tag.rpartition("}")[2] == "sheet" and el.get("name")
    ]
    return names or None


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
    abs_path: Path, sheet: int | str = 0,
    max_rows: int = PREVIEW_ROWS, max_cols: int = PREVIEW_COLS,
) -> dict:
    """Đọc thô (không qua adapter) `max_rows × max_cols` ô đầu của một sheet Excel.

    Trả dict cho template: sheet_names, selected_sheet, columns (nhãn A/B/…), rows,
    truncated_rows/cols, error. Dùng chung cho trang xem file + grid nhúng màn review.
    """
    import pandas as pd

    out: dict = {
        "sheet_names": [], "selected_sheet": 0, "selected_sheet_name": None,
        "columns": [], "rows": [],
        "truncated_rows": False, "truncated_cols": False, "error": None,
        "skipped_reason": None,
    }

    fast_names = _sheet_names_fast(abs_path)
    try:
        too_big = abs_path.stat().st_size > PREVIEW_MAX_BYTES
    except OSError:
        too_big = False
    if fast_names and too_big:
        # File lớn: giữ danh sách trang tính (thứ cán bộ cần để chọn), bỏ lưới ô.
        out["sheet_names"] = fast_names
        sel = fast_names.index(sheet) if isinstance(sheet, str) and sheet in fast_names else 0
        out["selected_sheet"] = sel
        out["selected_sheet_name"] = fast_names[sel]
        limit_mb = PREVIEW_MAX_BYTES // 1024 // 1024
        out["skipped_reason"] = (
            f"File nặng hơn {limit_mb}MB — không dựng lưới xem trước (mở workbook mất "
            "hàng chục giây, trang sẽ hết giờ). Danh sách trang tính vẫn chọn được."
        )
        return out

    try:
        xls = pd.ExcelFile(abs_path)
        out["sheet_names"] = list(xls.sheet_names)
        # `sheet` là TÊN trang khi gọi từ màn review (trang parser thật sự đọc) và là
        # chỉ số khi gọi từ trang xem file. Tên không có trong workbook → về trang đầu.
        if isinstance(sheet, str):
            sel = out["sheet_names"].index(sheet) if sheet in out["sheet_names"] else 0
        else:
            sel = sheet if 0 <= sheet < len(out["sheet_names"]) else 0
        out["selected_sheet"] = sel
        out["selected_sheet_name"] = out["sheet_names"][sel] if out["sheet_names"] else None
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


def _mapped_columns(row: DataFile) -> dict[str, dict]:
    """`{chỉ số cột: {trường, nhãn, cần soát}}` — cột parser THẬT SỰ đọc ở file này.

    Cùng nguồn với màn xác nhận cột (`parse_detail` của lần đọc gần nhất), chỉ đổi
    chỗ hiện. File chưa từng nạp thì rỗng: công tắc không có gì để đánh dấu, và
    lưới nói ra điều đó thay vì đánh dấu bừa theo mẫu biểu.
    """
    detail = row.parse_detail_obj
    column_map = detail.get("column_map") or {}
    meta_by_field = {c.get("field"): c for c in (detail.get("columns") or [])}
    out: dict[str, dict] = {}
    for field, index in column_map.items():
        if not isinstance(index, int) or isinstance(index, bool):
            continue
        meta = meta_by_field.get(field) or {}
        out[str(index)] = {
            "field": field,
            "label": meta.get("label") or field,
            "needs": meta.get("review") == "needs_review",
        }
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
    """Trang xem file: điểm neo cho lưới cuộn + dữ liệu chú giải cột, KHÔNG đọc ô.

    Máy chủ không mở file ở đây nữa. Ô đi qua điểm cuối cửa sổ, nên trang dựng
    được cả với file 71,3 MB lẫn file bộ đọc không mở nổi — lỗi định dạng hiện
    thành thẻ lỗi trong lưới thay vì làm chết cả trang. Ba hạn mức cũ (100 dòng ·
    40 cột · 25 MB) biến mất cùng lượt đọc đó.
    """
    company = get_company_or_404(db, code, user)
    row = db.get(DataFile, file_id)
    if row is None or row.company_id != company.id:
        raise HTTPException(status_code=404, detail="Không tìm thấy file")
    abs_path = _resolve_within_root(row.stored_path)
    if not abs_path.is_file():
        raise HTTPException(status_code=404, detail="File không còn trên đĩa")

    slug = company.slug or company.code
    return templates.TemplateResponse(
        request,
        "document_preview.html",
        {
            "user": user,
            "company": company,
            "file": row,
            "slot_label": SLOT_LABEL_VI.get(row.slot, row.slot),
            "human_size": _human_size,
            "cells_url": f"/companies/{slug}/documents/file/{row.id}/cells",
            "selected_sheet": sheet,
            # Trang tính parser đọc: cán bộ chỉ định thắng lần đọc gần nhất. Chú
            # giải cột chỉ đúng trên ĐÚNG trang đó — trang khác thì lưới nói rõ.
            "parsed_sheet": row.sheet_override or row.parse_detail_obj.get("sheet") or "",
            "mapped_columns": _mapped_columns(row),
        },
    )


# Trần MỘT CỬA SỔ, không phải trần cả file: lưới cuộn hỏi từng khoảng dòng, còn
# hạn mức cũ (100 dòng · 40 cột · 25MB) chặn ở mức FILE nên 11/493 file không xem
# được và 52/170 trang tính bị cắt cột — đúng lúc việc của màn đó là soát cột.
MAX_WINDOW_ROWS = 1000
MAX_WINDOW_COLS = 1000
# Trần thời gian chờ một request được phép giữ, kể cả khi máy khách hỏi cao hơn:
# biên cắt của Cloudflare là 100 giây.
MAX_WAIT_SECONDS = 60.0


@router.get("/companies/{code}/documents/file/{file_id}/cells", response_model=None)
def documents_file_cells(
    code: str,
    file_id: int,
    sheet: int = Query(default=0, ge=0),
    row: int = Query(default=0, ge=0),
    rows: int = Query(default=100, ge=1, le=MAX_WINDOW_ROWS),
    col: int = Query(default=0, ge=0),
    cols: int = Query(default=60, ge=1, le=MAX_WINDOW_COLS),
    formulas: bool = Query(default=False),
    wait: float | None = Query(default=None, ge=0, le=MAX_WAIT_SECONDS),
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> Response:
    """Một cửa sổ ô dạng JSON, chỉ số 0-based, phục vụ từ kho đệm trích xuất một lần.

    `total_rows` / `total_cols` lấy từ KẾT QUẢ TRÍCH XUẤT chứ không từ khai báo
    kích thước trong file — file kết xuất khai `A1:ZZ9999` cho 12 dòng dữ liệu.

    `formulas=1` trả thêm từ điển thưa công thức mỗi dòng; tắt thì ô luôn là GIÁ
    TRỊ đã tính, không bao giờ là chuỗi `=SUM(...)`. Với `.xls` cũ thì
    `formulas_supported = false` kèm `formula_note` — lưới vẫn đầy dữ liệu, chỉ
    riêng công thức là không đọc được.

    Chưa có kho đệm thì lượt trích xuất chạy NỀN và request này chờ tối đa `wait`
    giây (mặc định theo cấu hình). Hết hạn chờ thì trả **202** kèm số dòng đã đọc
    để lưới hiện màn chờ và hỏi lại với `wait=0` — file 71,3 MB mất 164,6 giây,
    quá biên 100 giây của Cloudflare, nên giữ kết nối là chắc chắn đứt.
    """
    company = get_company_or_404(db, code, user)
    file_row = db.get(DataFile, file_id)
    if file_row is None or file_row.company_id != company.id:
        raise HTTPException(status_code=404, detail="Không tìm thấy file")
    abs_path = _resolve_within_root(file_row.stored_path)
    if not abs_path.is_file():
        raise HTTPException(status_code=404, detail="File không còn trên đĩa")

    budget = float(settings.preview_wait_seconds) if wait is None else wait
    try:
        # Dò định dạng NGAY trong request (đọc 512 byte đầu): file không mở được
        # phải ra lỗi ngay ở lượt hỏi đầu, không thành một màn chờ rồi mới lỗi.
        detected = detect_format(abs_path)
        if not detected.supported:
            raise UnsupportedFileFormat(detected)
        status = request_extract(abs_path, sheet, wait_s=budget)
        if not status.ready or status.extract is None:
            return JSONResponse(
                status_code=202,
                content={
                    "state": "extracting",
                    "first_open": True,
                    "sheet_index": sheet,
                    "rows_done": status.rows_done,
                    "elapsed_ms": status.elapsed_ms,
                    "format": detected.kind,
                    "format_label": detected.label,
                    "detail": (
                        "Đang trích xuất trang tính vào kho đệm. Đây là lần đầu mở "
                        "file này; các lần sau sẽ hiện ngay."
                    ),
                },
            )
        # CHỈ ĐỌC kho: không lùi về dựng đồng bộ ở đây. Dựng trong request là đúng
        # cái làm request chạy 46 giây với file 200.000 dòng và 164,6 giây với file
        # 71,3 MB — quá biên cắt 100 giây, tức mất trắng cả lượt xem.
        window = read_window(
            cache_file_for(abs_path, sheet), status.extract,
            row_start=row, n_rows=rows, col_start=col, n_cols=cols, with_formulas=formulas,
        )
    except UnsupportedFileFormat as e:
        # Nêu ĐỊNH DẠNG DÒ ĐƯỢC, không nhắc lại đuôi file: đuôi nói dối ở 38 file.
        return JSONResponse(
            status_code=415,
            content={
                "detail": str(e),
                "format": e.detected.kind,
                "format_label": e.detected.label,
                "format_supported": False,
            },
        )
    except SheetOutOfRange as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except CellReadError as e:
        return JSONResponse(
            status_code=422, content={"detail": str(e), "format_supported": True},
        )

    payload = {
        "state": "ready",
        "sheet_index": window.extract.sheet_index,
        "sheet_name": window.extract.sheet_name,
        "sheet_names": window.extract.sheet_names,
        "format": window.fmt,
        "format_label": window.format_label,
        "format_supported": True,
        "total_rows": window.total_rows,
        "total_cols": window.total_cols,
        "row_start": window.row_start,
        "col_start": window.col_start,
        "rows": window.rows,
        "formulas_supported": window.formulas_supported,
        "formula_note": window.formula_note,
        "build_ms": window.extract.build_ms,
        "from_cache": window.from_cache,
    }
    if formulas:
        payload["formulas"] = window.formulas
    return JSONResponse(payload)


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
    # Một trường ở bố cục mở rộng đọc bằng TỔNG nhiều cột con `(6a)+(6b)`, nên ô nhập
    # nhận CẢ nhóm (viết ngăn bởi dấu phẩy) chứ không phải một chỉ số (#95).
    groups = column_groups(column_map)
    view_cols = []
    for c in columns:
        field = c.get("field", "")
        cols = groups.get(field, [])
        view_cols.append({
            **c,
            "col_index": cols[0] if len(cols) == 1 else None,
            "col_indexes": cols,
            "col_value": ",".join(str(i) for i in cols),
            "col_group": len(cols) > 1,
            "checks": checks_reading(row.slot, field),
        })

    # Grid preview nhúng: nội dung THẬT của file (dòng/cột đầu) để đối chiếu chỉ số cột —
    # bảng chỉ-số-không thì cán bộ không biết cột 8 là gì. Annotate mỗi cột grid bằng
    # field đã map (tô màu) + cột needs_review (vàng). Số cột grid phủ đủ chỉ số đã map.
    mapped_idx = [i for cols in groups.values() for i in cols]
    grid_cols = min(max((max(mapped_idx) + 2 if mapped_idx else 0), 8), PREVIEW_COLS)
    abs_path = _resolve_within_root(row.stored_path)
    # Lưới xem trước phải là TRANG PARSER ĐỌC, không phải trang đầu workbook: file BCCT
    # kết xuất từ ECUS có trang `Tổng hợp` đứng trước trang `Chi tiết` đang được nạp,
    # xác nhận chỉ số cột trên trang tổng hợp là xác nhận nhầm bố cục.
    parsed_sheet = detail.get("sheet")
    preview = (
        _extract_sheet_preview(
            abs_path, row.sheet_override or parsed_sheet or 0, REVIEW_PREVIEW_ROWS, grid_cols,
        )
        if abs_path.is_file() else None
    )
    # Tô MỌI cột của nhóm, không riêng cột đầu: nhóm `(6a)+(6b)` mà chỉ sáng một cột
    # thì cán bộ tưởng cột kia không được đọc.
    col_annot = {
        idx: {"label": c["label"], "needs": c.get("review") == "needs_review"}
        for c in view_cols
        for idx in c["col_indexes"]
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
            # Trang tính: trang parser đọc lần gần nhất, trang cán bộ đã chỉ định, và
            # danh sách trang có trong workbook để chọn lại.
            "parsed_sheet": parsed_sheet,
            "sheet_override": row.sheet_override,
            "sheet_names": (preview or {}).get("sheet_names", []),
            # Cửa sổ kỳ đang dùng lệch niên độ DN (#50): CẢNH BÁO, không tự chọn hộ.
            "period_conflict": period_window_conflict(db, company.id, row.period_year),
        },
    )


def _parse_column_answer(
    raw: str | None, default: list[int], label: str, allow_groups: bool = False,
) -> list[int]:
    """Chỉ số cột cán bộ nhập cho MỘT trường: `"8"` hoặc `"5,6"` (nhóm cột con).

    Ô trống = giữ vị trí đề xuất. Ô sai định dạng thì ném ``ValueError`` kèm câu nói
    cho cán bộ — không đoán, cũng không lặng lẽ giữ giá trị cũ.

    ``allow_groups`` theo BỐ CỤC CỦA FILE, không theo hình dạng hiện tại của trường:
    ở bố cục mở rộng một trường đang đọc một cột (cột Tổng `(6)`) hoàn toàn có thể
    phải đổi sang nhóm cột con `(6a)+(6b)`, và đó là bản sửa hợp lệ — đẳng thức của
    biểu vẫn là cổng cuối. Ở bố cục chuẩn adapter đọc đúng một ô mỗi trường, nhận
    "5,6" ở đó là hứa một việc hệ thống không làm (#95).
    """
    text = (raw or "").strip()
    if not text:
        return list(default)
    cols: list[int] = []
    for token in re.split(r"[,\s;]+", text):
        if not token:
            continue
        try:
            idx = int(token)
        except ValueError:
            raise ValueError(f"{label}: “{token}” không phải chỉ số cột.") from None
        if idx < 0:
            raise ValueError(f"{label}: chỉ số cột phải từ 0 trở lên.")
        if idx in cols:
            raise ValueError(f"{label}: cột {idx} khai hai lần trong cùng một trường.")
        cols.append(idx)
    if not cols:
        return list(default)
    if len(cols) > 1 and not allow_groups:
        raise ValueError(
            f"{label}: bố cục file này đọc mỗi trường bằng đúng một cột, "
            "không nhận nhiều cột."
        )
    return cols


def _reject_shared_columns(groups: dict[str, list[int]]) -> None:
    """Hai trường về cùng một cột thì map sai — từ chối thay vì nạp một cột cho hai chỗ."""
    owner: dict[int, str] = {}
    for field, cols in sorted(groups.items()):
        label = FIELD_LABEL_VI.get(field, field)
        for idx in cols:
            if idx in owner:
                raise ValueError(
                    f"Cột {idx} được gán cho cả “{owner[idx]}” lẫn “{label}”. "
                    "Mỗi cột chỉ đọc cho một trường."
                )
            owner[idx] = label


@router.post("/companies/{code}/documents/file/{file_id}/review", response_model=None)
async def documents_confirm_review(
    code: str,
    request: Request,
    file_id: int,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Xác nhận map cột / sổ / trang tính rồi xếp job nạp lại → file advance
    `analyzed→parsed`, cột trong map resolve `officer-confirmed` → `verified`.

    Chuỗi advance: ``save_column_map`` (+ commit) → job ``ingest`` → ``record_parse_result``
    (committed=True). Lượt nạp đó ĐỌC THEO VỊ TRÍ vừa lưu: `ingest` nạp map của DN rồi
    truyền vào adapter, map cán bộ thắng mẫu biểu curate ở từng trường (ADR #24 mục 5).
    ``record_parse_result`` gọi ``resolve_officer_confirmed`` nên các cột vừa lưu map lên
    `officer-confirmed`, cổng review clear. Phần nạp nằm ở hàng đợi vì đọc file là việc
    hàng phút với bộ dữ liệu thật (xem DECISIONS 2026-08-06).
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

    form = await request.form()

    if not form_signature or not base_map:
        # File đọc hỏng thì KHÔNG có bố cục cột để xác nhận, nhưng vẫn phải ghim được
        # trang tính: nguyên nhân thường gặp là không trang nào khớp biểu chuẩn (workbook
        # cán bộ tự gộp — chèn cột, xoá khối tiêu đề → mọi cột lệch một ô). Ghim trang rồi
        # nạp lại là đường DUY NHẤT đưa file đó vào hệ thống mà không phải sửa file nguồn.
        picked = (form.get("sheet") or "").strip() or None
        if picked is None and row.sheet_override is None:
            return _redirect(
                "error=" + quote_plus("File này không có thông tin bố cục cột để xác nhận.")
            )
        row.sheet_override = picked
        db.commit()
        _enqueue_ingest(db, user, company, year, gate=False)
        return _back_to_period(company, year)

    # Map đầy đủ = cột officer sửa (field `needs_review`) chồng lên map đề xuất. Ô trống
    # giữ giá trị đề xuất để map không khuyết cột; ô SAI thì từ chối cả biểu mẫu thay vì
    # lặng lẽ giữ giá trị cũ — cán bộ vừa gõ một thứ và cần biết nó không dùng được.
    base_groups = column_groups(base_map)
    # Nhóm cột chỉ có nghĩa ở bố cục MỞ RỘNG (một trường = tổng nhiều cột con). Xét
    # theo bố cục của FILE chứ không theo hình dạng hiện tại của từng trường: đổi một
    # trường từ cột Tổng sang các cột con là bản sửa hợp lệ trên chính bố cục đó.
    allow_groups = row.parse_layout == "extended"
    groups: dict[str, list[int]] = {}
    try:
        for field, default_cols in base_groups.items():
            label = FIELD_LABEL_VI.get(field, field)
            groups[field] = _parse_column_answer(
                form.get(f"col_{field}"), default_cols, label, allow_groups,
            )
        _reject_shared_columns(groups)
    except ValueError as e:
        return _redirect("error=" + quote_plus(str(e)))

    # Ghi `int` khi một cột, `list` khi là nhóm cột con — giữ nguyên hình dạng map cũ
    # cho bố cục chuẩn, và diễn đạt được nhóm cho bố cục mở rộng (#95).
    column_map: dict[str, int | list[int]] = {
        f: (cols[0] if len(cols) == 1 else cols) for f, cols in groups.items()
    }

    # Cột đổi map so với map đã commit (base_map = map đang lưu ở parse_detail, đã sinh
    # ra dòng hiện tại). Chỉ có ý nghĩa khi file đã `parsed` → scoped re-run.
    changed_fields = {f for f, cols in groups.items() if base_groups.get(f) != cols}

    # Sổ quyết toán (book) — chỉ file settlement mang book; tờ khai luôn toàn pháp nhân.
    # Set NGAY trên row (cùng session) → commit dưới → run_ingest đọc data_files.book,
    # gom balances theo sổ (ADR #19 Revision — upload). Rỗng → None (một sổ).
    book_changed = False
    if slot in SETTLEMENT_SLOTS:
        new_book = normalize_book(form.get("book"))
        book_changed = (row.book or None) != new_book
        row.book = new_book

    # Trang tính: ô trống = "để hệ thống tự chọn", chọn tên = ghim trang đó. Ghim đúng
    # trang đang đọc vẫn được lưu (không tự xoá), nếu không thì lần sửa sau lặng lẽ trả
    # quyền chọn về cho máy. So sánh trang SẼ ĐỌC (không phải giá trị ô) để biết có đổi
    # thật hay không — đổi trang là đổi toàn bộ dòng, xử lý như đổi sổ: chạy lại cả năm.
    new_sheet = (form.get("sheet") or "").strip() or None
    read_sheet = detail.get("sheet")  # trang lượt nạp gần nhất đã đọc
    unpinned = row.sheet_override is not None and new_sheet is None
    sheet_changed = unpinned or (row.sheet_override or read_sheet) != (new_sheet or read_sheet)
    row.sheet_override = new_sheet

    evidence = {c["field"]: c.get("evidence") for c in columns if c.get("field")}

    from app.auth_users import get_user_by_username
    from app.pipeline.saved_map import save_column_map

    ur = get_user_by_username(db, user.name)
    save_column_map(
        db, company.id, slot, form_signature, column_map,
        evidence=evidence, confirmed_by=ur.id if ur else None,
    )
    db.commit()

    # File đã `parsed` + có cột đổi map → chạy lại CHỈ check đọc cột đã đổi (scoped,
    # ADR #18). Finding tham chiếu Tầng 1 qua evidence_refs (table + filter theo mã
    # hàng), KHÔNG theo id dòng → dòng thay khi re-ingest không làm treo finding của
    # check KHÔNG chạy lại (khoá lọc = mã hàng vẫn đúng vì cột mã không đổi). Nếu cột
    # KHOÁ (mã) đổi thì khoá lọc đổi → mở rộng ra mọi check đọc slot (gồm C2.1/C2.2).
    # ĐỔI SỔ (book) trên file đã parsed → gom nội-sổ + union cross-layer đổi trên diện
    # rộng → chạy lại TOÀN BỘ năm (only=None).
    affected: set[str] = set()
    if was_parsed and changed_fields:
        from app.checks.registry import checks_reading, checks_reading_slot

        for f in changed_fields:
            affected.update(checks_reading(slot, f))
        if _SLOT_KEY_FIELD.get(slot) in changed_fields:
            affected.update(checks_reading_slot(slot))
    run_full = was_parsed and (book_changed or sheet_changed)
    then_run_checks: dict | None = None
    if was_parsed and (affected or run_full):
        then_run_checks = {"only": None if run_full else sorted(affected)}
        log_access(
            db, username=user.name, action=ACTION_RUN_CHECKS,
            company_code=company.code,
            detail=(
                f"year={year} "
                f"only={'ALL' if run_full else ','.join(sorted(affected))} (confirm-review)"
            ),
        )

    # Re-ingest thật (commit dòng) chạy ở worker — record_parse_result đọc saved-map vừa
    # ghi để nâng các cột lên officer-confirmed → verified → cổng review clear, file thành
    # `parsed`. Job nối tiếp job chạy kiểm tra khi cần, đúng thứ tự.
    _enqueue_ingest(
        db, user, company, year, gate=False, then_run_checks=then_run_checks,
    )
    return _back_to_period(company, year)


@router.post("/companies/{code}/documents/ingest", response_model=None)
def documents_ingest_year(
    code: str,
    year: int = Form(...),
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Nạp dữ liệu của 1 kỳ từ file đã tải lên. ĐI QUA cổng xác nhận cột (`gate=True`).

    Từ #88, ô thả file KHÔNG xếp việc nạp nữa, nên nút này là đường nạp DUY NHẤT
    trên web. Chạy `gate=False` ở đây là để một cấu trúc chưa ai xác nhận ghi thẳng
    dòng bằng cột đoán được — đúng kiểu hỏng ADR #15/#18 dựng cổng ra để chặn. Cổng
    tự mở sau lần đầu: map cán bộ đã lưu được nâng lên "đã xác nhận" nên lượt sau
    trả rỗng và đi thẳng (ADR #24 mục 8), không quay vòng cán bộ.

    Tầng chặn SỚM của gán sổ (#88): còn file quyết toán chưa gán sổ thì không xếp
    việc, để cán bộ không chờ hết một lượt nạp rồi mới nhận lỗi kế hoạch. Tầng chặn
    muộn (`IngestPlanError`) giữ nguyên cho đường dòng lệnh và mọi đường khác.
    """
    company = get_company_or_404(db, code, user)
    # Khoá sổ chặn TRƯỚC khi xếp job (#88): file quyết toán chưa gán sổ mà nạp tiếp
    # thì các sổ gộp thành một, im lặng.
    lock = book_lock(db, company.id, year)
    if lock.locked:
        return _documents_redirect(company, year, error=lock.message)
    # `gate=True` (#88): từ khi ô thả file không tự xếp job nữa, đây là đường nạp DUY
    # NHẤT trên web — để ngỏ cổng thì cấu trúc chưa ai xác nhận sẽ ghi dòng từ cột
    # đoán. Cổng tự mở sau lần xác nhận đầu của mỗi (DN × cấu trúc) nên không quay vòng.
    _enqueue_ingest(db, user, company, year, gate=True)
    return _back_to_period(company, year)


@router.get("/companies/{code}/documents/ingest.json")
def documents_ingest_status(
    code: str,
    year: int = Query(...),
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> dict:
    """Trạng thái lượt nạp gần nhất của một kỳ — bộ đếm poll của dòng kỳ đọc ở đây.

    Trả đủ bốn trạng thái công việc (đang chờ · đang chạy · xong · hỏng) cộng dạng
    kết quả khi xong, kèm chữ và nút đã dựng sẵn (xem `app/pipeline/ingest_status.py`).
    """
    company = get_company_or_404(db, code, user)
    status = ingest_status(db, company, year, ai_enabled=_ai_available())
    if status is None:
        return {"status": None}
    # Trả về một trạng thái đã dừng nghĩa là dòng kỳ vừa in kết quả cuối tại chỗ (#100).
    mark_seen(db, [status], user_id=_user_id_or_none(db, user))
    return status.as_dict()


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
    tôn trọng, không ghi đè. `reset=1` → về mặc định (`is_manual=False`), ingest sau tự suy.

    Từ #49: cửa sổ kỳ là selector của vế BCCT (`declaration_scope`) nên sửa cửa sổ ĐỔI
    kết quả kiểm tra mà KHÔNG qua ingest — đúng ca `data_version` sinh ra để bắt (WS3).
    Bump trong CÙNG transaction với thay đổi cửa sổ. Không cần nạp lại dữ liệu nữa:
    mọi dòng đã nằm trong DB (#48), chỉ cần chạy lại kiểm tra.
    """
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
            row.data_version = (row.data_version or 0) + 1
            db.commit()
        return _redirect(
            msg=f"Đã đặt kỳ năm {year} về mặc định — bấm Chạy kiểm tra để áp dụng"
        )

    try:
        pf = date.fromisoformat(period_from)
        pt = date.fromisoformat(period_to)
    except ValueError:
        return _redirect(error="Ngày không hợp lệ (định dạng YYYY-MM-DD)")

    # Cùng bộ bất biến với đường hệ suy từ tiêu đề file (#66) — trước đây chỗ này chỉ
    # kiểm `pf <= pt`, nên kỳ 2024 đặt cửa sổ 2022 vẫn lưu được.
    errors = period_window_errors(year, pf, pt)
    if errors:
        return _redirect(error=" ".join(errors))
    dups = duplicate_period_windows(db, company.id, year, pf, pt)
    if dups:
        return _redirect(
            error=f"Cửa sổ này trùng khít kỳ {', '.join(str(y) for y in dups)}. "
            "Hai kỳ khác nhau không thể cùng một khoảng ngày."
        )

    if row is None:
        row = CompanyPeriod(company_id=company.id, period_year=year)
        db.add(row)
    row.period_from = pf
    row.period_to = pt
    row.is_manual = True
    row.data_version = (row.data_version or 0) + 1
    db.commit()
    return _redirect(
        msg=f"Đã lưu kỳ năm {year} — bấm Chạy kiểm tra để áp dụng"
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
        raise HTTPException(
            status_code=403,
            detail="Tài khoản của phiên đăng nhập này không còn tồn tại. Hãy đăng nhập lại.",
        )

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
    """Xếp hàng sinh AI tổng quan cho 1 kiểm tra (DN, năm) — CHẠY NỀN (ADR #21 mục 5-6).

    SỬA quyết định "sinh đồng bộ trong request" của ADR #18 Rev WS3: job giờ đi
    vào worker RIÊNG chỉ nhận kind AI, nên hàng đợi kiểm tra vẫn không phải chờ
    lời gọi LLM — tính chất mà ADR #18 bảo vệ — mà vẫn có job row (traceback, ai
    tiêu token, trang công việc, thu hồi job treo).

    Trả 303 về ĐÚNG chỗ cán bộ đang đọc, KHÔNG chuyển sang `/jobs/{id}` như chạy
    kiểm tra: tổng quan là một đoạn nằm trong nhóm đang mở, mà trang doanh nghiệp
    không khôi phục vị trí cuộn lẫn nhóm đang mở.
    """
    from app.ai.config import get_setting
    from app.ai.limits import check_daily_budget
    from app.ai.overview import start_overview_job
    from app.audit import ACTION_AI_OVERVIEW
    from app.auth_users import get_user_by_username

    company = get_company_or_404(db, code, user)

    def _back(**params: str) -> RedirectResponse:
        from urllib.parse import urlencode

        qs = urlencode({"year": year, **params})
        return RedirectResponse(
            url=f"/companies/{company.slug or company.code}?{qs}#group-{check}",
            status_code=303,
        )

    if not get_setting("enabled"):
        return _back(error="Trợ lý AI đang tắt. Bật trong /admin/ai.")
    if not get_setting("api_key"):
        return _back(error="Chưa cấu hình mã API cho AI. Vào /admin/ai để thiết lập.")
    # Trần ngày chặn TRƯỚC khi xếp hàng. Giới hạn tin nhắn/giờ KHÔNG áp: nó là
    # guard của trợ lý chat, một lượt sinh tổng quan không được khoá trợ lý của
    # cán bộ một tiếng (ADR #21 mục 11).
    try:
        check_daily_budget(db)
    except HTTPException as e:
        return _back(error=str(e.detail))

    user_row = get_user_by_username(db, user.name)
    if user_row is None:
        return _back(error="Tài khoản của phiên đăng nhập này không còn tồn tại. Hãy đăng nhập lại.")

    try:
        job_id, existing = start_overview_job(
            db, company=company, period_year=year, check_code=check,
            created_by=user_row.id, username=user.name,
        )
    except Exception as e:  # noqa: BLE001 — báo lỗi xếp hàng ngay tại chỗ
        db.rollback()
        return _back(error=f"Không xếp hàng được: {type(e).__name__}: {str(e)[:200]}")

    log_access(db, username=user.name, action=ACTION_AI_OVERVIEW,
               company_code=company.code, detail=f"year={year} check={check} job={job_id}")
    if existing:
        return _back(msg=f"Tổng quan {check} đang được viết (công việc #{job_id}).")
    return _back(msg=f"Đã xếp hàng viết tổng quan {check} năm {year} (công việc #{job_id}).")


@router.post("/companies/{code}/overview-batch", response_model=None)
def generate_overview_batch(
    code: str,
    year: int = Form(...),
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    """Một nút cho cả năm: sinh tổng quan cho kiểm tra chưa có / đã cũ (ADR #21 mục 9).

    ADR #18 bác sinh TỰ ĐỘNG sau mỗi lần chạy kiểm tra (hàng trăm lời gọi mỗi
    lần chạy cả bộ, phần lớn không ai đọc). Đây là nút TƯỜNG MINH do cán bộ bấm.
    """
    from app.ai.config import get_setting
    from app.ai.limits import check_daily_budget
    from app.ai.overview import checks_needing_overview
    from app.audit import ACTION_AI_OVERVIEW
    from app.auth_users import get_user_by_username
    from app.jobs import enqueue_job
    from app.models.job import JobKind

    company = get_company_or_404(db, code, user)

    def _back(**params: str) -> RedirectResponse:
        from urllib.parse import urlencode

        return RedirectResponse(
            url=f"/companies/{company.slug or company.code}?{urlencode({'year': year, **params})}",
            status_code=303,
        )

    if not get_setting("enabled"):
        return _back(error="Trợ lý AI đang tắt. Bật trong /admin/ai.")
    if not get_setting("api_key"):
        return _back(error="Chưa cấu hình mã API cho AI. Vào /admin/ai để thiết lập.")
    try:
        check_daily_budget(db)
    except HTTPException as e:
        return _back(error=str(e.detail))

    targets = checks_needing_overview(db, company.id, year)
    if not targets:
        return _back(msg="Mọi kiểm tra có phát hiện đều đã có tổng quan còn mới.")

    user_row = get_user_by_username(db, user.name)
    if user_row is None:
        return _back(error="Tài khoản của phiên đăng nhập này không còn tồn tại. Hãy đăng nhập lại.")

    job = enqueue_job(
        db, kind=JobKind.AI_OVERVIEW_BATCH,
        payload={"company_code": company.code, "year": year, "username": user.name},
        created_by=user_row.id, company_id=company.id, period_year=year,
    )
    log_access(db, username=user.name, action=ACTION_AI_OVERVIEW,
               company_code=company.code, detail=f"batch year={year} n={len(targets)}")
    return _back(
        msg=f"Đã xếp hàng viết tổng quan cho {len(targets)} kiểm tra (công việc #{job.id})."
    )


@router.get("/companies/{code}/overview.json")
def overview_status(
    code: str,
    year: int = Query(...),
    check: str = Query(...),
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> dict:
    """Trạng thái sinh tổng quan — poller thay text tại chỗ khi job xong.

    KHÔNG trả chi phí/token/model: khối tổng quan trên trang doanh nghiệp chỉ
    hiện mốc sinh, cờ cũ và trạng thái đang chạy (ADR #21 mục 10).
    """
    from app.models import CheckOverview

    company = get_company_or_404(db, code, user)
    ov = db.scalar(
        select(CheckOverview).where(
            CheckOverview.company_id == company.id,
            CheckOverview.period_year == year,
            CheckOverview.check_code == check,
        )
    )
    if ov is None:
        return {"status": None}

    status, error = ov.status, ov.error
    # Job chết giữa chừng (server restart → thu hồi job treo) không kịp cập nhật
    # dòng tổng quan, nên dòng đứng nguyên `running`. Đọc trạng thái job để cán
    # bộ thấy lỗi thay vì một vòng xoay không bao giờ dừng.
    if status == CheckOverview.STATUS_RUNNING and ov.job_id is not None:
        from app.models.job import Job, JobStatus

        job = db.get(Job, ov.job_id)
        if job is None or job.status == JobStatus.FAILED.value:
            status = CheckOverview.STATUS_FAILED
            error = (job.error if job is not None and job.error
                     else "Công việc sinh tổng quan đã dừng.")
    return {
        "status": status,
        "content": ov.content or "",
        "error": error,
        "job_id": ov.job_id,
        "generated_at": ov.generated_at.isoformat() if ov.generated_at else None,
    }


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
    period_windows = load_period_windows(db, company.id, years=years)

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
            # Trong cùng mức: phát hiện nhiều tiền trước (sổ yêu cầu 3.1, 4.1). Phát
            # hiện chưa quy ra tiền được (`value_vnd` NULL) xuống cuối, không lẫn vào
            # nhóm giá trị nhỏ. Check chưa quy tiền thì cả nhóm NULL → giữ thứ tự mã
            # như cũ.
            .order_by(
                Finding.severity,
                Finding.value_vnd.is_(None),
                Finding.value_vnd.desc(),
                Finding.subject_key,
            )
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

    # Kiểm tra CHƯA ĐÁNH GIÁ ĐƯỢC — tách khỏi "đã đánh giá, 0 phát hiện". Cả hai đều
    # không sinh nhóm phát hiện nào, nên nếu không liệt kê riêng thì trên trang chúng
    # giống hệt nhau. Không phụ thuộc bộ lọc ?book= (trạng thái tính theo toàn pháp nhân).
    #
    # Gom theo LỚP CÁCH GỠ ĐÃ LƯU (#97) — đây là nơi đọc thứ hai của spec mục 2. Đích
    # tính lại lúc hiển thị, không lưu (ADR #24 mục 2).
    not_evaluable_groups: tuple = ()
    if selected_year is not None:
        not_evaluable_groups = not_evaluable_panel(
            db, company, selected_year, specs=all_specs
        )
    not_evaluable_count = sum(len(g.items) for g in not_evaluable_groups)

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

    # Tag phạm vi KTSTQ tính LÚC RENDER (#54) — không lưu state nào trên finding.
    # Phát hiện neo được vào ngày (mã có dòng tờ khai) → so ngày với cửa sổ 5 năm;
    # phát hiện thuần cân đối (tính trên trọn kỳ) → nói kỳ rộng hơn phạm vi.
    scope_tags: dict[int, str] = {}
    audit_scope_window = None
    if company.audit_decision_date is not None and selected_year is not None:
        audit_scope_window = audit_window(company.audit_decision_date)
        displayed = [f for _, rows_, _, _ in ordered_groups for f in rows_]
        period_status = "inside"
        for r in scope_coverage(db, company) or []:
            if r.period_year == selected_year:
                period_status = r.status
                break
        spans = declaration_spans(
            db, company.id, selected_year,
            sorted({f.subject_key for f in displayed if f.subject_key}),
        )
        for f in displayed:
            tag = finding_scope_tag(
                audit_scope_window, spans.get(f.subject_key), period_status
            )
            if tag:
                scope_tags[f.id] = tag

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

    # Phát hiện + điểm của kỳ có tính trên phiên bản dữ liệu cũ không (#90). Cùng phép
    # so mà tổng quan AI dùng, nay áp cho cả hai con số trên màn này. Hiện nhãn, KHÔNG
    # tự chạy lại và KHÔNG giấu số.
    results_stale_now = (
        results_stale(db, company.id, selected_year) if selected_year is not None else False
    )

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
            "not_evaluable_groups": not_evaluable_groups,
            "not_evaluable_count": not_evaluable_count,
            "focus_check": focus,
            "page": page,
            "page_size": _PAGE_SIZE,
            "preview_per_group": _PREVIEW_PER_GROUP,
            "year_score": year_score,
            "all_specs": all_specs,
            "has_data": has_data,
            "checks_run": checks_run,
            "results_stale": results_stale_now,
            "scope_tags": scope_tags,
            "audit_scope_window": audit_scope_window,
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

    Với `declaration_lines`, cặp (`company_id`, `period_year`) trong filter được
    dịch sang `declaration_scope` — bằng chứng phải trả về ĐÚNG tập dòng check đã
    đọc, mà từ ADR #23 T1 tập đó chọn theo cửa sổ ngày chứ không theo nhãn nạp.
    """
    table = ref.get("table")
    model = _EVIDENCE_MODELS.get(table)
    if model is None:
        return [], []
    filt = dict(ref.get("filter") or {})
    stmt = select(model)
    if model is DeclarationLine and "company_id" in filt and "period_year" in filt:
        stmt = stmt.where(
            declaration_scope(db, filt.pop("company_id"), filt.pop("period_year"))
        )
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
        "label": SLOT_LABEL_VI["m15"],
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
            ("import_qty", "Nhập trong kỳ", "num"),
            ("reexport_qty", "Tái xuất", "num"),
            ("repurpose_qty", "Chuyển MĐSD", "num"),
            ("production_out_qty", "Xuất SX", "num"),
            ("other_out_qty", "Xuất khác", "num"),
            ("closing_qty", "Tồn cuối", "num"),
            ("source_file", "Nguồn file", "file"),
        ],
    },
    "m15a": {
        "model": SpBalance,
        "label": SLOT_LABEL_VI["m15a"],
        "code_field": "product_code",
        "code_label": "Mã TP",
        "view_cols": [
            ("row_no", "STT", "num"),
            ("product_code", "Mã TP", "item-link"),
            ("product_name", "Tên TP", "wrap"),
            ("unit", "ĐVT", ""),
            ("opening_qty", "Tồn đầu", "num"),
            ("intake_qty", "Nhập kho từ SX", "num"),
            ("repurpose_qty", "Chuyển MĐSD", "num"),
            ("export_qty", "Xuất khẩu", "num"),
            ("other_out_qty", "Xuất khác", "num"),
            ("closing_qty", "Tồn cuối", "num"),
            ("source_file", "Nguồn file", "file"),
        ],
    },
    "m16": {
        "model": Norm,
        "label": SLOT_LABEL_VI["m16"],
        "code_field": "material_code",
        # Mẫu 16 là bảng CẶP: mỗi dòng mang cả mã TP lẫn mã NVL. Lọc một cột thôi thì
        # tra mã TP ở đây ra bảng rỗng, đọc như "không có định mức" — mà C4.9 lại trỏ
        # sang đúng bảng này bằng mã TP.
        "search_fields": ("material_code", "product_code"),
        "code_label": "Mã NVL hoặc mã TP",
        "view_cols": [
            ("product_code", "Mã SP", "item-link"),
            ("product_name", "Tên SP", "wrap"),
            ("product_unit", "ĐVT SP", ""),
            ("material_code", "Mã NVL", "item-link"),
            ("material_name", "Tên NVL", "wrap"),
            ("material_unit", "ĐVT NVL", ""),
            ("norm_qty", "Định mức", "num"),
            ("source_file", "Nguồn file", "file"),
        ],
    },
    "bcct": {
        "model": DeclarationLine,
        "label": SLOT_LABEL_VI["bcct"],
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
            ("unit_price", "Đơn giá", "price"),
            ("currency", "Nguyên tệ", ""),
            ("value_total", "Trị giá (VND)", "num"),
            ("partner", "Đối tác", ""),
            ("source_file", "Nguồn file", "file"),
        ],
    },
}

# Bảng Tầng 1 → tab trên màn dữ liệu gốc. Dùng để dựng link "Dữ liệu gốc →" từ
# một phát hiện: bảng lấy theo `evidence_refs` chứ không đoán theo `subject_type`
# — C1.2 có subject là mã NVL nhưng bằng chứng nằm ở tờ khai, link sang M15 sẽ ra
# bảng rỗng.
_DATA_TAB_BY_TABLE = {
    "nvl_balances": "m15",
    "sp_balances": "m15a",
    "norms": "m16",
    "declaration_lines": "bcct",
}


def raw_data_url(company: Company, year: int | None, finding: Finding) -> str | None:
    """Link tới bảng dữ liệu gốc đã lọc sẵn theo mã của phát hiện.

    Trả None khi không xác định được bảng (phát hiện tổ hợp trỏ vào bảng
    `findings`, hoặc phát hiện không có mã đối tượng).
    """
    if not finding.subject_key or year is None:
        return None
    tab = next(
        (
            _DATA_TAB_BY_TABLE[ref["table"]]
            for ref in (finding.evidence_refs or [])
            if isinstance(ref, dict) and ref.get("table") in _DATA_TAB_BY_TABLE
        ),
        None,
    )
    if tab is None:
        return None
    params = {"year": year, "table": tab, "q": finding.subject_key}
    # `declaration_lines` không có cột `book` — lọc sổ chỉ áp cho bảng BCQT.
    if finding.book and tab != "bcct":
        params["book"] = finding.book
    if tab == "bcct":
        codes = (finding.details or {}).get("import_codes") or \
                (finding.details or {}).get("export_codes")
        if codes:
            params["customs"] = ",".join(codes)
    slug = company.slug or company.code
    return f"/companies/{slug}/data?{urlencode(params)}"


templates.env.globals["raw_data_url"] = raw_data_url

# Tên bảng Tầng 1 bằng tiếng Việt — trang chứng cứ từng in thẳng tên bảng DB.
# Nhãn khối chứng cứ ở trang phát hiện. SUY từ bảng nhãn duy nhất qua map bảng → loại
# tài liệu (#98) — gõ lại tên ở đây là cách sinh ra tên thứ hai cho cùng một loại.
# `findings` không phải loại tài liệu Tầng 1 nên có nhãn riêng.
_EVIDENCE_TABLE_LABEL = {
    table: SLOT_LABEL_VI[slot] for table, slot in _DATA_TAB_BY_TABLE.items()
} | {"findings": "Phát hiện nguồn"}

# Khoá bộ lọc chứng cứ → nhãn. `__in` là hậu tố cú pháp của `_resolve_evidence`.
_EVIDENCE_FILTER_LABEL = {
    "material_code": "Mã NVL",
    "product_code": "Mã TP",
    "item_code": "Mã hàng",
    "customs_code": "Loại hình",
    "book": "Sổ quyết toán",
    "declaration_no": "Số tờ khai",
    "id": "Mã phát hiện",
    "period_year": "Kỳ khai",
}
# Khoá kỹ thuật, không nói thêm gì cho cán bộ (trang đã ghi rõ DN và kỳ).
# `period_year__in` KHÔNG bị ẩn: định mức kế thừa (issue #60) nằm ở kỳ khác kỳ phát
# hiện, và đó chính là thông tin cán bộ cần thấy.
_EVIDENCE_FILTER_HIDDEN = {"company_id", "period_year"}


def _describe_evidence_filter(filt: dict) -> str:
    """Bộ lọc chứng cứ thành câu đọc được, thay cho JSON thô."""
    parts = []
    for key, value in filt.items():
        field = key[:-4] if key.endswith("__in") else key
        if key in _EVIDENCE_FILTER_HIDDEN:
            continue
        label = _EVIDENCE_FILTER_LABEL.get(field, field)
        text = ", ".join(str(v) for v in value) if isinstance(value, list | tuple) \
            else str(value)
        parts.append(f"{label}: {text}")
    return " · ".join(parts) if parts else "toàn bộ dòng của kỳ"


def _evidence_data_url(company: Company, year: int, ref: dict) -> str | None:
    """Link mở bảng dữ liệu gốc đúng bằng bộ lọc của khối chứng cứ này."""
    tab = _DATA_TAB_BY_TABLE.get(ref.get("table"))
    if tab is None:
        return None
    filt = ref.get("filter") or {}
    params: dict[str, str | int] = {"year": year, "table": tab}
    for key in ("material_code", "product_code", "item_code"):
        if filt.get(key):
            params["q"] = filt[key]
            break
    codes = filt.get("customs_code__in") or filt.get("customs_code")
    if codes:
        params["customs"] = ",".join(codes) if isinstance(codes, list | tuple) else codes
    if filt.get("book") and tab != "bcct":
        params["book"] = filt["book"]
    if filt.get("declaration_no"):
        params["decl_no"] = filt["declaration_no"]
    slug = company.slug or company.code
    return f"/companies/{slug}/data?{urlencode(params)}"

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
    """Format value theo loại cột. Dấu phân cách theo `app/formatting.py`."""
    if value is None:
        return ""
    if cls == "num":
        return fmt_qty(value)
    if cls == "price":
        return fmt_price(value)
    if cls == "date" and hasattr(value, "strftime"):
        return fmt_date(value)
    if cls == "file" and isinstance(value, str):
        # `source_file` lưu đường dẫn đầy đủ trên máy chủ. Cán bộ cần TÊN FILE để
        # tìm lại trong Excel; đường dẫn máy chủ không có lý do gì phải in ra.
        return PurePosixPath(value.replace("\\", "/")).name
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


def _parse_iso_date(raw: str) -> date | None:
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


@router.get("/companies/{code}/scope", response_class=HTMLResponse)
def company_audit_scope(
    code: str,
    request: Request,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Màn độ phủ: chiếu cửa sổ kiểm tra 5 năm lên các kỳ quyết toán (ADR #23 T4).

    Nói CẢ HAI ngôn ngữ — khoảng ngày và danh sách kỳ — vì mẫu 01/QĐKT (PL II TT
    121/2025) để "Phạm vi kiểm tra" là dòng trống tự do, cán bộ có thể ghi theo cách
    nào cũng được. Không có ngày quyết định → 404 (màn này không tồn tại cho DN đó).
    """
    company = get_company_or_404(db, code, user)
    rows = scope_coverage(db, company)
    if rows is None:
        raise HTTPException(
            status_code=404,
            detail="Doanh nghiệp chưa đặt ngày quyết định kiểm tra sau thông quan",
        )
    window = audit_window(company.audit_decision_date)
    return templates.TemplateResponse(
        request,
        "company_scope.html",
        {
            "user": user,
            "company": company,
            "window": window,
            "rows": rows,
            "audit_years": AUDIT_YEARS,
        },
    )


@router.get("/companies/{code}/data", response_class=HTMLResponse)
def company_data(
    code: str,
    request: Request,
    year: int = Query(...),
    table: str = Query("m15"),
    q: str = Query("", description="Lọc theo mã"),
    decl_no: str = Query("", description="Lọc theo số tờ khai (BCCT)"),
    customs: str = Query("", description="Lọc loại hình, ngăn bằng dấu phẩy (BCCT)"),
    date_from: str = Query("", description="Ngày ĐK từ, dạng YYYY-MM-DD (BCCT)"),
    date_to: str = Query("", description="Ngày ĐK đến, dạng YYYY-MM-DD (BCCT)"),
    book: str = Query("", description="Lọc theo sổ quyết toán (bảng BCQT)"),
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
    # `declaration_lines` không có cột `book`; các bảng BCQT không có ngày/số tờ khai.
    # Bộ lọc nào không áp được cho bảng đang xem thì cũng không hiện trên form.
    is_bcct = model is DeclarationLine
    has_book = hasattr(model, "book")

    stmt = select(model).where(model.company_id == company.id, model.period_year == year)
    if q:
        # Bảng nào mang nhiều cột mã (Mẫu 16: mã TP + mã NVL) thì tra trúng cột nào
        # cũng ra. Bảng một cột giữ nguyên hành vi cũ.
        search_fields = config.get("search_fields") or (code_field,)
        stmt = stmt.where(
            or_(*(getattr(model, f).contains(q) for f in search_fields))
        )
    if book and has_book:
        stmt = stmt.where(model.book == book)
    if is_bcct:
        if decl_no:
            stmt = stmt.where(model.declaration_no.contains(decl_no))
        codes = [c.strip() for c in customs.split(",") if c.strip()]
        if codes:
            stmt = stmt.where(model.customs_code.in_(codes))
        d_from = _parse_iso_date(date_from)
        d_to = _parse_iso_date(date_to)
        if d_from:
            stmt = stmt.where(model.declaration_date >= d_from)
        if d_to:
            stmt = stmt.where(model.declaration_date <= d_to)
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

    # Giá trị có thật trong kỳ, để form gợi ý thay vì bắt cán bộ nhớ mã.
    customs_options: list[str] = []
    if is_bcct:
        customs_options = sorted(
            c for c in db.scalars(
                select(model.customs_code)
                .where(model.company_id == company.id, model.period_year == year)
                .distinct()
            ).all() if c
        )
    book_options: list[str] = []
    if has_book:
        book_options = sorted(
            b for b in db.scalars(
                select(model.book)
                .where(model.company_id == company.id, model.period_year == year)
                .distinct()
            ).all() if b
        )

    # Bộ lọc đang bật, dùng để giữ nguyên khi đổi tab / sang trang.
    active = {
        "q": q, "decl_no": decl_no, "customs": customs,
        "date_from": date_from, "date_to": date_to, "book": book,
    }
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
            "full": full,
            "is_bcct": is_bcct,
            "has_book": has_book,
            "customs_options": customs_options,
            "book_options": book_options,
            "filters": active,
            "filter_qs": urlencode({k: v for k, v in active.items() if v}),
            "any_filter": any(active.values()),
            "parse_layout": prov_file.parse_layout if prov_file else None,
            "parse_detail": prov_file.parse_detail_obj if prov_file else {},
            **active,
        },
    )


_KIND_LABEL_VI = {
    "nvl": "Nguyên vật liệu",
    "tp": "Thành phẩm",
    "both": "Nguyên vật liệu & Thành phẩm",
    "unknown": "Chưa xác định loại",
}


# `:path` chứ không phải `{item_code}`: mã hàng thật có chứa dấu `/` (đo được 63 dòng
# `declaration_lines`, 6 dòng `nvl_balances`, ví dụ `AB1680/4800MS10`), mà một segment
# thì không khớp nổi → 404 trước cả khi chạy auth. `| urlencode` ở nơi sinh link KHÔNG
# chữa được: phần trăm-mã hoá bị giải trước khi router so khớp nên `%2F` lại thành `/`.
# Không có route con nào dưới `/items/{item_code}/` nên `:path` tham lam là an toàn.
@router.get("/companies/{code}/items/{item_code:path}", response_class=HTMLResponse)
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
            "period_windows": load_period_windows(db, company.id, years=years),
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
            "table_label": _EVIDENCE_TABLE_LABEL.get(ref.get("table"), ref.get("table")),
            "filter_text": _describe_evidence_filter(ref.get("filter") or {}),
            "data_url": _evidence_data_url(company, finding.period_year, ref),
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
            "detail_rows": describe_details(finding.details),
            "evidence_blocks": evidence_blocks,
            # Nhãn kỳ ≠ dương lịch phải in kèm khoảng ngày ở MỌI màn (ADR #23 T2).
            "period_window": load_period_windows(
                db, finding.company_id, years=[finding.period_year]
            ).get(finding.period_year),
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
