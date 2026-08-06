"""Job handler implementations.

Mỗi handler nhận `(payload: dict, session: Session)` và trả `dict` result hoặc raise.
Register trong app/main.py lifespan.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import distinct, select, union_all
from sqlalchemy.orm import Session

from app.models import Company, DeclarationLine, Norm, NvlBalance, SpBalance
from app.pipeline.run_checks import run_checks as run_checks_pipeline
from app.settings import settings


def find_years_with_data(session: Session, company_id: int) -> list[int]:
    """Trả về list năm distinct có dữ liệu ở bất kỳ table nào (M15/M15a/M16/BCCT).

    Sorted ascending. Dùng cho batch run "tất cả năm có dữ liệu".
    """
    stmt = union_all(
        select(distinct(NvlBalance.period_year)).where(NvlBalance.company_id == company_id),
        select(distinct(SpBalance.period_year)).where(SpBalance.company_id == company_id),
        select(distinct(Norm.period_year)).where(Norm.company_id == company_id),
        select(distinct(DeclarationLine.period_year)).where(
            DeclarationLine.company_id == company_id
        ),
    )
    years = set(session.scalars(stmt).all())
    return sorted(y for y in years if y is not None)


def run_checks_handler(payload: dict, session: Session) -> dict:
    """Chạy `run_checks` cho (company_code, year).

    `only` (tuỳ chọn, list[str]) → chạy tập con check; không có → full năm.
    """
    company_code = payload.get("company_code")
    year = payload.get("year")
    if not company_code or year is None:
        raise ValueError(f"Payload thiếu company_code/year: {payload!r}")
    only_raw = payload.get("only")
    only = {str(c) for c in only_raw} if only_raw else None
    stats = run_checks_pipeline(company_code, int(year), only=only, session=session)
    return {
        "company_code": stats.company_code,
        "period_year": stats.period_year,
        "company_type": stats.company_type.value,
        "only": sorted(only) if only else None,
        "total_findings": stats.total,
        "findings_per_check": stats.findings_per_check,
        "not_evaluable": stats.not_evaluable,
        "combos_fired": stats.combos_fired,
        "risk_score": stats.risk_score,
    }


def ingest_handler(payload: dict, session: Session) -> dict:
    """Nạp dữ liệu 1 (DN, năm) từ file đã tải lên — chẩn đoán → xem trước → nạp.

    Chạy trong worker chứ không trong request: BCCT 68MB mất 97 giây một lượt đọc
    và một lần tải lên đọc ba lượt, trong khi Cloudflare cắt kết nối ở 100 giây
    (lỗi 524 ngày 06/08 khi cán bộ tải bộ 006). Cả ba lượt nằm trong một phạm vi
    `parse_cache()` nên mỗi file chỉ mở một lần.

    Payload:
      - ``company_code`` / ``year`` — bắt buộc.
      - ``gate`` (mặc định True) — dừng ở `analyzed` khi còn cột `needs_review`
        (đường tải lên). Đặt False cho nạp lại / xác nhận cột: cán bộ vừa quyết
        định xong, dừng lại lần nữa là quay vòng.
      - ``then_run_checks`` — ``{"only": [...] | None}`` để nối một job chạy kiểm
        tra ngay sau khi nạp xong. Handler tự enqueue để thứ tự chắc chắn đúng.
    """
    from app.adapters import parse_cache
    from app.pipeline.data_files import (
        record_parse_result,
        should_stop_for_review,
        sync_data_files,
        year_review_gate,
    )
    from app.pipeline.ingest import IngestPlanError, IngestStats
    from app.pipeline.ingest import ingest as run_ingest
    from app.pipeline.validate import diagnose_upload

    company_code = payload.get("company_code")
    year = payload.get("year")
    if not company_code or year is None:
        raise ValueError(f"Payload thiếu company_code/year: {payload!r}")
    year = int(year)
    gate = payload.get("gate", True)

    company = session.scalar(select(Company).where(Company.code == company_code))
    if company is None:
        raise ValueError(f"Không tìm thấy DN {company_code}.")

    raw_root = Path(settings.raw_data_path)
    base = {"company_code": company_code, "period_year": year}

    with parse_cache():
        sync_data_files(session, company)

        diagnosis = diagnose_upload(company_code, year, raw_root)
        if diagnosis.has_errors:
            record_parse_result(
                session, company, year,
                IngestStats(company_code=company_code, period_year=year), diagnosis,
            )
            return {
                **base,
                "status": "diagnosis_error",
                "note": "Chưa nạp dòng nào — file không đọc được, xem chi tiết bên dưới.",
                "diagnostics": [
                    {"slot": d.slot, "level": d.level, "title": d.title, "detail": d.detail}
                    for d in diagnosis.diagnostics
                ],
            }

        try:
            # Xem trước (chưa ghi dòng) để tính bằng chứng + review từng cột (ADR #18).
            analyze_stats = run_ingest(company_code, year, raw_root=raw_root, dry_run=True)
            record_parse_result(session, company, year, analyze_stats, diagnosis, committed=False)

            if gate:
                review = year_review_gate(session, company, year)
                if should_stop_for_review(review):
                    return {
                        **base,
                        "status": "needs_review",
                        "note": (
                            "Đã tải lên & phân tích, CHƯA nạp dòng nào — cần xác nhận cột "
                            "ở trang tài liệu trước khi nạp."
                        ),
                        "review_columns": [
                            f"{c.slot} · {c.label}" for c in review.columns
                        ],
                    }

            stats = run_ingest(company_code, year, raw_root=raw_root)
        except IngestPlanError as e:
            # Kế hoạch nạp bị từ chối TRƯỚC lệnh xoá → dữ liệu của lượt nạp trước còn
            # nguyên. Việc cán bộ phải xử lý (gán sổ), không phải sự cố hệ thống.
            return {
                **base,
                "status": "plan_error",
                "note": f"Đã tải lên, CHƯA nạp dữ liệu. {e}",
            }

    record_parse_result(session, company, year, stats, diagnosis)

    result = {
        **base,
        "status": "ok",
        "note": "Đã nạp dữ liệu.",
        "m15_rows": stats.m15_rows,
        "m15a_rows": stats.m15a_rows,
        "m16_rows": stats.m16_rows,
        "bcct_rows": stats.bcct_rows,
        "bcct_out_of_window": stats.bcct_out_of_window,
        "bcct_undated": stats.bcct_undated,
        "bcct_skipped": stats.bcct_skipped or [],
        "period_window_rejected": stats.period_window_rejected or [],
    }

    then = payload.get("then_run_checks")
    if then is not None:
        # Handler tự nối job kiểm tra (thay vì route enqueue sẵn hai job): chỉ khi
        # nạp THÀNH CÔNG mới có gì để kiểm tra, và thứ tự không phụ thuộc số worker.
        from app.jobs import enqueue_job
        from app.models.job import JobKind

        created_by = payload.get("created_by")
        if not created_by:
            raise ValueError("Payload có then_run_checks nhưng thiếu created_by.")
        follow_payload: dict = {"company_code": company_code, "year": year}
        only = then.get("only") if isinstance(then, dict) else None
        if only:
            follow_payload["only"] = sorted(only)
        follow = enqueue_job(
            session, kind=JobKind.RUN_CHECKS, payload=follow_payload,
            created_by=int(created_by), company_id=company.id, period_year=year,
        )
        result["checks_job_id"] = follow.id

    return result


def run_batch_handler(payload: dict, session: Session) -> dict:
    """Chạy checks cho mọi năm có dữ liệu của 1 DN. Aggregate stats.

    Payload: {"company_code": "HONG_AN"}
    """
    company_code = payload.get("company_code")
    if not company_code:
        raise ValueError(f"Payload thiếu company_code: {payload!r}")

    company = session.scalar(select(Company).where(Company.code == company_code))
    if company is None:
        raise ValueError(f"Không tìm thấy DN {company_code}. Chạy ingest trước.")

    years = find_years_with_data(session, company.id)
    if not years:
        return {
            "company_code": company_code,
            "years_processed": [],
            "total_findings": 0,
            "risk_score": 0,
            "note": "Không có dữ liệu nào để chạy kiểm tra.",
        }

    per_year: dict[int, dict] = {}
    total_findings = 0
    for year in years:
        stats = run_checks_pipeline(company_code, year, session=session)
        per_year[year] = {
            "total_findings": stats.total,
            "risk_score": stats.risk_score,
            "combos_fired": stats.combos_fired,
        }
        total_findings += stats.total

    # Sau khi loop, company.risk_score đã được update lần cuối = max qua các năm.
    session.refresh(company)
    return {
        "company_code": company_code,
        "years_processed": years,
        "total_findings": total_findings,
        "risk_score": company.risk_score or 0,
        "per_year": per_year,
    }
