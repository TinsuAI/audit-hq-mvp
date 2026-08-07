"""T9 (#89) — phản hồi nạp tại chỗ trên dòng kỳ.

`tests/helpers.py::drain_jobs()` chạy hàng đợi đến hết trong MỘT lời gọi, nên
không test nào viết theo lối đó quan sát được `queued` hay `running` — mà đúng
hai trạng thái đó là thứ vé này thêm. Vì vậy test ở đây dựng sẵn bản ghi `Job`
rồi GỌI THẲNG hàm seam và hàm route, không đi qua hàng đợi.

Ca công việc mồ côi (tiến trình chết giữa chừng, bản ghi kẹt ở `running` vĩnh
viễn vì việc thu hồi chỉ chạy lúc worker khởi động) có test riêng bên dưới.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.auth import SessionUser
from app.models import Company, User
from app.models.data_file import DataFileStatus
from app.models.job import Job, JobKind, JobStatus
from app.pipeline.ingest_status import (
    ACTION_LINK,
    ACTION_POST,
    OUTCOME_DIAGNOSIS_ERROR,
    OUTCOME_NEEDS_REVIEW,
    OUTCOME_OK,
    OUTCOME_PLAN_ERROR,
    ingest_status,
)
from tests.conftest import AppDb
from tests.test_readiness import add_file

ADMIN = SessionUser(name="admin", role="admin")


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@pytest.fixture
def world(app_db: AppDb) -> dict:
    with app_db.SessionLocal() as db:
        company = Company(code="DN_T9", slug="dn-t9", name="Công ty T9", tax_id="1")
        other = Company(code="DN_KHAC", slug="dn-khac", name="Công ty khác", tax_id="2")
        db.add_all([company, other])
        db.commit()
        user = db.query(User).filter_by(username="admin").first()
        return {
            "company_id": company.id,
            "other_id": other.id,
            "user_id": user.id,
        }


def _job(
    db,
    world: dict,
    *,
    kind: JobKind = JobKind.INGEST,
    status: JobStatus = JobStatus.QUEUED,
    company_id: int | None = None,
    year: int = 2025,
    result: dict | None = None,
    error: str | None = None,
    created_at: datetime | None = None,
    started_at: datetime | None = None,
) -> Job:
    """Một bản ghi `jobs` dựng tay ở đúng trạng thái cần quan sát."""
    job = Job(
        kind=kind.value,
        payload={"company_code": "DN_T9", "year": year},
        status=status.value,
        result=result,
        error=error,
        created_by=world["user_id"],
        company_id=company_id if company_id is not None else world["company_id"],
        period_year=year,
        created_at=created_at or _now(),
        started_at=started_at,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def _status(db, world: dict, *, year: int = 2025, ai_enabled: bool = False):
    company = db.get(Company, world["company_id"])
    return ingest_status(db, company, year, ai_enabled=ai_enabled)


# ───────────────────────── đang chờ ≠ đang chạy ─────────────────────────


def test_no_ingest_job_yet_has_nothing_to_show(app_db: AppDb, world: dict):
    with app_db.SessionLocal() as db:
        assert _status(db, world) is None


def test_queued_says_waiting_in_the_queue(app_db: AppDb, world: dict):
    """Việc nạp xếp sau việc khác phải nói ĐANG CHỜ, không phải một vòng xoay."""
    with app_db.SessionLocal() as db:
        job = _job(db, world, status=JobStatus.QUEUED)
        st = _status(db, world)

    assert st is not None
    assert st.job_id == job.id
    assert st.status == JobStatus.QUEUED.value
    assert st.active is True
    assert "Đang chờ trong hàng đợi" in st.title


def test_running_is_a_different_state_from_queued(app_db: AppDb, world: dict):
    with app_db.SessionLocal() as db:
        _job(db, world, status=JobStatus.QUEUED)
        queued = _status(db, world)
    with app_db.SessionLocal() as db:
        db.query(Job).update(
            {Job.status: JobStatus.RUNNING.value, Job.started_at: _now()}
        )
        db.commit()
        running = _status(db, world)

    assert running.status == JobStatus.RUNNING.value
    assert running.active is True
    assert running.title != queued.title
    assert "Đang chờ" not in running.title


def test_queued_counts_the_work_ahead_in_the_queue(app_db: AppDb, world: dict):
    """Hàng đợi kiểm tra chạy MỘT việc một lúc — số việc xếp trước là câu trả lời
    cho "vì sao đứng im", nên phải đếm theo đúng thứ tự worker claim."""
    base = _now() - timedelta(minutes=5)
    with app_db.SessionLocal() as db:
        # Lượt đọc BCCT của DN khác đang chạy.
        _job(
            db, world, company_id=world["other_id"], status=JobStatus.RUNNING,
            created_at=base, started_at=base,
        )
        # Một việc nữa xếp trước.
        _job(
            db, world, company_id=world["other_id"], status=JobStatus.QUEUED,
            created_at=base + timedelta(seconds=1),
        )
        _job(db, world, status=JobStatus.QUEUED, created_at=base + timedelta(seconds=2))
        st = _status(db, world)

    assert st.ahead == 2
    assert "2" in st.detail


def test_jobs_queued_after_mine_do_not_count_as_ahead(app_db: AppDb, world: dict):
    base = _now() - timedelta(minutes=5)
    with app_db.SessionLocal() as db:
        _job(db, world, status=JobStatus.QUEUED, created_at=base)
        _job(
            db, world, company_id=world["other_id"], status=JobStatus.QUEUED,
            created_at=base + timedelta(seconds=1),
        )
        # Cùng mốc giây với việc của tôi: xếp sau vì id lớn hơn. `created_at` có
        # độ phân giải giây nên so sánh một mình nó đếm nhầm việc xếp sau.
        _job(db, world, company_id=world["other_id"], status=JobStatus.QUEUED, created_at=base)
        st = _status(db, world)

    assert st.ahead == 0


def test_ai_jobs_do_not_count_as_work_ahead(app_db: AppDb, world: dict):
    """Worker AI là luồng riêng — job AI không chặn lượt nạp nào (ADR #21 mục 5)."""
    base = _now() - timedelta(minutes=5)
    with app_db.SessionLocal() as db:
        _job(
            db, world, kind=JobKind.AI_OVERVIEW, status=JobStatus.RUNNING,
            created_at=base, started_at=base,
        )
        _job(db, world, status=JobStatus.QUEUED, created_at=base + timedelta(seconds=1))
        st = _status(db, world)

    assert st.ahead == 0


# ───────────────────────── công việc mồ côi ─────────────────────────


def test_orphaned_running_job_falls_back_to_failed(app_db: AppDb, world: dict):
    """Tiến trình chết giữa chừng để lại bản ghi `running` vĩnh viễn.

    `recover_zombie_jobs` chỉ chạy lúc worker khởi động, nên nếu điểm cuối trạng
    thái không có đường lùi thì dòng kỳ quay vòng mãi mãi.
    """
    stale = _now() - timedelta(hours=2)
    with app_db.SessionLocal() as db:
        _job(db, world, status=JobStatus.RUNNING, created_at=stale, started_at=stale)
        st = _status(db, world)

    assert st.status == JobStatus.FAILED.value
    assert st.active is False
    assert "dừng" in st.detail.lower()
    # Đường lùi phải là một nút bấm được, không phải một câu.
    assert any(a.kind == ACTION_POST for a in st.actions)


def test_a_running_job_within_the_threshold_is_not_called_orphaned(
    app_db: AppDb, world: dict
):
    fresh = _now() - timedelta(minutes=3)
    with app_db.SessionLocal() as db:
        _job(db, world, status=JobStatus.RUNNING, created_at=fresh, started_at=fresh)
        st = _status(db, world)

    assert st.status == JobStatus.RUNNING.value
    assert st.active is True


# ───────────────────────── bốn dạng kết quả ─────────────────────────


def test_ok_asks_the_page_to_reload_and_stops_polling(app_db: AppDb, world: dict):
    with app_db.SessionLocal() as db:
        _job(
            db, world, status=JobStatus.DONE,
            result={"status": "ok", "note": "Đã nạp dữ liệu.", "m15_rows": 12},
        )
        st = _status(db, world)

    assert st.outcome == OUTCOME_OK
    assert st.active is False
    assert st.reload_url is not None
    assert "/companies/dn-t9/documents" in st.reload_url
    # Lượt nạp trót lọt không để lại tấm bảng nào trên dòng kỳ — số liệu mới nói thay.
    assert st.visible is False


def test_diagnosis_error_shows_the_diagnosis_at_the_period_row(app_db: AppDb, world: dict):
    with app_db.SessionLocal() as db:
        add_file(db, world["company_id"], slot="m15", year=2025, status=DataFileStatus.ERROR)
        db.commit()
        _job(
            db, world, status=JobStatus.DONE,
            result={
                "status": "diagnosis_error",
                "note": "Chưa nạp dòng nào — file không đọc được, xem chi tiết bên dưới.",
                "diagnostics": [{
                    "slot": "m15", "level": "error",
                    "title": "Không chọn được sheet đúng biểu Mẫu 15",
                    "detail": "Không trang tính nào khớp tiêu đề chuẩn.",
                }],
            },
        )
        st = _status(db, world)

    assert st.outcome == OUTCOME_DIAGNOSIS_ERROR
    assert st.visible is True
    assert st.active is False
    assert any("Không chọn được sheet đúng biểu" in n for n in st.notes)


def test_unreadable_file_offers_sheet_choice_and_ai_diagnosis_right_there(
    app_db: AppDb, world: dict
):
    """Không còn câu bảo cán bộ sang trang khác — hai nút nằm ngay tại dòng kỳ."""
    with app_db.SessionLocal() as db:
        row = add_file(
            db, world["company_id"], slot="m15", year=2025, status=DataFileStatus.ERROR
        )
        db.commit()
        file_id = row.id
        _job(
            db, world, status=JobStatus.DONE,
            result={
                "status": "diagnosis_error",
                "note": "Chưa nạp dòng nào.",
                "diagnostics": [{
                    "slot": "m15", "level": "error", "title": "Đọc hỏng", "detail": "…",
                }],
            },
        )
        st = _status(db, world, ai_enabled=True)

    links = [a.url for a in st.actions if a.kind == ACTION_LINK]
    assert f"/companies/dn-t9/documents/file/{file_id}/review" in links
    posts = [a.url for a in st.actions if a.kind == ACTION_POST]
    assert "/companies/dn-t9/diagnose-ai" in posts


def test_ai_diagnosis_button_is_absent_when_the_assistant_is_off(
    app_db: AppDb, world: dict
):
    with app_db.SessionLocal() as db:
        add_file(db, world["company_id"], slot="m15", year=2025, status=DataFileStatus.ERROR)
        db.commit()
        _job(
            db, world, status=JobStatus.DONE,
            result={"status": "diagnosis_error", "note": "x", "diagnostics": []},
        )
        st = _status(db, world, ai_enabled=False)

    assert all("diagnose-ai" not in a.url for a in st.actions)


def test_needs_review_lists_the_columns_and_links_the_file(app_db: AppDb, world: dict):
    with app_db.SessionLocal() as db:
        row = add_file(
            db, world["company_id"], slot="m15", year=2025,
            status=DataFileStatus.ANALYZED, needs_review=True,
        )
        db.commit()
        file_id = row.id
        _job(
            db, world, status=JobStatus.DONE,
            result={
                "status": "needs_review",
                "note": "Đã tải lên & phân tích, CHƯA nạp dòng nào.",
                "review_columns": ["m15 · Mã NVL"],
            },
        )
        st = _status(db, world)

    assert st.outcome == OUTCOME_NEEDS_REVIEW
    assert st.visible is True
    assert any("Mã NVL" in n for n in st.notes)
    assert any(
        a.url == f"/companies/dn-t9/documents/file/{file_id}/review" for a in st.actions
    )


def test_plan_error_offers_book_assignment_on_the_settlement_files(
    app_db: AppDb, world: dict
):
    with app_db.SessionLocal() as db:
        settlement = add_file(db, world["company_id"], slot="m15", year=2025)
        declarations = add_file(db, world["company_id"], slot="bcct", year=2025)
        db.commit()
        settlement_id, bcct_id = settlement.id, declarations.id
        _job(
            db, world, status=JobStatus.DONE,
            result={
                "status": "plan_error",
                "note": "Đã tải lên, CHƯA nạp dữ liệu. Hai file Mẫu 15 chưa gán sổ.",
            },
        )
        st = _status(db, world)

    assert st.outcome == OUTCOME_PLAN_ERROR
    assert st.visible is True
    assert "chưa gán sổ" in st.detail
    urls = [a.url for a in st.actions]
    assert f"/companies/dn-t9/documents/file/{settlement_id}/review" in urls
    # Tờ khai luôn toàn pháp nhân, không mang sổ — không mời cán bộ vào đó gán.
    assert f"/companies/dn-t9/documents/file/{bcct_id}/review" not in urls


def test_failed_job_shows_the_error_at_the_period_row(app_db: AppDb, world: dict):
    with app_db.SessionLocal() as db:
        _job(
            db, world, status=JobStatus.FAILED,
            error="ValueError: Không tìm thấy DN DN_T9.\n\nTraceback…",
        )
        st = _status(db, world)

    assert st.status == JobStatus.FAILED.value
    assert st.active is False
    assert st.visible is True
    assert "Không tìm thấy DN" in st.detail
    assert any(a.kind == ACTION_POST for a in st.actions)


def test_chained_check_run_keeps_the_row_active_instead_of_reloading(
    app_db: AppDb, world: dict
):
    """Xác nhận cột nối tiếp một lượt chạy kiểm tra. Tải lại trang ngay lúc lượt
    đó còn xếp hàng là mời cán bộ bấm chạy kiểm tra lần nữa."""
    with app_db.SessionLocal() as db:
        follow = _job(db, world, kind=JobKind.RUN_CHECKS, status=JobStatus.QUEUED)
        _job(
            db, world, status=JobStatus.DONE,
            result={"status": "ok", "note": "Đã nạp dữ liệu.", "checks_job_id": follow.id},
        )
        st = _status(db, world)

    assert st.active is True
    assert st.reload_url is None
    assert "kiểm tra" in st.title.lower()


def test_chained_check_run_finished_lets_the_row_reload(app_db: AppDb, world: dict):
    with app_db.SessionLocal() as db:
        follow = _job(db, world, kind=JobKind.RUN_CHECKS, status=JobStatus.DONE)
        _job(
            db, world, status=JobStatus.DONE,
            result={"status": "ok", "note": "Đã nạp dữ liệu.", "checks_job_id": follow.id},
        )
        st = _status(db, world)

    assert st.active is False
    assert st.reload_url is not None


def test_orphaned_chained_check_run_also_falls_back(app_db: AppDb, world: dict):
    """Ngưỡng job mồ côi phải áp cho job đang được BÁO CÁO, không riêng job nạp.

    Tiến trình chết giữa lượt chạy kiểm tra nối tiếp cũng để lại bản ghi `running`
    vĩnh viễn — nếu nhánh này không có đường lùi thì dòng kỳ quay vòng mãi mãi ở
    câu "đang chạy kiểm tra", lần tải trang nào cũng vậy.
    """
    stale = _now() - timedelta(hours=2)
    with app_db.SessionLocal() as db:
        follow = _job(
            db, world, kind=JobKind.RUN_CHECKS, status=JobStatus.RUNNING,
            created_at=stale, started_at=stale,
        )
        _job(
            db, world, status=JobStatus.DONE,
            result={"status": "ok", "note": "Đã nạp dữ liệu.", "checks_job_id": follow.id},
        )
        st = _status(db, world)

    assert st.active is False
    assert st.reload_url is None
    assert st.visible is True
    assert "dừng giữa chừng" in st.title


def test_chained_check_run_failure_is_reported_not_swallowed(app_db: AppDb, world: dict):
    with app_db.SessionLocal() as db:
        follow = _job(
            db, world, kind=JobKind.RUN_CHECKS, status=JobStatus.FAILED,
            error="RuntimeError: check nổ",
        )
        _job(
            db, world, status=JobStatus.DONE,
            result={"status": "ok", "note": "Đã nạp dữ liệu.", "checks_job_id": follow.id},
        )
        st = _status(db, world)

    assert st.active is False
    assert st.visible is True
    assert st.reload_url is None
    assert "check nổ" in st.detail


# ───────────────────────── điểm cuối trạng thái ─────────────────────────


def _endpoint(db, *, year: int = 2025) -> dict:
    from app.routes.companies import documents_ingest_status

    return documents_ingest_status("DN_T9", year=year, user=ADMIN, db=db)


def test_status_endpoint_without_a_job(app_db: AppDb, world: dict):
    with app_db.SessionLocal() as db:
        assert _endpoint(db) == {"status": None}


@pytest.mark.parametrize(
    "status", [JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.DONE, JobStatus.FAILED]
)
def test_status_endpoint_reports_every_job_state(app_db: AppDb, world: dict, status):
    with app_db.SessionLocal() as db:
        _job(
            db, world, status=status,
            started_at=_now() if status is not JobStatus.QUEUED else None,
            result={"status": "ok", "note": "Đã nạp dữ liệu."}
            if status is JobStatus.DONE else None,
            error="RuntimeError: hỏng" if status is JobStatus.FAILED else None,
        )
        body = _endpoint(db)

    assert body["status"] == status.value
    assert set(body) >= {
        "job_id", "status", "outcome", "active", "tone", "title", "detail",
        "ahead", "notes", "actions", "reload_url", "visible",
    }
    assert body["active"] is (status in (JobStatus.QUEUED, JobStatus.RUNNING))


def test_status_endpoint_reports_the_two_extra_result_shapes(app_db: AppDb, world: dict):
    with app_db.SessionLocal() as db:
        _job(
            db, world, status=JobStatus.DONE,
            result={"status": "plan_error", "note": "Chưa gán sổ."},
        )
        assert _endpoint(db)["outcome"] == OUTCOME_PLAN_ERROR

    with app_db.SessionLocal() as db:
        db.query(Job).update({
            Job.result: {"status": "needs_review", "note": "x", "review_columns": []},
        })
        db.commit()
        assert _endpoint(db)["outcome"] == OUTCOME_NEEDS_REVIEW


def test_status_endpoint_serialises_actions_for_the_poller(app_db: AppDb, world: dict):
    with app_db.SessionLocal() as db:
        _job(
            db, world, status=JobStatus.FAILED, error="RuntimeError: hỏng",
        )
        body = _endpoint(db)

    assert body["actions"]
    assert set(body["actions"][0]) == {"kind", "label", "url", "year"}
