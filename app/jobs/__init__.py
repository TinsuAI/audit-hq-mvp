"""Async job runner — public API.

- `register_handler(kind, fn)` — đăng ký handler cho 1 `JobKind`.
- `enqueue_job(session, ...)` — tạo Job row trạng thái `queued`.
- `run_job(session, job)` — chạy 1 job (claim → handler → mark done/failed).
- Worker thread (xem app/jobs/worker.py) poll bảng `jobs` và gọi `run_job`.

Handler signature: `(payload: dict, session: Session) -> dict | None`. Trả về dict
được lưu vào `Job.result`. Exception bất kỳ → job FAILED, `Job.error` chứa traceback.
"""

from __future__ import annotations

import logging
import traceback
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.job import Job, JobKind, JobStatus

log = logging.getLogger(__name__)


def _now() -> datetime:
    """UTC naive datetime — match shape của các model khác (started_at, finished_at)."""
    return datetime.now(UTC).replace(tzinfo=None)


Handler = Callable[[dict, Session], dict | None]
HANDLERS: dict[str, Handler] = {}


def register_handler(kind: JobKind | str, fn: Handler) -> None:
    key = kind.value if isinstance(kind, JobKind) else str(kind)
    if key in HANDLERS:
        raise ValueError(f"Handler cho kind={key!r} đã đăng ký")
    HANDLERS[key] = fn


def enqueue_job(
    session: Session,
    *,
    kind: JobKind,
    payload: dict,
    created_by: int,
    company_id: int | None = None,
    period_year: int | None = None,
) -> Job:
    """Tạo Job mới (status=queued) và commit. Worker sẽ pick lên trong vòng 1-2s."""
    job = Job(
        kind=kind.value,
        payload=payload,
        status=JobStatus.QUEUED.value,
        created_by=created_by,
        company_id=company_id,
        period_year=period_year,
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def run_job(session: Session, job: Job) -> None:
    """Chạy 1 job đồng bộ. Cập nhật started_at/finished_at/status/result/error.

    Gọi trực tiếp trong test; production qua worker thread.
    """
    handler = HANDLERS.get(job.kind)
    job.started_at = _now()
    job.status = JobStatus.RUNNING.value
    session.commit()

    if handler is None:
        job.status = JobStatus.FAILED.value
        job.error = f"Không có handler đăng ký cho kind={job.kind!r}"
        job.finished_at = _now()
        session.commit()
        return

    try:
        result = handler(job.payload or {}, session)
        job.status = JobStatus.DONE.value
        job.result = result if isinstance(result, dict) else (
            {"value": result} if result is not None else None
        )
    except Exception as e:  # noqa: BLE001 — capture mọi exception vào job.error
        log.exception("Job %s (kind=%s) failed", job.id, job.kind)
        job.status = JobStatus.FAILED.value
        job.error = f"{type(e).__name__}: {e}\n\n{traceback.format_exc()}"
    finally:
        job.finished_at = _now()
        session.commit()


__all__ = ["HANDLERS", "Handler", "enqueue_job", "register_handler", "run_job"]
