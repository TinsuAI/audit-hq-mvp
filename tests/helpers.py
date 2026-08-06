"""Tiện ích dùng chung cho test HTTP.

`TestClient(app)` không vào context manager nên lifespan không chạy → không có
worker thread. Từ khi nạp dữ liệu chuyển sang hàng đợi (job `ingest`), test phải
tự chạy job đã xếp thì mới thấy trạng thái sau khi nạp.
"""

from __future__ import annotations

import app.database as dbmod


def drain_jobs(max_rounds: int = 5) -> int:
    """Chạy hết job đang `queued`, kể cả job do job khác xếp thêm. Trả số job đã chạy.

    `ingest` xếp tiếp `run_checks` khi payload yêu cầu, nên phải lặp chứ không
    quét một lượt.
    """
    from app.jobs import HANDLERS, register_handler, run_job
    from app.jobs.handlers import ingest_handler, run_batch_handler, run_checks_handler
    from app.models.job import Job, JobKind, JobStatus

    for kind, fn in (
        (JobKind.RUN_CHECKS, run_checks_handler),
        (JobKind.BATCH_RUN, run_batch_handler),
        (JobKind.INGEST, ingest_handler),
    ):
        if kind.value not in HANDLERS:
            register_handler(kind, fn)

    ran = 0
    for _ in range(max_rounds):
        with dbmod.SessionLocal() as db:
            jobs = (
                db.query(Job)
                .filter_by(status=JobStatus.QUEUED.value)
                .order_by(Job.id)
                .all()
            )
            if not jobs:
                return ran
            for job in jobs:
                run_job(db, job)
                ran += 1
    return ran


def last_job_result(kind: str | None = None) -> dict | None:
    """`result` của job mới nhất (lọc theo `kind` nếu cần) — để test đọc kết luận."""
    from app.models.job import Job

    with dbmod.SessionLocal() as db:
        q = db.query(Job)
        if kind:
            q = q.filter_by(kind=kind)
        job = q.order_by(Job.id.desc()).first()
        return dict(job.result) if job and job.result else None
