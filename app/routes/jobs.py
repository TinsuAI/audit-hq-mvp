"""Routes cho job queue: list, detail, badge unread count.

POST /companies/{code}/run-checks (ở companies.py) tạo job và redirect tới
/jobs/{id} thay vì chạy sync.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import SessionUser, require_user
from app.auth_users import get_user_by_username
from app.database import get_db
from app.jobs.result_labels import JOB_KIND_LABEL_VI, describe_result
from app.models.job import Job, JobStatus
from app.version import VERSION, version_string

router = APIRouter()

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")
templates.env.globals["app_version"] = VERSION
templates.env.globals["app_version_string"] = version_string()

JOB_STATUS_LABEL_VI = {
    JobStatus.QUEUED.value: "Đang chờ",
    JobStatus.RUNNING.value: "Đang chạy",
    JobStatus.DONE.value: "Hoàn tất",
    JobStatus.FAILED.value: "Thất bại",
}
templates.env.globals["JOB_STATUS_LABEL"] = JOB_STATUS_LABEL_VI
templates.env.globals["JOB_KIND_LABEL"] = JOB_KIND_LABEL_VI


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _current_user_id(db: Session, user: SessionUser) -> int:
    u = get_user_by_username(db, user.name)
    if u is None:
        raise HTTPException(status_code=403, detail="Session user không tồn tại trong DB")
    return u.id


@router.get("/jobs", response_class=HTMLResponse)
def list_jobs(
    request: Request,
    status: str | None = Query(default=None),
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    user_id = _current_user_id(db, user)
    stmt = select(Job).where(Job.created_by == user_id)
    if status and status in {s.value for s in JobStatus}:
        stmt = stmt.where(Job.status == status)
    jobs = db.scalars(stmt.order_by(Job.created_at.desc()).limit(200)).all()

    counts_by_status = dict(
        db.execute(
            select(Job.status, func.count(Job.id))
            .where(Job.created_by == user_id)
            .group_by(Job.status)
        ).all()
    )

    return templates.TemplateResponse(
        request,
        "jobs_list.html",
        {
            "user": user,
            "jobs": jobs,
            "selected_status": status,
            "counts": counts_by_status,
            "all_statuses": [s.value for s in JobStatus],
        },
    )


@router.get("/jobs/unread.json")
def unread_count(
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> JSONResponse:
    user_id = _current_user_id(db, user)
    unread = db.scalar(
        select(func.count(Job.id)).where(
            Job.created_by == user_id,
            Job.status.in_([JobStatus.DONE.value, JobStatus.FAILED.value]),
            Job.viewed_at.is_(None),
        )
    ) or 0
    running = db.scalar(
        select(func.count(Job.id)).where(
            Job.created_by == user_id,
            Job.status == JobStatus.RUNNING.value,
        )
    ) or 0
    return JSONResponse({"unread": int(unread), "running": int(running)})


@router.get("/jobs/{job_id}", response_class=HTMLResponse)
def job_detail(
    job_id: int,
    request: Request,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    user_id = _current_user_id(db, user)
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy job {job_id}")
    if job.created_by != user_id and not user.is_admin:
        raise HTTPException(status_code=403, detail="Bạn không có quyền xem job này")

    # Mark viewed nếu job đã xong và lần đầu xem.
    if job.viewed_at is None and job.status in (JobStatus.DONE.value, JobStatus.FAILED.value):
        job.viewed_at = _now()
        db.commit()

    return templates.TemplateResponse(
        request,
        "job_detail.html",
        {
            "user": user,
            "job": job,
            "result_rows": describe_result(job.result),
            "auto_refresh": job.status in (JobStatus.QUEUED.value, JobStatus.RUNNING.value),
        },
    )
