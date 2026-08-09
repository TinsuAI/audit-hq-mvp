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

#120 bỏ lớp nói ở MỨC TRANG. Trước đây một câu mô tả cả file bằng tên tầng đã quyết
định vị trí cột ("Khớp mẫu biểu có sẵn"), đặt cạnh phần mỗi cột tự khai căn cứ của
mình — hai giọng nói về cùng một việc, và giọng mức trang đi stale vì các cột trong
cùng một file không nhất thiết cùng nguồn. Nay chỉ còn hai thứ: câu CỦA TỪNG CỘT
(`BasisColumn.evidence_sentence`, nêu cơ chế và giới hạn của cơ chế đó) và câu về CẢ
FILE mà không cột nào nói hộ được (`status_note`, `sheet_note` — trang tính nào, mấy
dòng, còn mấy cột chờ xác nhận).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.adapters.declared_fields import declared as declared_fields
from app.adapters.declared_fields import label_of
from app.adapters.evidence import (
    NEEDS_REVIEW,
    SOURCE_LABEL_VI,
    SOURCE_SENTENCE_VI,
    VERIFIED,
)
from app.adapters.templates import column_groups
from app.checks.registry import checks_reading
from app.models import DataFile

# Câu cho dòng trạng thái khi file chưa qua lượt nạp nào. Bảng gán cột chỉ render khi có
# cột đọc được, nên nếu chỗ này im thì file chưa đọc được ra một trang không lời giải
# thích. Tầng nào quyết định vị trí cột thì KHÔNG còn nói ở mức trang nữa (#120): mỗi
# cột mang căn cứ của riêng nó, còn một câu mô tả cả file bằng tên một tầng thì đi stale.
NEVER_PARSED = "Hệ thống chưa đọc file này lần nào"


def file_page_url(slug: str, file_id: int) -> str:
    """Địa chỉ DUY NHẤT của một file — mở được, gửi được, quay lại được."""
    return f"/companies/{slug}/documents/file/{file_id}"


def column_label(index: int, header: str | None = None) -> str:
    """Tên một cột như cán bộ đọc nó: chỉ số, kèm tiêu đề thật khi ảnh chụp cột có.

    MỘT chỗ dựng chuỗi này, dùng cho cả nhãn lựa chọn của bộ chọn cột lẫn câu tự khai
    của dòng nhóm cột con — hai chỗ nói cùng một thứ mà lệch câu chữ thì cán bộ phải tự
    khớp "cột 7" ở dòng này với "cột 7 · «…»" ở dòng kia.
    """
    return f"cột {index} · «{header}»" if header else f"cột {index}"


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

NO_CHECK_READS_IT = "Không kiểm tra nào đọc trường này."
NO_EVIDENCE_RECORDED = "Không ghi nhận bằng chứng nào cho cột đang đọc."

# Hai trạng thái KHÔNG có nguồn bằng chứng để nói, vì không đọc cột nào. Nhãn trạng thái
# ("Chưa gán") chỉ nêu trạng thái, không nêu thao tác phải làm — hai câu dưới nêu thao tác.
UNASSIGNED_MEANS = (
    "Chưa gán cột nào nên hệ thống không đọc gì cho trường này — chọn cột ở ô "
    "“Cột trên file” của dòng này, hoặc tích “Không có trong file” ngay cạnh nếu biểu "
    "này không có trường đó."
)
# Cùng trạng thái, nhưng màn KHÔNG dựng được hai ô kia: file nạp trước #112 không có ảnh
# chụp cột, nên dòng chỉ hiện “không có vị trí lưu”. Câu trên chỉ tới hai ô không tồn tại
# ở dòng đó — đúng lỗi mà vé này sinh ra để sửa, chỉ khác nhánh.
UNASSIGNED_NO_PICKER = (
    "Chưa gán cột nào nên hệ thống không đọc gì cho trường này — lượt nạp của file này "
    "không lưu ảnh chụp cột nên màn chưa dựng được bộ chọn; nạp lại file rồi gán cột."
)
ABSENT_MEANS = (
    "Cán bộ đã xác nhận file không có trường này; kiểm tra nào cần tới nó sẽ trả "
    "“chưa đánh giá được” thay vì tính trên số thiếu."
)


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
    # Màn CÓ dựng bộ chọn cột + ô khai vắng cho dòng này không. Quyết định câu chỉ đường
    # của trạng thái *chưa gán*: câu gọi tên hai ô đó, nên nhánh không dựng được chúng
    # phải nói việc khác. Mặc định `True` là ca thường — file có ảnh chụp cột.
    has_picker: bool = True
    # Tiêu đề THẬT của từng cột đang gán, lấy từ ảnh chụp cột lúc parse: "cột 7" không
    # nói được máy đang đọc đúng ô hay lệch một ô, còn tiêu đề của chính cột đó thì nói
    # được. Xếp CÙNG THỨ TỰ với `columns`; phần tử rỗng = cột nằm ngoài ảnh chụp (vị trí
    # đã lưu trỏ ra ngoài trang tính lượt nạp sau đọc được).
    headers: tuple[str, ...] = ()

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
        """Trục căn cứ, thành CÂU tại dòng của trường (#120) — cơ chế VÀ giới hạn của nó.

        Nói theo TRẠNG THÁI trước: trường chưa gán hay đã khai vắng thì không đọc cột nào,
        nên không có nguồn bằng chứng để nói — cái chúng cần là nghĩa của trạng thái và
        việc phải làm, vì nhãn trạng thái ("Chưa gán") chỉ nói được nửa đầu.

        Trường không kiểm tra nào đọc thì nói thẳng ra: `review_state` trả `verified` cho
        chính ca này, nên nhãn dựng từ `review` đọc ra là "đã được kiểm" trong khi sự thật
        là "không có gì phụ thuộc cột này".
        """
        if self.state == UNASSIGNED:
            return UNASSIGNED_MEANS if self.has_picker else UNASSIGNED_NO_PICKER
        if self.state == ABSENT:
            return ABSENT_MEANS
        if not self.evidence:
            return NO_EVIDENCE_RECORDED
        # Thuật ngữ ĐỨNG TRƯỚC nghĩa của nó, không bị thay bằng nghĩa. Xoá hẳn thuật ngữ
        # khỏi màn này thì cán bộ đọc mục B7 cẩm nang (liên kết ngay ở dòng trạng thái)
        # thấy một bộ từ vựng không khớp thứ gì trên màn hình, mà màn dữ liệu vẫn hiện
        # đúng những chữ đó ở chip. Giữ chữ, gắn nghĩa vào cạnh — đó là điều AC 6 đòi.
        term = SOURCE_LABEL_VI.get(self.evidence, self.evidence)
        sentence = f"{term} — {SOURCE_SENTENCE_VI.get(self.evidence, '')}".rstrip(" —")
        if not self.checks:
            return f"{sentence} {NO_CHECK_READS_IT}"
        return sentence

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

    @property
    def column_note(self) -> str:
        """Cột đang gán, thành CÂU cho dòng không có nhãn lựa chọn để nói hộ (#122).

        Lưới xem trước là phần TĂNG THÊM: lượt trích xuất đầu trả 202 rồi poll, và file
        chưa từng đọc thì không có ảnh chụp nào — dòng trường phải tự nói nó đang đọc cột
        nào kể cả khi lưới còn trống. `<select>` nói sẵn trong nhãn lựa chọn đang chọn;
        ô nhập chỉ số của nhóm cột con chỉ hiện `7,8`, nên câu này bù đúng chỗ đó.

        Dấu `+` là phép cộng thật: nhóm cột con đọc bằng TỔNG các cột (ADR #25).
        """
        return " + ".join(
            column_label(index, self.headers[i] if i < len(self.headers) else "")
            for i, index in enumerate(self.columns)
        )


@dataclass(frozen=True)
class ReadBasis:
    """Toàn bộ căn cứ đọc của một file — nguồn duy nhất của khối trên trang file.

    `parse_detail["sample_rows"]` KHÔNG đọc vào đây nữa (#121): dòng dữ liệu thật hiện ở
    lưới, nguyên vẹn theo hàng trang tính. Adapter vẫn ghi khoá đó — thôi ghi là đổi thứ
    một lượt nạp ghi xuống DB, không thuộc vé bố cục này.
    """

    parsed: bool
    match_source: str | None
    template_id: str | None
    layout: str | None
    sheet: str | None
    sheet_pinned: bool
    row_count: int | None
    form_signature: str | None
    columns: tuple[BasisColumn, ...]
    needs_confirmation: tuple[str, ...]
    # Ảnh chụp cột của file lúc parse — bộ chọn cột dựng từ đây. Rỗng với file nạp
    # trước #112 (tiến lên, không backfill): màn rơi về ô nhập chỉ số như cũ.
    choices: tuple[dict, ...] = ()

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
    def status_note(self) -> str:
        """Câu cho dòng trạng thái dưới lưới — thứ nói về CẢ FILE, không về một trường.

        Bốn ca, và ca đầu là ca dễ mất nhất: bảng gán cột chỉ render khi có cột đọc được,
        nên file chưa nạp lần nào mà chỗ này im thì trang không còn chỗ nào nói ra điều đó.
        """
        if not self.parsed:
            return NEVER_PARSED
        if self.needs_count:
            return (
                f"Còn {self.needs_count} cột cần cán bộ xác nhận vị trí: "
                f"{', '.join(self.needs_confirmation)}."
            )
        if self.columns:
            return "Mọi cột đang đọc đều có bằng chứng đủ mạnh cho các kiểm tra dùng tới chúng."
        return (
            "Lượt nạp gần nhất không đọc ra bố cục cột nào — chọn đúng trang tính chứa "
            "dữ liệu chi tiết rồi nạp lại."
        )

    @property
    def sheet_note(self) -> str:
        """Trang tính đang đọc + ai quyết định nó."""
        if not self.sheet:
            return "Chưa xác định trang tính nào chứa biểu."
        who = "cán bộ ghim" if self.sheet_pinned else "hệ thống tự nhận diện"
        return f"Đọc trang tính “{self.sheet}” ({who})."

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


def grid_column_marks(basis: ReadBasis) -> dict[str, dict]:
    """`{chỉ số cột: {trường, nhãn, nhãn ba trục}}` — chú giải cột cho lưới xem trước.

    Lưới KHÔNG giữ bộ từ vựng riêng: nhãn lấy thẳng từ `BasisColumn.labels`, đúng
    property mà dòng trường của bảng gán cột đọc (#123, ADR #29 mục 1). Trước đây lưới
    nhận một cờ `needs` rồi tự đặt câu chữ trong JavaScript, nên "cột này còn chờ cán bộ
    xác nhận" là bộ từ vựng THỨ TƯ — nằm ngoài ba trục, và không chỗ nào bắt được khi nó
    lệch câu chữ với dòng trường nói về cùng cột đó.

    Đánh dấu MỌI cột của một nhóm `(6a)+(6b)`, không riêng cột đầu: sáng một cột thì cán
    bộ tưởng cột kia không được đọc.
    """
    return {
        str(index): {
            "field": c.field,
            "label": c.label,
            "labels": [
                {"axis": lb.axis, "text": lb.text, "tone": lb.tone} for lb in c.labels
            ],
        }
        for c in basis.columns
        for index in c.columns
    }


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
        snapshot = {c.get("index"): c for c in choices if isinstance(c, dict)}
        # Điều kiện màn dựng bộ chọn + ô khai vắng, đúng như template hỏi
        # (`basis.can_confirm and basis.has_choices`): map ghi theo `(DN, slot, vân tay)`
        # nên không có vân tay thì không có khoá ghi, và không có ảnh chụp cột thì
        # không dựng nổi danh sách lựa chọn.
        has_picker = bool(detail.get("form_signature")) and bool(choices)
        columns = tuple(
            _basis_column(
                row.slot, field, meta.get(field) or {}, groups.get(field, []),
                absent=field in absent,
                snapshot=snapshot,
                has_picker=has_picker,
            )
            for field in order
        )
    parsed = bool(columns) or bool(detail)

    return ReadBasis(
        parsed=parsed,
        match_source=row.match_source,
        template_id=row.template_id or detail.get("template_id"),
        layout=row.parse_layout,
        sheet=row.sheet_override or detail.get("sheet") or None,
        sheet_pinned=row.sheet_override is not None,
        row_count=row.row_count,
        form_signature=detail.get("form_signature"),
        columns=columns,
        needs_confirmation=tuple(c.label for c in columns if c.needs_review),
        choices=tuple(detail.get("column_choices") or ()),
    )


def _basis_column(
    slot: str, field: str, meta: dict, cols: list[int], absent: bool = False,
    snapshot: dict | None = None, has_picker: bool = True,
) -> BasisColumn:
    evidence = meta.get("evidence")
    snapshot = snapshot or {}
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
        has_picker=has_picker,
        headers=tuple(str((snapshot.get(i) or {}).get("header") or "") for i in cols),
    )


__all__ = [
    "NEVER_PARSED",
    "BasisColumn",
    "ReadBasis",
    "column_label",
    "column_letter",
    "file_page_url",
    "file_read_basis",
    "grid_column_marks",
]
