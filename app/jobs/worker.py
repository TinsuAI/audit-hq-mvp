"""Background worker thread chạy job queue.

Sống trong process FastAPI (khởi tạo qua lifespan). Poll bảng `jobs` mỗi
`POLL_INTERVAL_SECONDS`, claim row `queued` cũ nhất, gọi `run_job`.

Concurrency: 1 worker thread đủ cho demo. Claim dùng SQL `UPDATE ... WHERE
status='queued'` atomic, an toàn với multi-thread (test `test_claim_is_race_safe`).
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from app.jobs import _now
from app.models.job import Job, JobStatus

log = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 1.5
ZOMBIE_THRESHOLD_SECONDS = 3600  # 1h: job RUNNING quá lâu → coi như crashed


def claim_next_job(
    session: Session,
    *,
    kinds: Iterable[str] | None = None,
    exclude_kinds: Iterable[str] | None = None,
) -> Job | None:
    """Atomic claim job cũ nhất đang queued. Trả Job với status=running, hoặc None.

    Dùng SQL UPDATE WHERE id=(SELECT ... LIMIT 1) AND status='queued' để 2 worker
    cùng claim → 1 thắng (rowcount=1), 1 thua (rowcount=0).

    `kinds` giới hạn loại được nhận, `exclude_kinds` loại trừ. Hai worker chia
    nhau theo loại: worker kiểm tra loại trừ job AI, worker AI chỉ nhận job AI —
    một lời gọi LLM 5 giây không được nằm chặn hàng đợi kiểm tra.
    """
    stmt = select(Job.id).where(Job.status == JobStatus.QUEUED.value)
    if kinds is not None:
        stmt = stmt.where(Job.kind.in_(list(kinds)))
    if exclude_kinds is not None:
        stmt = stmt.where(Job.kind.notin_(list(exclude_kinds)))
    candidate_id = session.scalar(stmt.order_by(Job.created_at, Job.id).limit(1))
    if candidate_id is None:
        return None

    result = session.execute(
        update(Job)
        .where(Job.id == candidate_id, Job.status == JobStatus.QUEUED.value)
        .values(status=JobStatus.RUNNING.value, started_at=_now())
    )
    session.commit()
    if result.rowcount == 0:
        return None
    return session.get(Job, candidate_id)


def recover_zombie_jobs(session: Session, older_than_seconds: int = ZOMBIE_THRESHOLD_SECONDS) -> int:
    """Mark mọi job RUNNING quá lâu thành FAILED. Trả số job đã recover.

    Gọi 1 lần khi server start để dọn job kẹt từ lần crash trước.
    """
    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=older_than_seconds)
    zombies = session.scalars(
        select(Job).where(
            Job.status == JobStatus.RUNNING.value,
            Job.started_at < cutoff,
        )
    ).all()
    for j in zombies:
        j.status = JobStatus.FAILED.value
        j.error = "Job interrupted: server restart hoặc crash khi đang chạy."
        j.finished_at = _now()
    session.commit()
    return len(zombies)


def run_worker_iteration(
    session_factory: sessionmaker,
    *,
    kinds: Iterable[str] | None = None,
    exclude_kinds: Iterable[str] | None = None,
) -> bool:
    """Chạy 1 vòng poll: claim 1 job và execute. Trả True nếu có job đã xử lý.

    Dùng 2 session: 1 để claim atomic, 1 để execute handler (tách transaction để
    failure ở handler không rollback việc claim).
    """
    with session_factory() as s:
        job = claim_next_job(s, kinds=kinds, exclude_kinds=exclude_kinds)
        if job is None:
            return False
        job_id = job.id

    with session_factory() as s:
        job = s.get(Job, job_id)
        _execute_claimed_job(s, job)
        return True


def _execute_claimed_job(session: Session, job: Job) -> None:
    """Chạy handler cho job đã được claim (status=RUNNING). Mark done/failed."""
    import traceback

    from app.jobs import HANDLERS  # late import tránh circular

    handler = HANDLERS.get(job.kind)
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
    except Exception as e:  # noqa: BLE001
        log.exception("Job %s (kind=%s) failed", job.id, job.kind)
        job.status = JobStatus.FAILED.value
        job.error = f"{type(e).__name__}: {e}\n\n{traceback.format_exc()}"
    finally:
        job.finished_at = _now()
        session.commit()


class JobWorker:
    """Background thread chạy poll loop. Dùng `start()`/`stop()` trong lifespan."""

    def __init__(
        self,
        session_factory: sessionmaker,
        poll_interval: float = POLL_INTERVAL_SECONDS,
        *,
        name: str = "audit-hq-job-worker",
        kinds: Iterable[str] | None = None,
        exclude_kinds: Iterable[str] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._poll_interval = poll_interval
        self._name = name
        self._kinds = list(kinds) if kinds is not None else None
        self._exclude_kinds = list(exclude_kinds) if exclude_kinds is not None else None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name=self._name, daemon=True,
        )
        self._thread.start()
        log.info("%s started (poll=%.1fs)", self._name, self._poll_interval)

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None
        log.info("%s stopped", self._name)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                worked = run_worker_iteration(
                    self._session_factory,
                    kinds=self._kinds,
                    exclude_kinds=self._exclude_kinds,
                )
            except Exception:
                log.exception("Worker poll iteration crashed")
                worked = False
            # Nếu vừa làm 1 job xong → poll ngay (queue có thể còn). Nếu rỗng → sleep.
            if not worked:
                self._stop.wait(self._poll_interval)


__all__ = [
    "JobWorker",
    "claim_next_job",
    "recover_zombie_jobs",
    "run_worker_iteration",
]
