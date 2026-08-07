"""Màn dữ liệu (#86): một doanh nghiệp, mọi kỳ là dòng, mới nhất trước.

Lớp SẮP XẾP, không phải lớp tính toán. Con số "đủ dữ liệu cho N/M kiểm tra", bảy
trạng thái mỗi (loại tài liệu, kỳ) và mọi câu vướng mắc đều đến từ
`period_readiness` (#85). Ở đây chỉ chọn nhóm, chọn hành động và dựng đường dẫn.
Tính lại bất kỳ phần nào của phép đếm tại đây là dựng đường thứ hai lệch được với
đường kiểm tra thật sự chạy (ADR #24 mục 2).

**Đúng BA nhóm cách gỡ.** Vướng mắc mức file (trạng thái 2–5) và cảnh báo độ phủ
tờ khai không mang lớp riêng — chúng nằm trong nhóm 1 vì việc gỡ chúng nằm ở chính
kỳ này, chứ không sinh lớp thứ tư (spec mục 3). Nhóm 3 "không nạp gì thêm được"
KHÔNG vào phép đếm: đó là kết luận về doanh nghiệp, chỗ đọc nó là màn phát hiện.

**Động từ theo trạng thái file, không theo phép đếm.** Phép đếm đo theo dòng đã
nạp; nút thì theo bản ghi file. File đã có mà chưa đọc lần nào thì nút là "nạp dữ
liệu", không phải "tải lên" — bảo cán bộ tải lên thứ họ vừa tải là lỗi mà cả spec
lẫn ADR #24 gọi tên.

Phạm vi vé: khung màn + dòng kỳ + phép đếm + danh sách vướng mắc. Phần mở rộng dòng
kỳ (số dòng theo loại + danh sách file thật) là #87, ô thả file là #88, phản hồi nạp
tại chỗ là #89.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.checks.not_evaluable import (
    REMEDY_NEED_FILE_THIS_PERIOD,
    REMEDY_NEED_OTHER_PERIOD_OR_CONFIRMATION,
    REMEDY_NOTHING_TO_LOAD,
    TARGET_COMPANY_FIELD,
    TARGET_DOCUMENT,
    TARGET_PERIOD,
    RemedyTarget,
)
from app.checks.scope import effective_window
from app.models import (
    Company,
    CompanyPeriod,
    CompanyYearScore,
    DataFile,
    DeclarationLine,
    Finding,
    Norm,
    NvlBalance,
    SpBalance,
)
from app.pipeline.period import YEAR_MAX, YEAR_MIN
from app.pipeline.readiness import (
    BLOCKER_CHECK,
    BLOCKER_FILE,
    CHECK_CONCLUSION,
    SLOT_NEEDS_BOOK,
    SLOT_NEEDS_COLUMN_REVIEW,
    SLOT_NOT_PARSED,
    SLOT_PARSE_ERROR,
    SLOT_STALE,
    Blocker,
    PeriodReadiness,
    period_readiness,
)
from app.pipeline.staleness import results_stale

# --- Hành động gỡ một vướng mắc --------------------------------------------------

#: Tải file của CHÍNH kỳ này lên.
ACTION_UPLOAD = "upload"
#: File đã có, chỉ chưa đọc (hoặc dòng đã cũ) — bấm nạp.
ACTION_INGEST = "ingest"
#: Việc nằm ở trang riêng của một file: chọn trang tính · xác nhận cột · gán sổ.
ACTION_OPEN_FILE = "open-file"
#: Cách gỡ nằm ở KỲ KHÁC — mở đúng kỳ đó.
ACTION_OPEN_PERIOD = "open-period"
#: Cách gỡ là một xác nhận ở mức doanh nghiệp, ngay đầu màn này.
ACTION_CONFIRM_COMPANY_FIELD = "confirm-company-field"
#: Sửa cửa sổ kỳ báo cáo tại chỗ trên dòng kỳ.
ACTION_EDIT_WINDOW = "edit-window"
#: Không nạp gì thêm được — đây là phát hiện, đọc ở màn phát hiện.
ACTION_OPEN_FINDINGS = "open-findings"
#: Không có nút: câu đã nói đủ việc phải làm ngoài hệ thống (soát lại file nguồn).
ACTION_NONE = "none"

ACTION_LABEL_VI = {
    ACTION_UPLOAD: "Tải lên tại đây",
    ACTION_INGEST: "Nạp dữ liệu",
    ACTION_OPEN_FILE: "Mở trang file",
    ACTION_OPEN_PERIOD: "Mở kỳ",
    ACTION_CONFIRM_COMPANY_FIELD: "Xác nhận thuộc tính doanh nghiệp",
    ACTION_EDIT_WINDOW: "Sửa cửa sổ kỳ",
    ACTION_OPEN_FINDINGS: "Xem ở màn phát hiện",
    ACTION_NONE: "",
}

COMPANY_FIELD_LABEL_VI = {
    "first_bcqt_year": "năm đầu nộp báo cáo quyết toán",
    "fiscal_start_month": "niên độ kế toán",
    "audit_decision_date": "ngày quyết định kiểm tra sau thông quan",
}

#: Mục lớp 3 — không phải vướng mắc dữ liệu, nên mang loại riêng để đếm không chạm.
BLOCKER_CONCLUSION = "conclusion"

# Ba lớp cách gỡ, đúng ba, theo thứ tự việc cán bộ làm được ngay → làm được ở chỗ
# khác → không làm gì được.
GROUP_ORDER = (
    REMEDY_NEED_FILE_THIS_PERIOD,
    REMEDY_NEED_OTHER_PERIOD_OR_CONFIRMATION,
    REMEDY_NOTHING_TO_LOAD,
)

GROUP_TITLE_VI = {
    REMEDY_NEED_FILE_THIS_PERIOD: "Nạp thêm dữ liệu cho kỳ này",
    REMEDY_NEED_OTHER_PERIOD_OR_CONFIRMATION: "Cần kỳ khác hoặc một xác nhận",
    REMEDY_NOTHING_TO_LOAD: "Không nạp gì thêm được",
}

GROUP_HINT_VI = {
    REMEDY_NEED_FILE_THIS_PERIOD: "Gỡ được bằng file của chính kỳ này.",
    REMEDY_NEED_OTHER_PERIOD_OR_CONFIRMATION: (
        "File của kỳ này không gỡ được — việc nằm ở kỳ khác hoặc ở thuộc tính "
        "doanh nghiệp."
    ),
    REMEDY_NOTHING_TO_LOAD: (
        "Đây là phát hiện về doanh nghiệp, không phải lỗ hổng dữ liệu — không tính "
        "vào số kiểm tra còn thiếu dữ liệu."
    ),
}

# Trạng thái file → việc phải làm. Trạng thái 2 và 7 gỡ bằng lượt nạp; 3, 4, 5 gỡ ở
# trang riêng của file (chọn trang tính · xác nhận cột · gán sổ).
_FILE_ACTION = {
    SLOT_NOT_PARSED: ACTION_INGEST,
    SLOT_STALE: ACTION_INGEST,
    SLOT_PARSE_ERROR: ACTION_OPEN_FILE,
    SLOT_NEEDS_COLUMN_REVIEW: ACTION_OPEN_FILE,
    SLOT_NEEDS_BOOK: ACTION_OPEN_FILE,
}

# Cảnh báo độ phủ → việc phải làm. Khoá đến từ `readiness._coverage_blockers`.
_COVERAGE_ACTION = {
    "coverage:overlap": ACTION_EDIT_WINDOW,
    "coverage:out-of-window": ACTION_NONE,
    "coverage:undated": ACTION_NONE,
    "coverage:cross-label-duplicates": ACTION_NONE,
}

#: Neo của khối thuộc tính mức doanh nghiệp — đích của cách gỡ lớp 2 kiểu trường DN.
COMPANY_FIELDS_ANCHOR = "thuoc-tinh-doanh-nghiep"

_TIER1_MODELS = (NvlBalance, SpBalance, Norm, DeclarationLine)


@dataclass(frozen=True)
class ScreenAction:
    """Một nút trên dòng vướng mắc.

    `url` là đích của liên kết; với `ACTION_UPLOAD` và `ACTION_INGEST` nó là điểm
    cuối POST và `year`/`slot` là hai trường ẩn của form.
    """

    kind: str
    label: str
    url: str | None = None
    year: int | None = None
    slot: str | None = None


@dataclass(frozen=True)
class BlockerItem:
    """Một dòng trong danh sách vướng mắc của một kỳ, kèm cách gỡ đúng chỗ."""

    kind: str
    key: str
    message: str
    action: ScreenAction
    slot: str | None = None
    #: Chỉ dòng loại `check`/`conclusion` mang lớp — dòng mức file và độ phủ thì không.
    remedy: str | None = None
    check_codes: tuple[str, ...] = ()
    #: Các loại tài liệu mà dòng này nói tới cùng lúc (dòng dấu hiệu cũ gộp cả kỳ).
    slots: tuple[str, ...] = ()


@dataclass(frozen=True)
class BlockerGroup:
    """Một trong ba nhóm cách gỡ."""

    remedy: str
    title: str
    hint: str
    #: Nhóm 3 không nằm trong phép đếm "đủ dữ liệu cho N/M kiểm tra".
    counted: bool
    items: tuple[BlockerItem, ...] = ()


@dataclass(frozen=True)
class PeriodRow:
    """Một kỳ = một dòng."""

    year: int
    anchor: str
    window_anchor: str
    sufficient_count: int
    total_count: int
    run_to_know_codes: tuple[str, ...]
    #: Dữ liệu đã nạp không còn khớp bộ file — TRỤC RIÊNG, không vào phép đếm.
    stale: bool
    #: Phát hiện và điểm tính trên phiên bản dữ liệu cũ hơn hiện tại — cần CHẠY LẠI
    #: kiểm tra, khác `stale` (cần NẠP LẠI). Cũng không vào phép đếm.
    results_stale: bool
    groups: tuple[BlockerGroup, ...]
    window_from: date
    window_to: date
    #: Chỉ hiện cửa sổ khi khác năm dương lịch (spec mục 15).
    window_custom: bool
    window_manual: bool
    has_files: bool
    has_data: bool
    checks_run: bool
    score: int | None
    findings_url: str
    window_url: str
    ingest_url: str
    upload_url: str

    @property
    def ready(self) -> bool:
        return self.sufficient_count >= self.total_count

    @property
    def blocker_count(self) -> int:
        """Số vướng mắc phải xử lý — nhóm 3 không tính, nó không phải việc phải làm."""
        return sum(len(g.items) for g in self.groups if g.counted)

    def group(self, remedy: str) -> BlockerGroup:
        return next(g for g in self.groups if g.remedy == remedy)


@dataclass(frozen=True)
class CompanyFields:
    """Thuộc tính mức doanh nghiệp, sửa được ngay đầu màn dữ liệu.

    Ở đây chứ không ở trang sửa doanh nghiệp: `first_bcqt_year` rỗng đang chặn kỳ
    sớm nhất của mọi doanh nghiệp, mà chỗ sửa nó lại nằm ngoài luồng nạp (ADR #24
    mục 3).
    """

    first_bcqt_year: int | None
    fiscal_start_month: int
    audit_decision_date: date | None
    missing_first_bcqt_year: bool
    url: str
    anchor: str = COMPANY_FIELDS_ANCHOR


@dataclass(frozen=True)
class DataScreen:
    """Toàn bộ ngữ cảnh màn dữ liệu của một doanh nghiệp."""

    company: Company
    fields: CompanyFields
    periods: tuple[PeriodRow, ...]
    add_years: tuple[int, ...]
    #: Doanh nghiệp chưa có kỳ nào — hiện lời mời thêm kỳ thay cho bảng rỗng.
    invite: bool


# --- Dựng ngữ cảnh ---------------------------------------------------------------


def _period_anchor(year: int) -> str:
    return f"ky-{year}"


def _window_anchor(year: int) -> str:
    return f"ky-{year}-cua-so"


def _data_years(session: Session, company_id: int) -> set[int]:
    """Năm có dòng Tầng 1 đã nạp (gộp bốn bảng)."""
    years: set[int] = set()
    for model in _TIER1_MODELS:
        years |= set(
            session.scalars(
                select(model.period_year)
                .where(model.company_id == company_id)
                .distinct()
            ).all()
        )
    return years


def _file_years(session: Session, company_id: int) -> set[int]:
    return set(
        session.scalars(
            select(DataFile.period_year)
            .where(DataFile.company_id == company_id)
            .distinct()
        ).all()
    )


def _open_period_action(year: int, slug: str, years_present: set[int]) -> ScreenAction:
    """Nút mở đúng kỳ cần nạp.

    Kỳ chưa có gì thì chưa phải một dòng — đường dẫn phải mang `add` để màn hình
    dựng dòng trống cho nó, nếu không nút trỏ vào chỗ không tồn tại.
    """
    anchor = f"#{_period_anchor(year)}"
    url = anchor if year in years_present else f"/companies/{slug}/documents?add={year}{anchor}"
    return ScreenAction(
        ACTION_OPEN_PERIOD, f"{ACTION_LABEL_VI[ACTION_OPEN_PERIOD]} {year}",
        url=url, year=year,
    )


def _company_field_action(target: RemedyTarget) -> ScreenAction:
    label = COMPANY_FIELD_LABEL_VI.get(str(target.value))
    return ScreenAction(
        ACTION_CONFIRM_COMPANY_FIELD,
        f"Xác nhận {label}" if label else ACTION_LABEL_VI[ACTION_CONFIRM_COMPANY_FIELD],
        url=f"#{COMPANY_FIELDS_ANCHOR}",
    )


def _upload_action(year: int, slug: str, slot: str | None) -> ScreenAction:
    return ScreenAction(
        ACTION_UPLOAD, ACTION_LABEL_VI[ACTION_UPLOAD],
        url=f"/companies/{slug}/documents/upload", year=year, slot=slot,
    )


def _file_action(
    blocker: Blocker, state: str | None, year: int, slug: str
) -> ScreenAction:
    kind = _FILE_ACTION.get(state or "", ACTION_INGEST)
    if kind == ACTION_OPEN_FILE and blocker.file_ids:
        return ScreenAction(
            ACTION_OPEN_FILE, ACTION_LABEL_VI[ACTION_OPEN_FILE],
            url=f"/companies/{slug}/documents/file/{blocker.file_ids[0]}/review",
        )
    return ScreenAction(
        ACTION_INGEST, ACTION_LABEL_VI[ACTION_INGEST],
        url=f"/companies/{slug}/documents/ingest", year=year,
    )


def _check_action(blocker: Blocker, year: int, slug: str, years_present: set[int]) -> ScreenAction:
    target = blocker.target
    if target is None:
        return ScreenAction(ACTION_NONE, ACTION_LABEL_VI[ACTION_NONE])
    if target.kind == TARGET_DOCUMENT:
        return _upload_action(year, slug, str(target.value))
    if target.kind == TARGET_PERIOD:
        return _open_period_action(int(target.value), slug, years_present)
    if target.kind == TARGET_COMPANY_FIELD:
        return _company_field_action(target)
    return ScreenAction(ACTION_NONE, ACTION_LABEL_VI[ACTION_NONE])


def _coverage_action(blocker: Blocker, year: int, slug: str) -> ScreenAction:
    if blocker.key.startswith("coverage:gap:"):
        return _upload_action(year, slug, blocker.slot)
    kind = _COVERAGE_ACTION.get(blocker.key, ACTION_NONE)
    if kind == ACTION_EDIT_WINDOW:
        return ScreenAction(
            ACTION_EDIT_WINDOW, ACTION_LABEL_VI[ACTION_EDIT_WINDOW],
            url=f"#{_window_anchor(year)}", year=year,
        )
    return ScreenAction(ACTION_NONE, ACTION_LABEL_VI[ACTION_NONE])


def _blocker_item(
    blocker: Blocker,
    readiness: PeriodReadiness,
    year: int,
    slug: str,
    years_present: set[int],
) -> BlockerItem:
    if blocker.kind == BLOCKER_FILE:
        # Dòng dấu hiệu cũ nói cả kỳ nên không neo vào một slot nào — việc gỡ là một
        # lượt nạp, đúng mặc định của `_file_action`.
        slot = readiness.slot(blocker.slot) if blocker.slot else None
        action = _file_action(blocker, slot.state if slot else None, year, slug)
    elif blocker.kind == BLOCKER_CHECK:
        action = _check_action(blocker, year, slug, years_present)
    else:
        action = _coverage_action(blocker, year, slug)
    return BlockerItem(
        kind=blocker.kind,
        key=blocker.key,
        message=blocker.message,
        action=action,
        slot=blocker.slot,
        remedy=blocker.remedy,
        check_codes=blocker.check_codes,
        slots=blocker.slots,
    )


def _conclusion_items(readiness: PeriodReadiness, findings_url: str) -> list[BlockerItem]:
    """Lớp 3 KHÔNG nằm trong `blockers` — nó là kết luận, không phải lỗ hổng dữ liệu.

    Gom theo lý do: nhiều mã cùng một câu thì cán bộ đọc một dòng, không đọc n dòng
    giống nhau.
    """
    by_reason: dict[str, list[str]] = {}
    for check in readiness.checks:
        if check.status != CHECK_CONCLUSION:
            continue
        by_reason.setdefault(check.reason or "", []).append(check.code)

    items: list[BlockerItem] = []
    for reason, codes in sorted(by_reason.items(), key=lambda kv: sorted(kv[1])[0]):
        ordered = tuple(sorted(codes))
        items.append(BlockerItem(
            kind=BLOCKER_CONCLUSION,
            key=f"conclusion:{ordered[0]}",
            message=reason or (
                "Kiểm tra không kết luận được và không có dữ liệu nào nạp thêm gỡ được."
            ),
            action=ScreenAction(
                ACTION_OPEN_FINDINGS, ACTION_LABEL_VI[ACTION_OPEN_FINDINGS],
                url=findings_url,
            ),
            remedy=REMEDY_NOTHING_TO_LOAD,
            check_codes=ordered,
        ))
    return items


def _groups(
    readiness: PeriodReadiness,
    year: int,
    slug: str,
    years_present: set[int],
    findings_url: str,
) -> tuple[BlockerGroup, ...]:
    buckets: dict[str, list[BlockerItem]] = {remedy: [] for remedy in GROUP_ORDER}
    for blocker in readiness.blockers:
        item = _blocker_item(blocker, readiness, year, slug, years_present)
        # Dòng mức file và dòng độ phủ không mang lớp: việc gỡ chúng nằm ở chính kỳ
        # này nên chúng đứng cùng nhóm 1, KHÔNG sinh nhóm thứ tư.
        buckets[item.remedy or REMEDY_NEED_FILE_THIS_PERIOD].append(item)
    buckets[REMEDY_NOTHING_TO_LOAD].extend(_conclusion_items(readiness, findings_url))

    return tuple(
        BlockerGroup(
            remedy=remedy,
            title=GROUP_TITLE_VI[remedy],
            hint=GROUP_HINT_VI[remedy],
            counted=remedy != REMEDY_NOTHING_TO_LOAD,
            items=tuple(buckets[remedy]),
        )
        for remedy in GROUP_ORDER
    )


def _period_row(
    session: Session,
    company: Company,
    year: int,
    *,
    slug: str,
    years_present: set[int],
    file_years: set[int],
    data_years: set[int],
    windows: dict[int, CompanyPeriod],
    scores: dict[int, CompanyYearScore],
    finding_years: set[int],
) -> PeriodRow:
    readiness = period_readiness(session, company.id, year)
    findings_url = f"/companies/{slug}?year={year}"
    window_from, window_to = effective_window(session, company.id, year)
    stored = windows.get(year)
    score_row = scores.get(year)
    return PeriodRow(
        year=year,
        anchor=_period_anchor(year),
        window_anchor=_window_anchor(year),
        sufficient_count=readiness.sufficient_count,
        total_count=readiness.total_count,
        run_to_know_codes=readiness.run_to_know_codes,
        stale=readiness.stale,
        results_stale=results_stale(session, company.id, year),
        groups=_groups(readiness, year, slug, years_present, findings_url),
        window_from=window_from,
        window_to=window_to,
        # Năm dương lịch là mặc định ai cũng hiểu — chỉ in cửa sổ khi nó khác.
        window_custom=(window_from, window_to) != (date(year, 1, 1), date(year, 12, 31)),
        window_manual=bool(stored and stored.is_manual),
        has_files=year in file_years,
        has_data=year in data_years,
        checks_run=year in scores or year in finding_years,
        score=score_row.score if score_row is not None else None,
        findings_url=findings_url,
        window_url=f"/companies/{slug}/documents/period",
        ingest_url=f"/companies/{slug}/documents/ingest",
        upload_url=f"/companies/{slug}/documents/upload",
    )


def build_data_screen(
    session: Session, company: Company, *, add: int | None = None
) -> DataScreen:
    """Ngữ cảnh màn dữ liệu của một doanh nghiệp — mọi kỳ, mới nhất trước.

    `session` là tham số; hàm KHÔNG tự mở phiên nào. `add` là kỳ cán bộ vừa yêu cầu
    thêm: dựng thành dòng trống để có chỗ tải file lên, kể cả khi kỳ đó chưa có gì.
    """
    slug = company.slug or company.code

    file_years = _file_years(session, company.id)
    data_years = _data_years(session, company.id)
    finding_years = set(session.scalars(
        select(Finding.period_year)
        .where(Finding.company_id == company.id)
        .distinct()
    ).all())
    scores = {
        row.period_year: row
        for row in session.scalars(
            select(CompanyYearScore).where(CompanyYearScore.company_id == company.id)
        ).all()
    }
    windows = {
        row.period_year: row
        for row in session.scalars(
            select(CompanyPeriod).where(CompanyPeriod.company_id == company.id)
        ).all()
    }

    years = file_years | data_years | finding_years | set(scores) | set(windows)
    if add is not None and YEAR_MIN <= add <= YEAR_MAX:
        years.add(add)
    ordered = sorted(years, reverse=True)

    periods = tuple(
        _period_row(
            session, company, year,
            slug=slug,
            years_present=years,
            file_years=file_years,
            data_years=data_years,
            windows=windows,
            scores=scores,
            finding_years=finding_years,
        )
        for year in ordered
    )

    this_year = date.today().year
    add_years = tuple(
        y for y in range(this_year, this_year - 8, -1)
        if YEAR_MIN <= y <= YEAR_MAX and y not in years
    )

    return DataScreen(
        company=company,
        fields=CompanyFields(
            first_bcqt_year=company.first_bcqt_year,
            fiscal_start_month=company.fiscal_start_month or 1,
            audit_decision_date=company.audit_decision_date,
            missing_first_bcqt_year=company.first_bcqt_year is None,
            url=f"/companies/{slug}/documents/company",
        ),
        periods=periods,
        add_years=add_years,
        invite=not periods,
    )


__all__ = [
    "ACTION_CONFIRM_COMPANY_FIELD",
    "ACTION_EDIT_WINDOW",
    "ACTION_INGEST",
    "ACTION_LABEL_VI",
    "ACTION_NONE",
    "ACTION_OPEN_FILE",
    "ACTION_OPEN_FINDINGS",
    "ACTION_OPEN_PERIOD",
    "ACTION_UPLOAD",
    "BLOCKER_CONCLUSION",
    "COMPANY_FIELDS_ANCHOR",
    "GROUP_ORDER",
    "BlockerGroup",
    "BlockerItem",
    "CompanyFields",
    "DataScreen",
    "PeriodRow",
    "ScreenAction",
    "build_data_screen",
]
