"""AI tổng quan mỗi test (WS3) — sinh + staleness.

On-demand, ĐỒNG BỘ trong request (endpoint `def` thuần → threadpool). Đọc snapshot
nền (aggregate finding + `check_runs.ran_at` + `CompanyPeriod.data_version`) TRƯỚC,
gọi LLM, rồi upsert `check_overviews` SAU khi LLM trả — không để transaction ghi bắc
qua lời gọi LLM.

Kỷ luật prompt (không-hộp-đen): nạp ĐẾM severity + top-N `subject_key`/tiêu đề, KHÔNG
nạp dòng (một DN-năm sinh tới 11.003 finding). Xem ADR #18 Revision — WS3.
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.client import (
    call_with_fallback,
    fallback_model_for,
    make_client,
    make_fallback_client,
)
from app.ai.config import get_setting
from app.ai.cost import estimate_cost
from app.ai.overview_content import (
    SYSTEM_PROMPT as CONTENT_SYSTEM_PROMPT,
)
from app.ai.overview_content import (
    build_prompt_payload,
    finalize_sections,
    parse_sections,
)
from app.ai.overview_stats import build_stats
from app.ai.usage import overview_ref, record_usage
from app.checks.registry import SEVERITY_LABEL_VI, SPECS
from app.models import AiUsage, CheckOverview, CheckRun, Company, Finding
from app.pipeline.period import current_data_version

log = logging.getLogger(__name__)

_TOP_N = 15

_SYSTEM_PROMPT = (
    "Bạn là trợ lý kiểm toán. Viết một đoạn tổng quan tiếng Việt trang trọng, ngắn "
    "gọn (3–6 câu) cho MỘT kiểm tra của một doanh nghiệp trong một năm, dựa DUY NHẤT "
    "trên số liệu tổng hợp được cung cấp. Yêu cầu:\n"
    "- Nêu rõ đây là CHỈ SỐ RỦI RO DỮ LIỆU, không phải kết luận vi phạm.\n"
    "- Dẫn mã đối tượng cụ thể (subject_key) khi mô tả phát hiện nổi bật, để truy nguồn.\n"
    "- KHÔNG khẳng định 'sạch' hay 'không có bất thường' chỉ vì một con số bằng 0.\n"
    "- KHÔNG bịa số liệu ngoài dữ liệu tổng hợp. Không markdown tiêu đề, chỉ văn xuôi."
)


def build_overview_aggregate(
    db: Session, company_id: int, period_year: int, check_code: str, top_n: int = _TOP_N
) -> dict:
    """Tổng hợp finding cho (DN, năm, mã) — ĐẾM + top-N, KHÔNG nạp dòng.

    Bản WS3. Từ TQ-3 prompt dùng `overview_stats.build_stats` (bảng số liệu đầy
    đủ, có lưu); hàm này còn lại cho consumer nào cần đúng hình đếm gọn đó.
    """
    spec = SPECS.get(check_code)
    _filt = (
        Finding.company_id == company_id,
        Finding.period_year == period_year,
        Finding.check_code == check_code,
    )

    sev_counts = {"critical": 0, "warning": 0, "info": 0}
    for sev, n in db.execute(
        select(Finding.severity, func.count()).where(*_filt).group_by(Finding.severity)
    ).all():
        if sev in sev_counts:
            sev_counts[sev] = n

    total = sum(sev_counts.values())

    top_subjects = [
        {"subject_key": sk, "count": n}
        for sk, n in db.execute(
            select(Finding.subject_key, func.count())
            .where(*_filt, Finding.subject_key.is_not(None))
            .group_by(Finding.subject_key)
            .order_by(func.count().desc())
            .limit(top_n)
        ).all()
    ]

    top_titles = [
        {
            "title": title,
            "severity": SEVERITY_LABEL_VI.get(sev, sev),
            "count": n,
        }
        for title, sev, n in db.execute(
            select(Finding.title, Finding.severity, func.count())
            .where(*_filt)
            .group_by(Finding.title, Finding.severity)
            .order_by(func.count().desc())
            .limit(top_n)
        ).all()
    ]

    return {
        "check_code": check_code,
        "title": spec.title if spec else check_code,
        "description": spec.description if spec else "",
        "year": period_year,
        "total_findings": total,
        "severity_totals": sev_counts,
        "top_subjects": top_subjects,
        "top_titles": top_titles,
    }


def overview_is_stale(
    ov: CheckOverview,
    current_ran_at: datetime | None,
    current_data_version: int,
) -> bool:
    """Overview cũ khi check chạy lại (ran_at dời) HOẶC dữ liệu nạp lại (data_version
    dời) so với snapshot lúc sinh. Xử None hai đầu: dòng nền mới xuất hiện = stale."""
    ran_at_stale = current_ran_at is not None and (
        ov.based_on_run_at is None or current_ran_at > ov.based_on_run_at
    )
    dv_stale = current_data_version > (ov.based_on_data_version or 0)
    return ran_at_stale or dv_stale


def generate_check_overview(
    db: Session, *, company: Company, period_year: int, check_code: str,
    created_by: str | None = None,
) -> CheckOverview:
    """Sinh + upsert overview cho (DN, năm, mã). Đọc snapshot nền, gọi LLM, ghi SAU.

    Giả định guard (rate-limit/budget/enabled/api_key) đã kiểm ở route. Không tự
    kiểm — tách để test được logic sinh mà không cần cấu hình AI đầy đủ.
    """
    # ── Đọc snapshot nền (một transaction, TRƯỚC lời gọi LLM) ──
    # Tính LẠI bảng số liệu ngay trước lời gọi: một lần chạy kiểm tra chen vào
    # giữa lúc xếp hàng và lúc sinh sẽ để nhận định mô tả bảng khác bảng đang
    # hiện (ADR #21 mục 7).
    stats = build_stats(
        db, company_id=company.id, period_year=period_year, check_code=check_code
    )

    run_row = db.scalar(
        select(CheckRun).where(
            CheckRun.company_id == company.id,
            CheckRun.period_year == period_year,
            CheckRun.check_code == check_code,
        )
    )
    based_on_run_at = run_row.ran_at if run_row is not None else None

    based_on_data_version = current_data_version(db, company.id, period_year)

    # ── Gọi LLM ──
    # Model chỉ ĐỌC bảng số liệu đã tính và trả bốn trường ngắn với số copy
    # nguyên văn, nên dùng slot model RẺ (`model_fast`) — slot khai sẵn cho
    # summarize/explain, đổi ở /admin/ai không cần redeploy (ADR #21 mục 12).
    prompt_block, allowed_strings = build_prompt_payload(stats, company.name or company.code)
    messages = [
        {"role": "system", "content": CONTENT_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "BẢNG SỐ LIỆU:\n" + prompt_block
                + "\n\nViết nhận định theo đúng cấu trúc JSON đã nêu."
            ),
        },
    ]

    client = make_client()
    fb_client = make_fallback_client()
    model = get_setting("model_fast")
    fb_model = fallback_model_for("fast")
    temperature = float(get_setting("temperature"))
    max_tokens = int(get_setting("max_tokens"))

    t0 = time.time()
    resp, used_model = call_with_fallback(
        primary_client=client,
        primary_model=model,
        fallback_client=fb_client,
        fallback_model=fb_model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        return_model=True,
    )
    latency_ms = int((time.time() - t0) * 1000)

    content = (resp.choices[0].message.content or "").strip()
    usage = getattr(resp, "usage", None)
    tokens_in = getattr(usage, "prompt_tokens", 0) or 0
    tokens_out = getattr(usage, "completion_tokens", 0) or 0
    cost_usd = estimate_cost(used_model, tokens_in, tokens_out).total_usd

    # ── Upsert check_overviews (SAU khi LLM trả) ──
    ov = db.scalar(
        select(CheckOverview).where(
            CheckOverview.company_id == company.id,
            CheckOverview.period_year == period_year,
            CheckOverview.check_code == check_code,
        )
    )
    generated_at = datetime.now(UTC).replace(tzinfo=None)  # naive UTC — như phần còn lại
    if ov is None:
        ov = CheckOverview(
            company_id=company.id, period_year=period_year, check_code=check_code,
        )
        db.add(ov)
    sections, unsupported = finalize_sections(
        parse_sections(content), stats, allowed_strings
    )
    ov.content = content
    ov.sections_json = sections
    ov.needs_review = bool(unsupported)
    ov.unsupported_numbers = ", ".join(unsupported) if unsupported else None
    ov.generated_at = generated_at
    ov.based_on_run_at = based_on_run_at
    ov.based_on_data_version = based_on_data_version
    ov.aggregate_json = stats
    ov.status = CheckOverview.STATUS_DONE
    ov.error = None
    ov.model = used_model
    ov.tokens_in = tokens_in
    ov.tokens_out = tokens_out
    ov.cost_usd = cost_usd
    ov.latency_ms = latency_ms
    # Ghi sổ chi phí (ADR #21 mục 10). Telemetry ở trên là chi phí của CHÍNH
    # overview này và bị ghi đè mỗi lần sinh lại; dòng sổ thì cộng dồn, nên trần
    # ngày thấy đủ cả ba lần sinh lại trong một ngày.
    record_usage(
        db,
        kind=AiUsage.KIND_OVERVIEW,
        ref=overview_ref(company.id, period_year, check_code),
        model=used_model,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_usd=cost_usd,
        user=created_by,
    )
    db.commit()
    db.refresh(ov)
    return ov


def start_overview_job(
    db: Session, *, company: Company, period_year: int, check_code: str, created_by: int,
    username: str | None = None,
) -> tuple[int, bool]:
    """Xếp hàng sinh tổng quan. Trả `(job_id, đã_có_sẵn)` (ADR #21 mục 5-6).

    Bấm lại khi job cũ còn `queued`/`running` → TRẢ JOB CŨ, không tạo job thứ
    hai: hai lần bấm liên tiếp là một thao tác của cán bộ, không phải hai lời
    gọi tính tiền.
    """
    from app.jobs import enqueue_job
    from app.models.job import Job, JobKind, JobStatus

    ov = db.scalar(
        select(CheckOverview).where(
            CheckOverview.company_id == company.id,
            CheckOverview.period_year == period_year,
            CheckOverview.check_code == check_code,
        )
    )
    if ov is not None and ov.job_id is not None and ov.status == CheckOverview.STATUS_RUNNING:
        running = db.get(Job, ov.job_id)
        if running is not None and running.status in (
            JobStatus.QUEUED.value, JobStatus.RUNNING.value
        ):
            return running.id, True

    job = enqueue_job(
        db,
        kind=JobKind.AI_OVERVIEW,
        payload={
            "company_code": company.code,
            "year": period_year,
            "check_code": check_code,
            "username": username,
        },
        created_by=created_by,
        company_id=company.id,
        period_year=period_year,
    )
    # Dòng tổng quan tồn tại NGAY: bảng số liệu hiện được liền, chỗ nhận định
    # hiện "đang viết" thay vì trang trống cho tới khi job xong.
    if ov is None:
        ov = CheckOverview(
            company_id=company.id, period_year=period_year, check_code=check_code,
            content="", based_on_data_version=0,
        )
        db.add(ov)
    ov.status = CheckOverview.STATUS_RUNNING
    ov.job_id = job.id
    ov.error = None
    # Bảng số liệu hiện NGAY, không chờ LLM (ADR #21 mục 6).
    ov.aggregate_json = build_stats(
        db, company_id=company.id, period_year=period_year, check_code=check_code
    )
    db.commit()
    return job.id, False


def run_overview_job(payload: dict, db: Session) -> dict:
    """Handler job `ai_overview`. KHÔNG trả chi phí/token — `/jobs/{id}` in nguyên
    `result` ra màn hình cho mọi cán bộ, tiền chỉ vào sổ + telemetry dòng tổng quan.
    """
    code = payload["company_code"]
    year = int(payload["year"])
    check_code = payload["check_code"]
    company = db.scalar(select(Company).where(Company.code == code))
    if company is None:
        raise ValueError(f"Không tìm thấy doanh nghiệp {code}")

    try:
        ov = generate_check_overview(
            db, company=company, period_year=year, check_code=check_code,
            created_by=payload.get("username"),
        )
    except Exception as e:
        db.rollback()
        row = db.scalar(
            select(CheckOverview).where(
                CheckOverview.company_id == company.id,
                CheckOverview.period_year == year,
                CheckOverview.check_code == check_code,
            )
        )
        if row is not None:
            row.status = CheckOverview.STATUS_FAILED
            row.error = f"{type(e).__name__}: {str(e)[:500]}"
            db.commit()
        raise

    return {
        "company_code": code,
        "year": year,
        "check_code": check_code,
        "chars": len(ov.content or ""),
    }


def checks_needing_overview(db: Session, company_id: int, period_year: int) -> list[str]:
    """Mã kiểm tra có ≥1 phát hiện mà tổng quan chưa có HOẶC đã cũ.

    Bỏ qua meta-finding tổ hợp (`COMBO_*`) — chúng không phải một bài kiểm tra.
    """
    codes = [
        c for (c,) in db.execute(
            select(Finding.check_code).where(
                Finding.company_id == company_id,
                Finding.period_year == period_year,
            ).group_by(Finding.check_code).order_by(Finding.check_code)
        ).all()
        if c and not c.startswith("COMBO_")
    ]
    if not codes:
        return []

    existing = load_overviews_with_staleness(db, company_id, period_year, codes)
    out = []
    for code in codes:
        entry = existing.get(code)
        if entry is None:
            out.append(code)
            continue
        ov = entry["overview"]
        if entry["stale"] or ov.status != CheckOverview.STATUS_DONE:
            out.append(code)
    return out


def run_overview_batch_job(payload: dict, db: Session) -> dict:
    """Handler `ai_overview_batch` — duyệt kiểm tra chưa có / đã cũ (ADR #21 mục 9).

    Commit TỪNG kiểm tra: job dừng giữa chừng vẫn giữ phần đã sinh.

    Hết ngân sách ngày → DỪNG và kết thúc ở trạng thái hoàn tất, KHÔNG `failed`:
    những tổng quan đã sinh vẫn đúng, còn `failed` mời cán bộ bấm lại một nút
    chắc chắn không làm gì.
    """
    from app.ai.config import get_setting
    from app.ai.limits import spent_today

    code = payload["company_code"]
    year = int(payload["year"])
    username = payload.get("username")
    company = db.scalar(select(Company).where(Company.code == code))
    if company is None:
        raise ValueError(f"Không tìm thấy doanh nghiệp {code}")

    targets = checks_needing_overview(db, company.id, year)
    # Kiểm tra đã có tổng quan còn mới — bỏ qua TRƯỚC vòng lặp. Đếm riêng để kết
    # quả nói đủ: "bỏ qua" trong báo cáo gồm cả nhóm này lẫn nhóm chưa tới lượt.
    all_codes = [
        c for (c,) in db.execute(
            select(Finding.check_code).where(
                Finding.company_id == company.id, Finding.period_year == year
            ).group_by(Finding.check_code)
        ).all()
        if c and not c.startswith("COMBO_")
    ]
    already_fresh = len(all_codes) - len(targets)
    budget = float(get_setting("daily_budget_usd", db=db))

    created: list[str] = []
    failed: list[str] = []
    stopped: str | None = None
    for check_code in targets:
        if budget > 0 and spent_today(db) >= budget:
            stopped = "hết ngân sách ngày"
            break
        try:
            generate_check_overview(
                db, company=company, period_year=year, check_code=check_code,
                created_by=username,
            )
            created.append(check_code)
        except Exception as e:  # noqa: BLE001 — một kiểm tra hỏng không giết cả lượt
            db.rollback()
            log.warning("Overview batch: %s lỗi: %s", check_code, e)
            failed.append(check_code)

    not_reached = len(targets) - len(created) - len(failed)
    return {
        "company_code": code,
        "year": year,
        "da_tao": len(created),
        "bo_qua": already_fresh + not_reached,
        "bo_qua_con_moi": already_fresh,
        "bo_qua_chua_toi_luot": not_reached,
        "loi": len(failed),
        "checks_da_tao": created,
        "checks_loi": failed,
        "dung_vi": stopped,
    }


def load_overviews_with_staleness(
    db: Session, company_id: int, period_year: int, check_codes: list[str]
) -> dict[str, dict]:
    """`{check_code: {overview, stale}}` cho các mã cần render ở company_detail.

    Đọc overview + check_runs.ran_at + CompanyPeriod.data_version, tính stale mỗi mã.
    """
    if not check_codes:
        return {}

    overviews = {
        ov.check_code: ov
        for ov in db.scalars(
            select(CheckOverview).where(
                CheckOverview.company_id == company_id,
                CheckOverview.period_year == period_year,
                CheckOverview.check_code.in_(check_codes),
            )
        ).all()
    }
    if not overviews:
        return {}

    ran_ats = {
        r.check_code: r.ran_at
        for r in db.scalars(
            select(CheckRun).where(
                CheckRun.company_id == company_id,
                CheckRun.period_year == period_year,
                CheckRun.check_code.in_(list(overviews)),
            )
        ).all()
    }
    data_version = current_data_version(db, company_id, period_year)

    return {
        code: {
            "overview": ov,
            "stale": overview_is_stale(ov, ran_ats.get(code), data_version),
        }
        for code, ov in overviews.items()
    }
