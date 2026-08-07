"""Nguồn DUY NHẤT cho "đủ dữ liệu cho N/M kiểm tra" + danh sách vướng mắc (ADR #24).

Hàm thuần trên một phiên DB — không dựng UI, không mở phiên nào bên trong (mở phiên
bên trong là đọc trúng DB dev của máy).

Hai phép đo KHÁC NHAU, đi cùng nhau:

- **Phép đếm đo theo DÒNG đã nạp.** Kiểm tra đọc dòng, nên khả năng chạy được là sự
  thật về dòng. `available_sources` trả lời "đã nạp dòng chưa", không phải "đã có file
  chưa".
- **Câu chữ cách gỡ tra BẢN GHI FILE trước khi chọn động từ.** Một file có thể nằm
  trên đĩa, đã đăng ký, mà chưa ghi dòng nào — lượt nạp dừng ở cổng xác nhận cột. Đo
  theo dòng một mình thì hệ thống bảo cán bộ tải lên thứ họ vừa tải.

**Dấu hiệu cũ là TRỤC RIÊNG.** Sau khi xoá file, "đủ dữ liệu" vẫn ĐÚNG — kiểm tra vẫn
chạy được, chỉ là dữ liệu không còn khớp bộ file. Việc cần làm là nạp lại, không phải
tải thêm. Không bao giờ gộp trục này vào phép đếm.

**Ba cổng mà `registry.requires` không diễn đạt được** — C3.3 cần "BCCT HOẶC Mẫu 16",
C6.1 đọc Mẫu 15 kỳ TRƯỚC, cổng độ phủ định mức xuyên kỳ — được đánh giá bằng cách GỌI
CHÍNH hàm điều kiện mà kiểm tra gọi (`comparison_units_gate`, `previous_period_gate`,
`norm_gate_outcome`). Đó mới là cách "một hàm phân loại" thành sự thật: bảng điều
khiển và kiểm tra khớp nhau vì chạy cùng một đoạn mã, không phải vì hai bản chép tay
tình cờ giống nhau.

Mã nào thật sự không dự đoán được (kiểm tra mở rộng do admin soạn) vẫn nằm trong MẪU
SỐ, gắn "biết khi chạy" — rút mẫu số là cách làm doanh nghiệp trông sạch hơn.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.checks import ALL_CHECKS
from app.checks.c3_classify import comparison_units_gate
from app.checks.c6_cross_period import previous_period_gate
from app.checks.norm_gate import norm_gate_outcome
from app.checks.not_evaluable import (
    REMEDY_NOTHING_TO_LOAD,
    TARGET_COMPANY_FIELD,
    TARGET_DOCUMENT,
    TARGET_PERIOD,
    RemedyClassification,
    RemedyTarget,
    truncate_reason,
)
from app.checks.registry import missing_sources
from app.checks.scope import effective_window
from app.checks.sources import (
    available_sources,
    classify_missing_sources,
    missing_sources_reason,
)
from app.models import CheckDefinition, DataFile, DeclarationLine
from app.models.check_definition import CheckStatus
from app.models.data_file import (
    SETTLEMENT_SLOTS,
    SLOT_LABEL_VI,
    SLOT_ORDER,
    SLOT_SHORT_VI,
    DataFileStatus,
)
from app.pipeline.coverage import bcct_coverage, coverage_gaps, overlapping_periods
from app.pipeline.data_files import review_gate_for_files
from app.pipeline.ingest import book_assignment_error

# --- Bảy trạng thái của một (loại tài liệu, kỳ) — spec mục 3 --------------------

#: 1. Không có bản ghi file → nạp thêm file kỳ này.
SLOT_NO_FILE = "no-file"
#: 2. Có file, chưa đọc lần nào → bấm nạp (KHÔNG phải "tải thêm file").
SLOT_NOT_PARSED = "not-parsed"
#: 3. File đọc hỏng → sửa file hoặc chọn trang tính.
SLOT_PARSE_ERROR = "parse-error"
#: 4. Đã phân tích, còn cột cần xác nhận → xác nhận cột.
SLOT_NEEDS_COLUMN_REVIEW = "needs-column-review"
#: 5. Đã phân tích, không vướng cột, còn file quyết toán chưa gán sổ → gán sổ.
SLOT_NEEDS_BOOK = "needs-book"
#: 6. Đã có dòng, mọi file đã đọc xong → nguồn sẵn sàng.
SLOT_READY = "ready"
#: 7. Có dòng nhưng bộ file đã đổi từ sau lượt nạp → dấu hiệu cũ, cần nạp lại.
SLOT_STALE = "stale"

SLOT_STATES: tuple[str, ...] = (
    SLOT_NO_FILE,
    SLOT_NOT_PARSED,
    SLOT_PARSE_ERROR,
    SLOT_NEEDS_COLUMN_REVIEW,
    SLOT_NEEDS_BOOK,
    SLOT_READY,
    SLOT_STALE,
)

# Trạng thái mức file (2–5) là vướng mắc ĐỘC LẬP với bộ ba lớp cách gỡ: chúng hiện
# thành dòng trong danh sách nhưng KHÔNG mang lớp, và không sinh lớp thứ tư.
_FILE_LEVEL_STATES = frozenset({
    SLOT_NOT_PARSED,
    SLOT_PARSE_ERROR,
    SLOT_NEEDS_COLUMN_REVIEW,
    SLOT_NEEDS_BOOK,
})

# --- Trạng thái dự đoán của một kiểm tra ----------------------------------------

#: Đủ nguồn, không cổng nào chặn.
CHECK_READY = "ready"
#: Thiếu dữ liệu — lớp cách gỡ 1 hoặc 2, có việc để làm.
CHECK_BLOCKED = "blocked"
#: Lớp 3 — không nạp gì thêm được; là kết luận về DN, thuộc màn phát hiện.
CHECK_CONCLUSION = "conclusion"
#: Không dự đoán được (kiểm tra mở rộng) — vẫn trong mẫu số, "biết khi chạy".
CHECK_RUN_TO_KNOW = "run-to-know"

# --- Loại vướng mắc --------------------------------------------------------------

BLOCKER_CHECK = "check"
BLOCKER_FILE = "file"
BLOCKER_COVERAGE = "coverage"


@dataclass(frozen=True)
class SlotStatus:
    """Trạng thái một (loại tài liệu, kỳ) — một trong bảy giá trị của `SLOT_STATES`."""

    slot: str
    state: str
    #: Có dòng Tầng 1 mà kiểm tra đọc được cho slot này.
    has_rows: bool
    #: Dòng đã nạp không còn khớp bộ file — TRỤC RIÊNG, không vào phép đếm.
    stale: bool
    file_ids: tuple[int, ...] = ()
    message: str | None = None


@dataclass(frozen=True)
class CheckReadiness:
    """Dự đoán cho một mã kiểm tra: chạy được chưa, thiếu gì, gỡ bằng cách nào."""

    code: str
    status: str
    remedy: str | None = None
    target: RemedyTarget | None = None
    reason: str | None = None

    @property
    def data_sufficient(self) -> bool:
        """Có đủ nguồn Tầng 1 để chạy không.

        Lớp 3 tính là ĐỦ: "chưa từng khai định mức" là kết luận về doanh nghiệp, không
        phải lỗ hổng dữ liệu. Đếm nó vào phần thiếu thì con số không bao giờ đầy và cán
        bộ đi tìm file không tồn tại.
        """
        return self.status in (CHECK_READY, CHECK_CONCLUSION)


@dataclass(frozen=True)
class Blocker:
    """Một dòng trong danh sách vướng mắc.

    `remedy` CHỈ có ở dòng loại `check`. Vướng mắc mức file và cảnh báo độ phủ tờ khai
    không mang lớp — không thêm lớp thứ tư vào bộ ba cách gỡ.
    """

    kind: str
    key: str
    message: str
    slot: str | None = None
    remedy: str | None = None
    target: RemedyTarget | None = None
    check_codes: tuple[str, ...] = ()
    file_ids: tuple[int, ...] = ()
    #: Nhiều loại tài liệu cùng một việc — dòng dấu hiệu cũ gộp cả kỳ vào một dòng.
    slots: tuple[str, ...] = ()


@dataclass(frozen=True)
class PeriodReadiness:
    """Kết quả cho một (DN, kỳ): mẫu số, tử số, bảy trạng thái, danh sách vướng mắc."""

    company_id: int
    year: int
    checks: tuple[CheckReadiness, ...] = ()
    slots: tuple[SlotStatus, ...] = ()
    blockers: tuple[Blocker, ...] = ()
    #: Dữ liệu đã nạp không còn khớp bộ file của kỳ — trục riêng, không vào phép đếm.
    stale: bool = False

    @property
    def total_count(self) -> int:
        """Mẫu số: MỌI kiểm tra áp dụng, kể cả mã chỉ biết được khi chạy."""
        return len(self.checks)

    @property
    def sufficient_count(self) -> int:
        return sum(1 for c in self.checks if c.data_sufficient)

    @property
    def run_to_know_codes(self) -> tuple[str, ...]:
        return tuple(c.code for c in self.checks if c.status == CHECK_RUN_TO_KNOW)

    def slot(self, slot: str) -> SlotStatus | None:
        return next((s for s in self.slots if s.slot == slot), None)


# --- Ba cổng `requires` không diễn đạt được -------------------------------------

# {mã kiểm tra → hàm điều kiện CHÍNH kiểm tra đó gọi}. Mỗi hàm trả (lý do, (lớp, đích))
# khi chặn, None khi không. Thêm mã vào đây là thêm một cổng, không phải chép logic.
#
# Bảng giữ TAY, nằm cách chỗ kiểm tra khai `requires` — nên có test canh giữ hai bên
# khớp nhau: `tests/test_readiness.py::test_every_check_with_a_gate_of_its_own_is_in_
# the_prediction_table` đọc chú thích kiểu trả về của từng hàm kiểm tra và bắt buộc mọi
# mã khai `-> CheckResult` (tức có nhánh `NotEvaluable` của riêng nó) phải có mặt ở đây,
# và ngược lại. Kiểm tra thứ tư nhận thêm một cổng mà quên dòng này thì test đó ĐỎ —
# test đối chiếu dự đoán ↔ trạng thái đã lưu KHÔNG bắt được, vì nó chỉ chạy trên các mã
# fixture dựng sẵn. Dấu hiệu nhận biết là chú thích kiểu, nên nó chỉ đúng khi hàm kiểm
# tra khai thật: trả `NotEvaluable` dưới chú thích `-> list[Finding]` thì vẫn lọt.
_EXTRA_GATES = {
    "C3.3": comparison_units_gate,
    "C4.3": norm_gate_outcome,
    "C6.1": previous_period_gate,
}


def _applicable_codes(session: Session) -> list[str]:
    """Tập mã `run_checks` sẽ chạy: built-in ∪ kiểm tra mở rộng đã công bố.

    Dựng đúng như `codes_to_run` của bộ điều phối — lệch tập mã là lệch mẫu số.
    """
    dynamic = session.scalars(
        select(CheckDefinition.code).where(CheckDefinition.status == CheckStatus.PUBLISHED)
    ).all()
    return sorted(set(ALL_CHECKS) | set(dynamic))


def predict_check(
    session: Session, company_id: int, year: int, code: str, present: set[str]
) -> CheckReadiness:
    """Dự đoán trạng thái một mã, theo ĐÚNG thứ tự bộ điều phối quyết định.

    Cổng thiếu nguồn xét TRƯỚC cổng riêng của check: (DN, kỳ) vừa thiếu Mẫu 16 vừa ở
    kỳ biên thì `run_checks` ghi lớp 1, nên dự đoán cũng phải là lớp 1.
    """
    if code not in ALL_CHECKS:
        # Kiểm tra mở rộng: logic là SQL/Python tự do, có thể hỏng lúc chạy. Vẫn trong
        # mẫu số, chỉ không hứa trước.
        return CheckReadiness(code, CHECK_RUN_TO_KNOW)

    missing = missing_sources(code, present)
    if missing:
        remedy, target = classify_missing_sources(missing)
        return CheckReadiness(
            code, CHECK_BLOCKED, remedy, target,
            truncate_reason(missing_sources_reason(missing)),
        )

    gate = _EXTRA_GATES.get(code)
    if gate is not None:
        outcome: tuple[str, RemedyClassification] | None = gate(session, company_id, year)
        if outcome is not None:
            reason, (remedy, target) = outcome
            status = (
                CHECK_CONCLUSION if remedy == REMEDY_NOTHING_TO_LOAD else CHECK_BLOCKED
            )
            return CheckReadiness(code, status, remedy, target, truncate_reason(reason))

    return CheckReadiness(code, CHECK_READY)


# --- Bảy trạng thái mỗi (loại tài liệu, kỳ) --------------------------------------


def _slot_state(
    files: list[DataFile],
    has_rows: bool,
    needs_column_review: bool,
    book_blocked: bool,
) -> str:
    """Một trong bảy giá trị. Thứ tự ưu tiên = thứ tự việc cán bộ phải làm trước.

    File đọc hỏng chặn nặng hơn cột chưa xác nhận (file không đọc được thì xác nhận
    cột cũng vô ích); cột chưa xác nhận đứng trước gán sổ, vì trạng thái 5 theo định
    nghĩa là "không vướng cột, nhưng chưa gán sổ".
    """
    if not files:
        return SLOT_STALE if has_rows else SLOT_NO_FILE
    if any(f.parse_status == DataFileStatus.ERROR for f in files):
        return SLOT_PARSE_ERROR
    if needs_column_review:
        return SLOT_NEEDS_COLUMN_REVIEW
    if book_blocked:
        return SLOT_NEEDS_BOOK
    if all(f.parse_status == DataFileStatus.OK for f in files):
        return SLOT_READY if has_rows else SLOT_NOT_PARSED
    # Còn file chưa đọc: chưa có dòng thì bấm nạp, có dòng rồi thì dòng đã cũ.
    return SLOT_STALE if has_rows else SLOT_NOT_PARSED


def _slot_statuses(
    session: Session, company_id: int, year: int, present: set[str]
) -> tuple[SlotStatus, ...]:
    rows = session.scalars(
        select(DataFile).where(
            DataFile.company_id == company_id,
            DataFile.period_year == year,
        )
    ).all()
    by_slot: dict[str, list[DataFile]] = {slot: [] for slot in SLOT_ORDER}
    for r in rows:
        by_slot.setdefault(r.slot, []).append(r)

    gate = review_gate_for_files(rows)
    review_file_ids = tuple(sorted({c.file_id for c in gate.columns})) if gate else ()
    book_problem = book_assignment_error(session, company_id, year)

    out: list[SlotStatus] = []
    for slot in SLOT_ORDER:
        files = by_slot.get(slot, [])
        has_rows = slot in present
        # Cổng xác nhận cột là cổng của CẢ KỲ: lượt nạp dừng lại thì mọi file của kỳ
        # nằm ở `analyzed`, kể cả file mà cột của chính nó không vướng gì.
        needs_column_review = bool(gate) and any(
            f.parse_status == DataFileStatus.ANALYZED for f in files
        )
        book_blocked = bool(book_problem) and slot in SETTLEMENT_SLOTS and bool(files)
        state = _slot_state(files, has_rows, needs_column_review, book_blocked)

        file_ids = tuple(f.id for f in files if f.id is not None)
        message: str | None = None
        if state == SLOT_NEEDS_BOOK:
            message = book_problem
        elif state == SLOT_PARSE_ERROR:
            message = next(
                (f.parse_message for f in files
                 if f.parse_status == DataFileStatus.ERROR and f.parse_message),
                None,
            )
        elif state == SLOT_NEEDS_COLUMN_REVIEW and review_file_ids:
            # Trỏ tới đúng file có cột cần xác nhận — cột vướng có thể nằm ở file của
            # slot khác, vì cổng dừng cả kỳ.
            file_ids = review_file_ids
        elif state == SLOT_NOT_PARSED and all(
            f.parse_status == DataFileStatus.OK for f in files
        ):
            # File đã đọc xong mà kỳ vẫn không có dòng nào: với tờ khai, đây là ca mọi
            # dòng rơi ngoài cửa sổ kỳ. Bảo cán bộ "bấm nạp" ở đây là sai việc — cảnh
            # báo độ phủ bên dưới mới nói đúng chỗ phải sửa.
            message = (
                f"File {_slot_label(slot)} của kỳ {year} đã đọc xong nhưng kỳ không "
                "nhận được dòng nào — soát lại cửa sổ kỳ báo cáo và nội dung file."
            )

        out.append(SlotStatus(
            slot=slot,
            state=state,
            has_rows=has_rows,
            # Bộ file đã đổi từ sau lượt nạp: hoặc bản ghi file biến mất, hoặc còn file
            # chưa đọc xong. `record_parse_result` chạm MỌI file của kỳ ở mỗi lượt nạp,
            # nên file còn `pending` nghĩa là nó lên sau lượt nạp gần nhất.
            stale=has_rows and (
                not files or any(f.parse_status != DataFileStatus.OK for f in files)
            ),
            file_ids=file_ids,
            message=message,
        ))
    return tuple(out)


def _slot_label(slot: str) -> str:
    return SLOT_LABEL_VI.get(slot, slot)


def _stale_blocker(slots: tuple[SlotStatus, ...], year: int) -> Blocker | None:
    """MỘT dòng cho cả kỳ, kể tên các loại tài liệu — không phải mỗi loại một dòng.

    Ba loại tài liệu cùng cũ vẫn là một việc duy nhất: nạp lại kỳ. Ba dòng ba nút cùng
    trỏ về một lượt nạp đọc ra ba vấn đề khác nhau, trên đúng màn hình sinh ra để bớt
    nhiễu. Điều kiện cũ giữ nguyên (`SlotStatus.stale`), chỉ số dòng đổi.
    """
    stale = [s for s in slots if s.stale]
    if not stale:
        return None
    labels = ", ".join(SLOT_SHORT_VI.get(s.slot, s.slot) for s in stale)
    return Blocker(
        kind=BLOCKER_FILE,
        key="file:stale",
        message=(
            f"Dữ liệu của kỳ {year} ({labels}) đã nạp nhưng bộ file của kỳ đã đổi — "
            "nạp lại để dữ liệu khớp bộ file."
        ),
        file_ids=tuple(sorted({fid for s in stale for fid in s.file_ids})),
        slots=tuple(s.slot for s in stale),
    )


def _file_blocker_message(status: SlotStatus, year: int) -> str:
    label = _slot_label(status.slot)
    if status.state == SLOT_NOT_PARSED:
        return status.message or (
            f"Đã có file {label} của kỳ {year} nhưng chưa nạp lần nào — bấm nạp dữ liệu."
        )
    if status.state == SLOT_PARSE_ERROR:
        detail = f" {status.message}" if status.message else ""
        return (
            f"File {label} của kỳ {year} đọc không được.{detail} "
            "Sửa file hoặc chọn lại trang tính ở trang của file."
        )
    if status.state == SLOT_NEEDS_COLUMN_REVIEW:
        return (
            f"File {label} của kỳ {year} đã phân tích nhưng còn cột cần xác nhận — "
            "xác nhận cột rồi nạp lại; lượt nạp đang dừng ở đó nên chưa ghi dòng nào."
        )
    # Còn lại là trạng thái 5 (chưa gán sổ). Dấu hiệu cũ KHÔNG đi qua đây: nó gộp cả
    # kỳ thành một dòng ở `_stale_blocker`.
    return status.message or (
        f"File {label} của kỳ {year} chưa gán sổ quyết toán — gán sổ rồi nạp lại."
    )


def _check_group_message(remedy: str, target: RemedyTarget | None, year: int) -> str:
    if target is not None and target.kind == TARGET_DOCUMENT:
        return (
            f"Kỳ {year} chưa có {SLOT_LABEL_VI.get(str(target.value), target.value)} — "
            "nạp thêm file kỳ này."
        )
    if target is not None and target.kind == TARGET_PERIOD:
        return (
            f"Cần dữ liệu của kỳ {target.value} — mở kỳ {target.value} và nạp file của "
            "kỳ đó, file của kỳ này không gỡ được."
        )
    if target is not None and target.kind == TARGET_COMPANY_FIELD:
        return (
            "Cần một xác nhận ở mức doanh nghiệp: năm đầu nộp báo cáo quyết toán. "
            "Nhập ở phần thuộc tính doanh nghiệp, không nạp file nào gỡ được."
        )
    return "Thiếu dữ liệu để chạy — xem lý do của từng kiểm tra."


def _target_key(target: RemedyTarget | None) -> str:
    return "—" if target is None else f"{target.kind}:{target.value}"


def _coverage_blockers(session: Session, company_id: int, year: int) -> list[Blocker]:
    """Ba khối cảnh báo cũ trở thành mục trong danh sách vướng mắc.

    Không mang lớp cách gỡ: chúng nói dữ liệu đã nạp lệch cửa sổ kỳ, không nói kiểm tra
    nào thiếu nguồn.
    """
    out: list[Blocker] = []
    overlaps = overlapping_periods(session, company_id, year)
    if overlaps:
        out.append(Blocker(
            kind=BLOCKER_COVERAGE,
            key="coverage:overlap",
            message=(
                f"Cửa sổ kỳ {year} chồng lấn kỳ "
                f"{', '.join(str(y) for y in overlaps)} của cùng doanh nghiệp — một tờ "
                "khai có thể được đếm ở cả hai kỳ. Hợp lệ khi đây là kỳ chuyển tiếp đổi "
                "niên độ; nếu không, sửa lại cửa sổ."
            ),
        ))

    has_declarations = session.scalar(
        select(DeclarationLine.id)
        .where(
            DeclarationLine.company_id == company_id,
            DeclarationLine.period_year == year,
        )
        .limit(1)
    )
    if not has_declarations:
        return out

    period_from, period_to = effective_window(session, company_id, year)
    for i, (start, end) in enumerate(coverage_gaps(session, company_id, year)):
        out.append(Blocker(
            kind=BLOCKER_COVERAGE,
            key=f"coverage:gap:{i}",
            slot="bcct",
            message=(
                f"Kỳ thiếu dữ liệu tờ khai từ {start.strftime('%d/%m/%Y')} – "
                f"{end.strftime('%d/%m/%Y')} — nạp thêm file tờ khai của khoảng này "
                "(thường nằm ở file kết xuất theo năm dương lịch kề bên)."
            ),
        ))

    coverage = bcct_coverage(session, company_id, year)
    if coverage.out_of_window:
        out.append(Blocker(
            kind=BLOCKER_COVERAGE,
            key="coverage:out-of-window",
            slot="bcct",
            message=(
                f"{coverage.out_of_window} dòng nạp ở nhãn năm {year} nhưng ngày tờ khai "
                f"nằm ngoài kỳ {period_from.strftime('%d/%m/%Y')} – "
                f"{period_to.strftime('%d/%m/%Y')} — các dòng này thuộc kỳ khác khi chạy "
                "kiểm tra."
            ),
        ))
    if coverage.undated:
        out.append(Blocker(
            kind=BLOCKER_COVERAGE,
            key="coverage:undated",
            slot="bcct",
            message=(
                f"{coverage.undated} dòng không có ngày tờ khai — quy theo nhãn kỳ nạp."
            ),
        ))
    if coverage.cross_label_duplicates:
        out.append(Blocker(
            kind=BLOCKER_COVERAGE,
            key="coverage:cross-label-duplicates",
            slot="bcct",
            message=(
                f"{coverage.cross_label_duplicates} dòng trùng khoá (số tờ khai · dòng "
                "hàng) với nhãn kỳ khác của cùng doanh nghiệp — hai bản kết xuất chồng "
                "nhau. Hệ thống KHÔNG tự loại: số lượng có thể lệch giữa hai bản, cán bộ "
                "sửa file nguồn rồi nạp lại."
            ),
        ))
    return out


@dataclass
class _Group:
    """Bản nháp một dòng vướng mắc trong lúc gom mã kiểm tra."""

    blocker: Blocker
    codes: list[str] = field(default_factory=list)

    def done(self) -> Blocker:
        b = self.blocker
        return Blocker(
            kind=b.kind, key=b.key, message=b.message, slot=b.slot, remedy=b.remedy,
            target=b.target, check_codes=tuple(sorted(self.codes)), file_ids=b.file_ids,
            slots=b.slots,
        )


def _blockers(
    slots: tuple[SlotStatus, ...],
    checks: tuple[CheckReadiness, ...],
    session: Session,
    company_id: int,
    year: int,
) -> tuple[Blocker, ...]:
    file_groups: dict[str, _Group] = {}
    for s in slots:
        if s.state not in _FILE_LEVEL_STATES:
            continue
        file_groups[s.slot] = _Group(Blocker(
            kind=BLOCKER_FILE,
            key=f"file:{s.slot}",
            message=_file_blocker_message(s, year),
            slot=s.slot,
            file_ids=s.file_ids,
        ))

    # Slot đang vướng ở mức file thì kiểm tra thiếu nguồn của slot đó TRỎ TỚI dòng ấy,
    # không nhắc lại "nạp thêm file kỳ này" cho thứ cán bộ vừa tải lên.
    file_level_slots = {s.slot for s in slots if s.state in _FILE_LEVEL_STATES}

    check_groups: dict[str, _Group] = {}
    for c in checks:
        if c.status != CHECK_BLOCKED:
            continue  # lớp 3 là kết luận về DN, không phải lỗ hổng dữ liệu
        target = c.target
        if (
            target is not None
            and target.kind == TARGET_DOCUMENT
            and target.value in file_level_slots
        ):
            file_groups[str(target.value)].codes.append(c.code)
            continue
        key = f"check:{c.remedy}:{_target_key(target)}"
        group = check_groups.get(key)
        if group is None:
            group = _Group(Blocker(
                kind=BLOCKER_CHECK,
                key=key,
                message=_check_group_message(str(c.remedy), target, year),
                slot=str(target.value) if target is not None
                and target.kind == TARGET_DOCUMENT else None,
                remedy=c.remedy,
                target=target,
            ))
            check_groups[key] = group
        group.codes.append(c.code)

    ordered_files = [file_groups[s.slot].done() for s in slots if s.slot in file_groups]
    stale = _stale_blocker(slots, year)
    ordered_checks = [check_groups[k].done() for k in sorted(check_groups)]
    return tuple(
        ordered_files
        + ([stale] if stale is not None else [])
        + ordered_checks
        + _coverage_blockers(session, company_id, year)
    )


def period_readiness(session: Session, company_id: int, year: int) -> PeriodReadiness:
    """"Đủ dữ liệu cho N/M kiểm tra" + danh sách vướng mắc của một (DN, kỳ).

    KHÔNG đọc `check_runs`: con số này phải tính được từ trạng thái DB trước khi chạy
    kiểm tra lần nào. Đọc trạng thái đã lưu ở đây sẽ biến phép so "dự đoán bằng đã lưu"
    thành đồng nhất thức và giấu mất chỗ hai đường lệch nhau.

    `session` là tham số — hàm KHÔNG tự mở phiên nào.
    """
    present = available_sources(session, company_id, year)
    checks = tuple(
        predict_check(session, company_id, year, code, present)
        for code in _applicable_codes(session)
    )
    slots = _slot_statuses(session, company_id, year, present)
    return PeriodReadiness(
        company_id=company_id,
        year=year,
        checks=checks,
        slots=slots,
        blockers=_blockers(slots, checks, session, company_id, year),
        stale=any(s.stale for s in slots),
    )


__all__ = [
    "BLOCKER_CHECK",
    "BLOCKER_COVERAGE",
    "BLOCKER_FILE",
    "CHECK_BLOCKED",
    "CHECK_CONCLUSION",
    "CHECK_READY",
    "CHECK_RUN_TO_KNOW",
    "SLOT_NEEDS_BOOK",
    "SLOT_NEEDS_COLUMN_REVIEW",
    "SLOT_NOT_PARSED",
    "SLOT_NO_FILE",
    "SLOT_PARSE_ERROR",
    "SLOT_READY",
    "SLOT_STALE",
    "SLOT_STATES",
    "Blocker",
    "CheckReadiness",
    "PeriodReadiness",
    "SlotStatus",
    "period_readiness",
    "predict_check",
]
