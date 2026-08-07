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

from dataclasses import dataclass

from app.adapters.evidence import (
    FIELD_LABEL_VI,
    NEEDS_REVIEW,
    REVIEW_LABEL_VI,
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


@dataclass(frozen=True)
class BasisColumn:
    """Một trường dữ liệu: đọc ở cột nào, và cái gì quyết định cột đó."""

    field: str
    label: str
    evidence: str | None
    evidence_label: str
    review: str
    needs_review: bool
    columns: tuple[int, ...]
    column_ref: str
    checks: tuple[str, ...]

    @property
    def review_label(self) -> str:
        return REVIEW_LABEL_VI.get(self.review, self.review)

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

    @property
    def needs_count(self) -> int:
        return len(self.needs_confirmation)

    @property
    def can_confirm(self) -> bool:
        """Có VỊ TRÍ cột để xác nhận không. Không có thì chỉ còn ghim trang tính.

        Đo theo vị trí đã lưu chứ không theo số cột có bằng chứng: đường xác nhận đọc
        `column_map`, nên một file chỉ có bằng chứng mà không có vị trí nào sẽ hiện nút
        xác nhận rồi báo lỗi khi bấm.
        """
        return bool(self.form_signature) and any(c.columns for c in self.columns)


def file_read_basis(row: DataFile) -> ReadBasis:
    """Căn cứ đọc của một file, dựng từ `parse_detail` của lượt nạp gần nhất."""
    detail = row.parse_detail_obj
    groups = column_groups(detail.get("column_map"))
    meta = {c.get("field"): c for c in (detail.get("columns") or []) if c.get("field")}

    # HỢP của hai nguồn, thứ tự theo `columns` (đã sắp theo biểu ở `_evidence_columns`)
    # rồi tới các trường chỉ có trong map. Bỏ bên nào cũng là giấu một cột: map là thứ
    # parser THẬT SỰ đọc, còn bằng chứng ghi cho một trường mà map không giữ vị trí
    # (`resolve_template_evidence` lọc map theo trường có vị trí) vẫn là căn cứ đọc.
    order = list(meta) + [f for f in groups if f not in meta]
    columns = tuple(
        _basis_column(row.slot, field, meta.get(field) or {}, groups.get(field, []))
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
    )


def _basis_column(slot: str, field: str, meta: dict, cols: list[int]) -> BasisColumn:
    evidence = meta.get("evidence")
    review = meta.get("review") or (VERIFIED if evidence else NEEDS_REVIEW)
    return BasisColumn(
        field=field,
        label=meta.get("label") or FIELD_LABEL_VI.get(field, field),
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
