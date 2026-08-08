"""Trang file: MỘT địa chỉ cho mỗi file + căn cứ đọc của file đó (#92, ADR #24).

Trang xem file và trang xác nhận cột trước đây là hai địa chỉ dựng cùng một thứ.
Gộp lại thì địa chỉ chuẩn là ``/companies/{slug}/documents/file/{id}`` — hai địa chỉ
cũ chuyển hướng về đây, và mọi chỗ trong sản phẩm dựng liên kết bằng ``file_page_url``
thay vì nối chuỗi, để lần dời địa chỉ sau chỉ phải sửa một chỗ.

``file_read_basis`` là toàn bộ CĂN CỨ ĐỌC mà #87 đã gỡ khỏi dòng file ở màn dữ liệu
(ADR #24 sửa ADR #18): dòng file chỉ còn thứ có hệ quả, còn "hệ thống đọc file này
bằng cách nào" nằm cách một cú bấm. Cấu trúc dựng ở đây chứ không trong template để
khẳng định được ở mức dữ liệu, và để một chỗ duy nhất quyết định câu chữ.

Hàm KHÔNG nhận `Session`: mọi thứ nó cần nằm trên chính dòng registry. File chưa nạp
lần nào (và mọi file nạp trước #84, khi `match_source` còn rỗng trên 15/15 file) vẫn
phải mở được — nên đường thiếu dữ liệu nói ra điều đó chứ không ném lỗi.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.adapters.declared_fields import declared as declared_fields
from app.adapters.declared_fields import label_of
from app.adapters.evidence import (
    NEEDS_REVIEW,
    SOURCE_LABEL_VI,
    VERIFIED,
)
from app.adapters.templates import (
    MATCH_BUILTIN,
    MATCH_DEFAULT,
    MATCH_EXTENDED,
    MATCH_KEYWORD,
    MATCH_OFFICER,
    column_groups,
)
from app.checks.registry import checks_reading
from app.models import DataFile

# Tầng đã quyết định vị trí cột → câu nói cho cán bộ. Nêu CƠ CHẾ chứ không chỉ tên
# tầng: "khớp mẫu" và "suy từ dòng đánh số" là hai mức tin cậy khác hẳn nhau.
MATCH_SOURCE_LABEL_VI: dict[str, str] = {
    MATCH_OFFICER: "Cán bộ đã xác nhận vị trí cột cho cấu trúc biểu này",
    MATCH_BUILTIN: "Khớp mẫu biểu có sẵn của hệ thống",
    MATCH_EXTENDED: "Suy cột từ dòng đánh số của chính file, kiểm lại bằng đẳng thức cân đối",
    MATCH_KEYWORD: "Dò từ khoá ở dòng tiêu đề của file",
    MATCH_DEFAULT: "Đọc theo vị trí mặc định của biểu — không nhãn nào khớp",
}
MATCH_SOURCE_UNKNOWN = "Không ghi nhận được tầng nào đã quyết định vị trí cột"
NEVER_PARSED = "Hệ thống chưa đọc file này lần nào"

PARSE_LAYOUT_LABEL_VI: dict[str, str] = {
    "standard": "Bố cục chuẩn của biểu",
    "extended": "Bố cục mở rộng — một trường đọc bằng tổng nhiều cột con",
    "labeled": "Đọc theo nhãn cột ghi trên chính file",
}


def file_page_url(slug: str, file_id: int) -> str:
    """Địa chỉ DUY NHẤT của một file — mở được, gửi được, quay lại được."""
    return f"/companies/{slug}/documents/file/{file_id}"


def column_letter(index: int) -> str:
    """Chỉ số cột 0-based → chữ cái cột của Excel (0 = A)."""
    out = ""
    x = index
    while True:
        out = chr(65 + x % 26) + out
        x = x // 26 - 1
        if x < 0:
            return out


# Ba trạng thái gán của một trường khai (ADR #28). Trạng thái thứ ba là LỜI CỦA CÁN BỘ.
ASSIGNED = "assigned"
UNASSIGNED = "unassigned"
ABSENT = "absent"

STATE_LABEL_VI = {
    ASSIGNED: "Đã gán",
    UNASSIGNED: "Chưa gán",
    ABSENT: "Không có trong file",
}

# Ba trục nhãn của luồng cán bộ (ADR #29). Mỗi nhãn thuộc ĐÚNG một trục, và không trục nào nói
# lại điều trục khác đã nói.
AXIS_ASSIGNMENT = "assignment"  # trường này đọc ở đâu
AXIS_EVIDENCE = "evidence"      # vì sao tin là cột đó
AXIS_WORK = "work"              # cán bộ còn phải làm gì
AXES = (AXIS_ASSIGNMENT, AXIS_EVIDENCE, AXIS_WORK)

# Sắc thái của nhãn. Giá trị phải là lớp CÓ THẬT trong `style.css` (`.badge.critical`,
# `.badge.warning`, `.badge.muted`) — `danger` không có rule nào nên nhãn sẽ hiện trần.
TONE_BLOCKING = "critical"
TONE_ATTENTION = "warning"
TONE_QUIET = "muted"

NO_CHECK_READS_IT = "Không kiểm tra nào đọc trường này"


@dataclass(frozen=True)
class FieldLabel:
    axis: str
    text: str
    tone: str


@dataclass(frozen=True)
class BasisColumn:
    """Một trường KHAI của biểu: đọc ở cột nào, và cái gì quyết định cột đó.

    Có dòng kể cả khi máy không đặt được trường này ở file — đó là điểm của màn theo
    trường (#112). Mô hình cũ chỉ dựng dòng cho trường đã có bằng chứng, nên file bố
    cục lệch hẳn ra biểu mẫu rỗng và kẹt vĩnh viễn (#95).
    """

    field: str
    label: str
    evidence: str | None
    evidence_label: str
    review: str
    needs_review: bool
    columns: tuple[int, ...]
    column_ref: str
    checks: tuple[str, ...]
    state: str = ASSIGNED
    required: bool = False
    row_key: bool = False
    # Tiêu đề + mẫu giá trị của CỘT ĐANG GÁN, lấy từ ảnh chụp cột lúc parse. Màn
    # hiện giá trị thật thay cho chỉ số cột trần: "cột 7" không nói được máy đang
    # đọc đúng ô hay lệch một ô, còn `1.5 / 1.51 / 1.52` thì nói được.
    header: str = ""
    samples: tuple[str, ...] = ()

    @property
    def labels(self) -> tuple[FieldLabel, ...]:
        """Nhãn HIỆN theo ngoại lệ: trường đã gán và không còn việc gì thì trả rỗng.

        Trục *căn cứ* không góp nhãn ở đây — nó nói bằng câu đủ nghĩa (`evidence_sentence`)
        tại chỗ dùng, nên một cột bằng chứng yếu chỉ được nói MỘT lần, ở trục *việc còn lại*.
        """
        if self.state == ABSENT:
            return (FieldLabel(AXIS_ASSIGNMENT, STATE_LABEL_VI[ABSENT], TONE_QUIET),)
        if self.state == UNASSIGNED:
            tone = (
                TONE_BLOCKING if self.row_key
                else TONE_ATTENTION if self.required
                else TONE_QUIET
            )
            return (FieldLabel(AXIS_ASSIGNMENT, STATE_LABEL_VI[UNASSIGNED], tone),)
        if self.needs_review:
            return (FieldLabel(AXIS_WORK, "Cần xác nhận", TONE_ATTENTION),)
        return ()

    @property
    def evidence_sentence(self) -> str:
        """Trục căn cứ, thành câu. Trường không kiểm tra nào đọc thì nói thẳng ra điều đó.

        `review_state` trả `verified` cho chính trường hợp này, nên nhãn dựng từ `review`
        đọc ra là "đã được kiểm" trong khi sự thật là "không có gì phụ thuộc cột này".
        """
        if not self.checks:
            return f"{self.evidence_label} — {NO_CHECK_READS_IT}"
        return self.evidence_label

    @property
    def is_absent(self) -> bool:
        return self.state == ABSENT

    @property
    def is_group(self) -> bool:
        return len(self.columns) > 1

    @property
    def col_value(self) -> str:
        """Giá trị ô nhập của biểu mẫu xác nhận: `"8"` hoặc `"5,6"` (nhóm cột con)."""
        return ",".join(str(i) for i in self.columns)


@dataclass(frozen=True)
class ReadBasis:
    """Toàn bộ căn cứ đọc của một file — nguồn duy nhất của khối trên trang file."""

    parsed: bool
    match_source: str | None
    match_source_label: str
    template_id: str | None
    template_name: str | None
    layout: str | None
    layout_label: str
    sheet: str | None
    sheet_pinned: bool
    row_count: int | None
    form_signature: str | None
    columns: tuple[BasisColumn, ...]
    needs_confirmation: tuple[str, ...]
    # Ảnh chụp cột của file lúc parse — bộ chọn cột dựng từ đây. Rỗng với file nạp
    # trước #112 (tiến lên, không backfill): màn rơi về ô nhập chỉ số như cũ.
    choices: tuple[dict, ...] = ()
    # Vài DÒNG dữ liệu thật, nguyên vẹn theo hàng — bảng gán cột dựng theo dòng nên
    # phải là dòng có thật, không phải mẫu ghép từ nhiều dòng khác nhau.
    sample_rows: tuple[dict, ...] = ()

    @property
    def needs_count(self) -> int:
        return len(self.needs_confirmation)

    @property
    def has_choices(self) -> bool:
        return bool(self.choices)

    @property
    def missing_row_keys(self) -> tuple[str, ...]:
        """Khoá dòng chưa gán/xác nhận vắng → KHÔNG dựng nổi một dòng Tầng 1 nào."""
        return tuple(c.label for c in self.columns if c.row_key and c.state != ASSIGNED)

    @property
    def missing_required(self) -> tuple[str, ...]:
        """Bắt buộc theo biểu mà KHÔNG phải khoá dòng → nhận file, cảnh báo, đánh dấu."""
        return tuple(
            c.label for c in self.columns
            if c.required and not c.row_key and c.state != ASSIGNED
        )

    @property
    def can_confirm(self) -> bool:
        """Gán được cột không. Không thì chỉ còn ghim trang tính.

        Hai đường: đã có vị trí lưu để sửa, HOẶC có ảnh chụp cột để gán từ đầu. Đường
        thứ hai là điểm của #112 — trước đây đo riêng theo vị trí đã lưu, nên file máy
        đặt được 0 trường ra biểu mẫu rỗng và kẹt vĩnh viễn (#95). Vẫn cần vân tay
        form: map lưu theo `(DN, slot, vân tay)`, không có vân tay thì không có khoá ghi.
        """
        return bool(self.form_signature) and (
            any(c.columns for c in self.columns) or self.has_choices
        )


def file_read_basis(
    row: DataFile, absent_fields: Iterable[str] | None = None,
) -> ReadBasis:
    """Căn cứ đọc của một file, dựng từ `parse_detail` của lượt nạp gần nhất.

    `absent_fields` = trường cán bộ đã xác nhận không có trong file, lấy từ map đã
    lưu của `(DN, slot, vân tay)`. Truyền vào chứ không tự tra: hàm này không giữ
    phiên DB, và người gọi đã có sẵn map đó."""
    detail = row.parse_detail_obj
    groups = column_groups(detail.get("column_map"))
    meta = {c.get("field"): c for c in (detail.get("columns") or []) if c.get("field")}

    # Thứ tự theo TẬP TRƯỜNG KHAI của biểu, rồi tới trường lạ chỉ có trong dữ liệu cũ.
    # Khai là nguồn sự thật: mỗi trường khai có MỘT dòng, kể cả trường máy không đặt
    # được ở file này — đó là đường gỡ cho file bố cục lệch hẳn (#95). Trường ngoài khai
    # vẫn hiện vì map cũ trong DB có thể mang nó, và giấu đi là giấu một cột đang đọc.
    # File CHƯA nạp lần nào không có bố cục để nói về: dựng 11 dòng "chưa gán" ở đó là
    # bịa ra một biểu mẫu cho một file hệ thống chưa mở. Đường "chưa đọc lần nào" giữ
    # nguyên như trước — nó nói ra điều đó thay vì ném lỗi.
    if not detail:
        columns: tuple[BasisColumn, ...] = ()
    else:
        declared = [f.name for f in declared_fields(row.slot)]
        extra = [f for f in list(meta) + list(groups) if f not in declared]
        seen: set[str] = set()
        order = [f for f in declared + extra if not (f in seen or seen.add(f))]
        absent = set(absent_fields or ())
        choices = detail.get("column_choices") or ()
        by_index = {c.get("index"): c for c in choices if isinstance(c, dict)}
        columns = tuple(
            _basis_column(
                row.slot, field, meta.get(field) or {}, groups.get(field, []),
                absent=field in absent,
                choice=by_index.get((groups.get(field) or [None])[0]),
            )
            for field in order
        )
    parsed = bool(columns) or bool(detail)

    return ReadBasis(
        parsed=parsed,
        match_source=row.match_source,
        match_source_label=_match_source_label(row.match_source, parsed),
        template_id=row.template_id or detail.get("template_id"),
        template_name=detail.get("template_name"),
        layout=row.parse_layout,
        layout_label=PARSE_LAYOUT_LABEL_VI.get(row.parse_layout or "", ""),
        sheet=row.sheet_override or detail.get("sheet") or None,
        sheet_pinned=row.sheet_override is not None,
        row_count=row.row_count,
        form_signature=detail.get("form_signature"),
        columns=columns,
        needs_confirmation=tuple(c.label for c in columns if c.needs_review),
        choices=tuple(detail.get("column_choices") or ()),
        sample_rows=tuple(detail.get("sample_rows") or ()),
    )


def _basis_column(
    slot: str, field: str, meta: dict, cols: list[int], absent: bool = False,
    choice: dict | None = None,
) -> BasisColumn:
    evidence = meta.get("evidence")
    declared = {f.name: f for f in declared_fields(slot)}.get(field)
    if absent:
        state = ABSENT
    elif cols:
        state = ASSIGNED
    else:
        state = UNASSIGNED
    # `review` là trục BẰNG CHỨNG: "cột này đọc bằng căn cứ yếu tới đâu". Chỉ trường ĐÃ
    # GÁN mới có câu trả lời — chưa gán thì không đọc cột nào, xác nhận vắng thì cán bộ
    # đã kết luận. Nhét hai trạng thái kia vào cổng review làm phồng số "cột cần xác
    # nhận" bằng những dòng không đọc gì; việc phải làm với chúng nằm ở cảnh báo thiếu
    # trường bắt buộc / khoá dòng, là đúng chỗ theo ADR #28.
    if state == ABSENT:
        review = VERIFIED
    elif meta or cols:
        # Parser đã nói gì đó về trường này (có mục bằng chứng, hoặc có vị trí lưu) →
        # giữ NGUYÊN cách tính cũ. Có bằng chứng mà map không giữ vị trí vẫn là cột
        # parser ĐÃ đọc, không được im chỉ vì thiếu vị trí.
        review = meta.get("review") or (VERIFIED if evidence else NEEDS_REVIEW)
    else:
        # Trường KHAI mà parser chưa nói gì: chưa đọc cột nào nên không có gì để soát.
        # Việc phải làm với nó nằm ở cảnh báo thiếu khoá dòng / thiếu trường bắt buộc.
        review = VERIFIED
    return BasisColumn(
        field=field,
        label=meta.get("label") or label_of(slot, field),
        evidence=evidence,
        evidence_label=(
            SOURCE_LABEL_VI.get(evidence, evidence) if evidence
            else "Không ghi nhận bằng chứng"
        ),
        review=review,
        needs_review=review == NEEDS_REVIEW,
        columns=tuple(cols),
        column_ref=", ".join(column_letter(i) for i in cols),
        checks=tuple(checks_reading(slot, field)),
        state=state,
        required=bool(declared and declared.required),
        row_key=bool(declared and declared.row_key),
        header=str((choice or {}).get("header") or ""),
        samples=tuple((choice or {}).get("samples") or ()),
    )


def _match_source_label(match_source: str | None, parsed: bool) -> str:
    if match_source:
        return MATCH_SOURCE_LABEL_VI.get(match_source, match_source)
    return MATCH_SOURCE_UNKNOWN if parsed else NEVER_PARSED


__all__ = [
    "MATCH_SOURCE_LABEL_VI",
    "PARSE_LAYOUT_LABEL_VI",
    "BasisColumn",
    "ReadBasis",
    "column_letter",
    "file_page_url",
    "file_read_basis",
]
