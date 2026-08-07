"""Trạng thái lượt nạp của một kỳ, dựng sẵn để in ra dòng kỳ (#89).

Trước vé này, bấm nạp là chuyển hướng sang `/jobs/{id}`: cán bộ rời màn dữ liệu,
đọc một bảng kết quả, rồi tự tìm đường quay lại đúng kỳ mình đang làm. Ở đây phản
hồi ở lại dòng kỳ, và trang hàng đợi lùi về vai trò màn quản trị.

**Đang chờ KHÁC đang chạy.** Worker chia theo loại: một luồng loại trừ job AI, một
luồng chỉ nhận job AI (ADR #21 mục 5). Nghĩa là mọi lượt nạp nối đuôi nhau trên
đúng một luồng. Cán bộ có lượt nạp xếp sau một lượt đọc BCCT 97 giây của doanh
nghiệp khác mà chỉ thấy "đang nạp" thì không hiểu vì sao đứng im, nên `queued` và
`running` là hai câu khác nhau, và `queued` nói luôn có bao nhiêu việc xếp trước.
Phép đếm ấy lặp đúng thứ tự `claim_next_job` dùng — `(created_at, id)` — vì
`created_at` chỉ có độ phân giải giây, so sánh một mình nó đếm nhầm.

**Công việc mồ côi.** Tiến trình chết giữa chừng để lại bản ghi `running` vĩnh
viễn; `recover_zombie_jobs` chỉ chạy lúc worker khởi động. Không có đường lùi thì
dòng kỳ quay vòng mãi mãi, nên ở đây job `running` quá `ZOMBIE_THRESHOLD_SECONDS`
được đọc thành hỏng — cùng ngưỡng với việc thu hồi, một định nghĩa duy nhất.

**Câu chữ dựng ở đây, không dựng ở JavaScript.** Bộ đếm poll chỉ đổ `title`,
`detail`, `notes`, `actions` ra DOM. Nhờ đó lần render đầu (server) và lần cập
nhật (poll) đọc cùng một nguồn chữ, không có hai bản tiếng Việt lệch nhau.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import quote_plus

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.jobs.worker import ZOMBIE_THRESHOLD_SECONDS
from app.models import Company, DataFile
from app.models.data_file import SETTLEMENT_SLOTS, SLOT_LABEL_VI, DataFileStatus
from app.models.job import AI_JOB_KINDS, Job, JobKind, JobStatus

#: Bốn dạng kết quả của `ingest_handler` — xem app/jobs/handlers.py.
OUTCOME_OK = "ok"
OUTCOME_DIAGNOSIS_ERROR = "diagnosis_error"
OUTCOME_NEEDS_REVIEW = "needs_review"
OUTCOME_PLAN_ERROR = "plan_error"

#: Nút mở một trang.
ACTION_LINK = "link"
#: Nút gửi form POST (kèm trường ẩn `year`).
ACTION_POST = "post"

TONE_INFO = "info"
TONE_SUCCESS = "success"
TONE_WARNING = "warning"
TONE_ERROR = "error"


@dataclass(frozen=True)
class StatusAction:
    """Một nút cạnh câu trạng thái — việc gỡ nằm ngay đây, không ở trang khác."""

    kind: str
    label: str
    url: str
    year: int | None = None

    def as_dict(self) -> dict:
        return {"kind": self.kind, "label": self.label, "url": self.url, "year": self.year}


@dataclass(frozen=True)
class IngestStatus:
    """Lượt nạp gần nhất của một kỳ, đã dựng thành chữ và nút."""

    job_id: int
    year: int
    #: `queued` · `running` · `done` · `failed`. Job mồ côi đọc thành `failed`.
    status: str
    #: Dạng kết quả khi `done`: ok · diagnosis_error · needs_review · plan_error.
    outcome: str | None
    #: Còn phải hỏi lại — bộ đếm poll dừng khi cờ này tắt.
    active: bool
    tone: str
    title: str
    detail: str
    #: Số việc đang chạy hoặc xếp trước trên cùng luồng worker.
    ahead: int
    notes: tuple[str, ...]
    actions: tuple[StatusAction, ...]
    #: Đích tải lại trang khi lượt nạp trót lọt — số liệu của dòng kỳ đã đổi.
    reload_url: str | None

    @property
    def visible(self) -> bool:
        """Có in tấm bảng ra dòng kỳ hay không.

        Còn chạy thì có. Xong xuôi mà có `reload_url` thì KHÔNG: dòng kỳ dựng lại
        với số dòng mới đã nói đủ, thêm một câu "đã nạp xong" đọng lại nhiều ngày
        sau chỉ là nhiễu. Mọi kết cục còn lại đều có việc phải làm nên phải in.
        """
        return self.active or self.reload_url is None

    def as_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "year": self.year,
            "status": self.status,
            "outcome": self.outcome,
            "active": self.active,
            "tone": self.tone,
            "title": self.title,
            "detail": self.detail,
            "ahead": self.ahead,
            "notes": list(self.notes),
            "actions": [a.as_dict() for a in self.actions],
            "reload_url": self.reload_url,
            "visible": self.visible,
        }


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _latest_ingest_job(session: Session, company_id: int, year: int) -> Job | None:
    return session.scalars(
        select(Job)
        .where(
            Job.company_id == company_id,
            Job.period_year == year,
            Job.kind == JobKind.INGEST.value,
        )
        .order_by(Job.created_at.desc(), Job.id.desc())
        .limit(1)
    ).first()


def _count_ahead(session: Session, job: Job) -> int:
    """Số việc worker phải xong trước khi tới lượt `job`.

    Đếm trên luồng KHÔNG-AI vì đó là luồng job nạp chạy, và lặp đúng thứ tự claim:
    `order_by(created_at, id)`. Job đang chạy tính là một — nó đang giữ luồng.
    """
    not_ai = Job.kind.notin_(sorted(AI_JOB_KINDS))
    queued_before = session.scalar(
        select(func.count(Job.id)).where(
            not_ai,
            Job.status == JobStatus.QUEUED.value,
            or_(
                Job.created_at < job.created_at,
                and_(Job.created_at == job.created_at, Job.id < job.id),
            ),
        )
    ) or 0
    running = session.scalar(
        select(func.count(Job.id)).where(not_ai, Job.status == JobStatus.RUNNING.value)
    ) or 0
    return int(queued_before) + int(running)


def _files(session: Session, company_id: int, year: int) -> list[DataFile]:
    return list(session.scalars(
        select(DataFile)
        .where(DataFile.company_id == company_id, DataFile.period_year == year)
        .order_by(DataFile.slot, DataFile.original_filename)
    ).all())


def _short_label(slot: str) -> str:
    return SLOT_LABEL_VI.get(slot, slot).split(" — ")[0]


def _review_action(slug: str, row: DataFile, label: str) -> StatusAction:
    return StatusAction(
        ACTION_LINK, label, f"/companies/{slug}/documents/file/{row.id}/review",
    )


def _retry_action(slug: str, year: int, label: str = "Nạp lại dữ liệu") -> StatusAction:
    return StatusAction(
        ACTION_POST, label, f"/companies/{slug}/documents/ingest", year=year,
    )


def _first_line(text: str | None) -> str:
    for line in (text or "").splitlines():
        if line.strip():
            return line.strip()
    return "Không rõ nguyên nhân."


def ingest_status(
    session: Session,
    company: Company,
    year: int,
    *,
    ai_enabled: bool = False,
) -> IngestStatus | None:
    """Lượt nạp gần nhất của (DN, kỳ) — `None` khi kỳ chưa từng được xếp lượt nạp.

    `ai_enabled` truyền vào chứ không đọc trong đây: `app.ai.config.get_setting`
    giữ sẵn một `SessionLocal` từ lúc import, gọi nó trong một seam nhận `session`
    là mở phiên thứ hai vào DB khác.
    """
    job = _latest_ingest_job(session, company.id, year)
    if job is None:
        return None

    slug = company.slug or company.code
    common = {"job_id": job.id, "year": year, "outcome": None, "ahead": 0,
              "notes": (), "reload_url": None}

    if job.status == JobStatus.QUEUED.value:
        ahead = _count_ahead(session, job)
        return IngestStatus(
            **{**common, "ahead": ahead},
            status=JobStatus.QUEUED.value,
            active=True,
            tone=TONE_INFO,
            title="Đang chờ trong hàng đợi",
            detail=(
                f"Có {ahead} việc đang chạy hoặc xếp trước. Hàng đợi chạy một việc "
                "một lúc — một bộ tờ khai lớn mất vài phút."
                if ahead
                else "Sắp tới lượt. Hàng đợi chạy một việc nạp một lúc."
            ),
            actions=(),
        )

    if job.status == JobStatus.RUNNING.value:
        cutoff = _now() - timedelta(seconds=ZOMBIE_THRESHOLD_SECONDS)
        if job.started_at is None or job.started_at >= cutoff:
            return IngestStatus(
                **common,
                status=JobStatus.RUNNING.value,
                active=True,
                tone=TONE_INFO,
                title="Đang nạp dữ liệu",
                detail=(
                    f"Hệ thống đang đọc file của kỳ {year}. Một bộ tờ khai lớn mất "
                    "vài phút."
                ),
                actions=(),
            )
        # Bản ghi kẹt ở `running`: tiến trình chết giữa chừng, mà việc thu hồi job
        # treo chỉ chạy lúc worker khởi động. Không đọc thành hỏng ở đây thì dòng
        # kỳ quay vòng cho tới lần khởi động lại tiếp theo.
        return IngestStatus(
            **common,
            status=JobStatus.FAILED.value,
            active=False,
            tone=TONE_ERROR,
            title="Lượt nạp đã dừng giữa chừng",
            detail=(
                "Việc nạp đã dừng mà không báo kết quả — thường là do máy chủ khởi "
                "động lại khi đang đọc file. Dữ liệu của lượt nạp trước còn nguyên."
            ),
            actions=(_retry_action(slug, year),),
        )

    if job.status == JobStatus.FAILED.value:
        return IngestStatus(
            **common,
            status=JobStatus.FAILED.value,
            active=False,
            tone=TONE_ERROR,
            title="Nạp dữ liệu hỏng",
            detail=_first_line(job.error),
            actions=(
                _retry_action(slug, year),
                StatusAction(ACTION_LINK, f"Xem công việc #{job.id}", f"/jobs/{job.id}"),
            ),
        )

    return _done_status(session, company, year, job, slug=slug, ai_enabled=ai_enabled)


def _done_status(
    session: Session,
    company: Company,
    year: int,
    job: Job,
    *,
    slug: str,
    ai_enabled: bool,
) -> IngestStatus:
    result = job.result or {}
    outcome = result.get("status")
    note = str(result.get("note") or "")
    common = {"job_id": job.id, "year": year, "outcome": outcome, "ahead": 0,
              "status": JobStatus.DONE.value}

    if outcome == OUTCOME_DIAGNOSIS_ERROR:
        notes = tuple(
            f"{'🔴' if d.get('level') == 'error' else '🟡'} {d.get('title', '')}"
            f" — {d.get('detail', '')}"
            for d in result.get("diagnostics") or ()
        )
        return IngestStatus(
            **common,
            active=False,
            tone=TONE_ERROR,
            title="Chưa nạp được — hệ thống đọc không ra file",
            detail=note or (
                "Chưa nạp dòng nào. Hệ thống dừng để khỏi phân tích trên dữ liệu "
                "đọc sai."
            ),
            notes=notes,
            actions=_diagnosis_actions(session, company, year, result, slug, ai_enabled),
            reload_url=None,
        )

    if outcome == OUTCOME_NEEDS_REVIEW:
        return IngestStatus(
            **common,
            active=False,
            tone=TONE_WARNING,
            title="Đã phân tích, chưa nạp dòng nào — cần xác nhận cột",
            detail=note or (
                "Các cột dưới đây chỉ suy được theo vị trí. Xác nhận vị trí cột rồi "
                "hệ thống nạp tiếp."
            ),
            notes=_review_notes(session, company, year, result),
            actions=_review_actions(session, company, year, slug),
            reload_url=None,
        )

    if outcome == OUTCOME_PLAN_ERROR:
        return IngestStatus(
            **common,
            active=False,
            tone=TONE_ERROR,
            title="Chưa nạp được — kế hoạch sổ quyết toán chưa hợp lệ",
            detail=note or (
                "Kế hoạch nạp bị từ chối trước khi xoá dữ liệu cũ. Dữ liệu của lượt "
                "nạp trước còn nguyên."
            ),
            notes=(),
            actions=_book_actions(session, company, year, slug),
            reload_url=None,
        )

    # Nạp trót lọt. Lượt chạy kiểm tra nối tiếp (xác nhận cột trên file đã nạp) còn
    # trong hàng đợi thì CHƯA tải lại: tải lại lúc đó dựng dòng kỳ với gắn cờ "kết
    # quả cũ", mời cán bộ bấm chạy kiểm tra thêm một lần nữa cho cùng một việc.
    follow = _follow_up(session, result)
    if follow is not None and follow.status in (
        JobStatus.QUEUED.value, JobStatus.RUNNING.value,
    ):
        return IngestStatus(
            **common,
            active=True,
            tone=TONE_INFO,
            title="Đã nạp xong — đang chạy kiểm tra",
            detail="Lượt nạp đã ghi dữ liệu. Hệ thống đang chạy các kiểm tra của kỳ.",
            notes=(),
            actions=(),
            reload_url=None,
        )
    if follow is not None and follow.status == JobStatus.FAILED.value:
        return IngestStatus(
            **common,
            active=False,
            tone=TONE_WARNING,
            title="Đã nạp dữ liệu — lượt chạy kiểm tra hỏng",
            detail=_first_line(follow.error),
            notes=(),
            actions=(
                StatusAction(
                    ACTION_LINK, f"Xem công việc #{follow.id}", f"/jobs/{follow.id}",
                ),
            ),
            reload_url=None,
        )

    msg = note or "Đã nạp dữ liệu."
    return IngestStatus(
        **common,
        active=False,
        tone=TONE_SUCCESS,
        title="Đã nạp xong",
        detail=msg,
        notes=(),
        actions=(),
        reload_url=(
            f"/companies/{slug}/documents?msg={quote_plus(f'Kỳ {year}: {msg}')}"
            f"#ky-{year}"
        ),
    )


def _follow_up(session: Session, result: dict) -> Job | None:
    follow_id = result.get("checks_job_id")
    return session.get(Job, int(follow_id)) if follow_id else None


def _diagnosis_actions(
    session: Session,
    company: Company,
    year: int,
    result: dict,
    slug: str,
    ai_enabled: bool,
) -> tuple[StatusAction, ...]:
    """Nút chọn trang tính cho từng file đọc hỏng, cộng nút nhờ AI chẩn đoán.

    Trang riêng của file là chỗ DUY NHẤT ghim được trang tính khi không trang nào
    khớp biểu chuẩn — nguyên nhân thường gặp nhất của một file "đọc không ra".
    """
    slots = {d.get("slot") for d in result.get("diagnostics") or () if d.get("slot")}
    actions: list[StatusAction] = []
    seen: set[int] = set()
    for row in _files(session, company.id, year):
        broken = row.parse_status == DataFileStatus.ERROR
        if not (broken or row.slot in slots) or row.id in seen:
            continue
        seen.add(row.id)
        actions.append(_review_action(
            slug, row, f"Chọn trang tính · {_short_label(row.slot)}",
        ))
    if ai_enabled:
        actions.append(StatusAction(
            ACTION_POST, "🤖 Nhờ AI chẩn đoán cấu trúc file",
            f"/companies/{slug}/diagnose-ai", year=year,
        ))
    return tuple(actions)


def _review_notes(
    session: Session, company: Company, year: int, result: dict
) -> tuple[str, ...]:
    """Danh sách cột cần xác nhận, đọc lại từ registry chứ không từ kết quả job.

    Cán bộ có thể đã xác nhận một phần trong lúc job nằm đó; ảnh chụp của job thì
    đứng yên còn registry thì không.
    """
    from app.pipeline.data_files import year_review_gate

    gate = year_review_gate(session, company, year)
    if gate is not None:
        return tuple(f"{_short_label(c.slot)} · {c.label}" for c in gate.columns)
    return tuple(str(c) for c in result.get("review_columns") or ())


def _review_actions(
    session: Session, company: Company, year: int, slug: str
) -> tuple[StatusAction, ...]:
    from app.pipeline.data_files import year_review_gate

    gate = year_review_gate(session, company, year)
    if gate is None:
        return ()
    by_file: dict[int, str] = {}
    for column in gate.columns:
        by_file.setdefault(column.file_id, _short_label(column.slot))
    return tuple(
        StatusAction(
            ACTION_LINK, f"Xác nhận cột · {label}",
            f"/companies/{slug}/documents/file/{file_id}/review",
        )
        for file_id, label in sorted(by_file.items())
    )


def _book_actions(
    session: Session, company: Company, year: int, slug: str
) -> tuple[StatusAction, ...]:
    """Sổ quyết toán chỉ có ở biểu quyết toán — tờ khai luôn toàn pháp nhân."""
    return tuple(
        _review_action(slug, row, f"Gán sổ · {row.original_filename}")
        for row in _files(session, company.id, year)
        if row.slot in SETTLEMENT_SLOTS
    )


__all__ = [
    "ACTION_LINK",
    "ACTION_POST",
    "OUTCOME_DIAGNOSIS_ERROR",
    "OUTCOME_NEEDS_REVIEW",
    "OUTCOME_OK",
    "OUTCOME_PLAN_ERROR",
    "IngestStatus",
    "StatusAction",
    "ingest_status",
]
