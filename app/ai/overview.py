"""AI tổng quan mỗi test (WS3) — sinh + staleness.

On-demand, ĐỒNG BỘ trong request (endpoint `def` thuần → threadpool). Đọc snapshot
nền (aggregate finding + `check_runs.ran_at` + `CompanyPeriod.data_version`) TRƯỚC,
gọi LLM, rồi upsert `check_overviews` SAU khi LLM trả — không để transaction ghi bắc
qua lời gọi LLM.

Kỷ luật prompt (không-hộp-đen): nạp ĐẾM severity + top-N `subject_key`/tiêu đề, KHÔNG
nạp dòng (một DN-năm sinh tới 11.003 finding). Xem ADR #18 Revision — WS3.
"""

from __future__ import annotations

import json
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
from app.checks.registry import SEVERITY_LABEL_VI, SPECS
from app.models import CheckOverview, CheckRun, Company, Finding
from app.pipeline.period import current_data_version

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
    """Tổng hợp finding cho (DN, năm, mã) — ĐẾM + top-N, KHÔNG nạp dòng."""
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
    db: Session, *, company: Company, period_year: int, check_code: str
) -> CheckOverview:
    """Sinh + upsert overview cho (DN, năm, mã). Đọc snapshot nền, gọi LLM, ghi SAU.

    Giả định guard (rate-limit/budget/enabled/api_key) đã kiểm ở route. Không tự
    kiểm — tách để test được logic sinh mà không cần cấu hình AI đầy đủ.
    """
    # ── Đọc snapshot nền (một transaction, TRƯỚC lời gọi LLM) ──
    aggregate = build_overview_aggregate(db, company.id, period_year, check_code)

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
    user_payload = {
        "company": {"code": company.code, "name": company.name},
        **aggregate,
    }
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "Số liệu tổng hợp (JSON):\n"
                + json.dumps(user_payload, ensure_ascii=False)
                + "\n\nViết đoạn tổng quan cho kiểm tra này."
            ),
        },
    ]

    client = make_client()
    fb_client = make_fallback_client()
    model = get_setting("model_default")
    fb_model = fallback_model_for("default")
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
    ov.content = content
    ov.generated_at = generated_at
    ov.based_on_run_at = based_on_run_at
    ov.based_on_data_version = based_on_data_version
    ov.model = used_model
    ov.tokens_in = tokens_in
    ov.tokens_out = tokens_out
    ov.cost_usd = cost_usd
    ov.latency_ms = latency_ms
    db.commit()
    db.refresh(ov)
    return ov


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
