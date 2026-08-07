"""Tầng BUILTIN của template registry — cấu trúc biểu đã được curate (ADR #23 T3).

Mỗi entry mô tả MỘT họ biểu: tập vân tay `form_signature`, map cột và dòng bắt đầu
dữ liệu. Thứ tự resolve khi parse:

    map officer-confirmed của DN  →  template builtin khớp vân tay
                                  →  dò từ khoá  →  cổng review

Khớp template = TỰ QUA cổng review. Cổng review canh CẤU TRÚC chưa có người xem;
template là cấu trúc đã được xem lúc curate (code + PR + test fixture), nên bắt mỗi
DN bấm xác nhận lại là bắt họ review lại đúng thứ mình đã review, không thêm được
kiểm tra nào cổng thực sự làm. Rủi ro chấp nhận: một template curate SAI sẽ áp im
lặng trên diện rộng — chặn bằng hai lớp: test fixture cho từng template, và badge
"Khớp mẫu: <tên>" luôn hiển thị.

**Map cán bộ thắng template ở MỨC TỪNG TRƯỜNG, ngay lúc đọc file** (ADR #24 mục 5).
`resolve_columns` trộn ba tầng theo đúng thứ tự trên: trường nào map cán bộ có thì
lấy vị trí của map và mang nguồn `officer-confirmed`, trường còn lại lấy theo
template (hoặc cột mặc định của slot khi không họ nào khớp).

*Ràng buộc khi seed họ mới:* một họ có `column_map` KHÔNG rỗng chỉ được seed khi
test ca xung đột (`tests/test_officer_map_precedence.py`) còn xanh — đó là chỗ duy
nhất chứng minh map cán bộ không bị template che. Trước bản sửa này cả bốn họ đã
seed đều để `column_map` rỗng, nên lỗi che map chưa từng lộ ra trên dữ liệu thật.

*Bố cục MỞ RỘNG* (Mẫu 15/15a suy map từ dòng đánh số) NAY cũng nhận vị trí của cán
bộ (#95): map lưu diễn đạt được `trường → [cột…]` nên nhóm cột con `(6a)+(6b)` giữ
nguyên ngữ nghĩa, và sau khi áp thì đẳng thức cân đối của biểu được KIỂM LẠI — không
khớp là ném ``OfficerMapBalanceError``, không nạp. Xem `app/adapters/extended_layout.py`.

**Tầng này sống trong CODE, đổi qua PR.** ADR #23 đã chốt yêu cầu tương lai: quản
lý template qua UI (bảng DB seed từ code). CHƯA build.

Vân tay tính từ vùng tiêu đề (`app.adapters.form_signature`) — chỉ cấu trúc cột,
không chứa mã số thuế, tên DN hay số liệu, nên hằng số dưới đây an toàn để commit.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field

from app.adapters.evidence import BUILTIN_TEMPLATE, OFFICER_CONFIRMED, POSITION_ONLY

# Nguồn khớp ghi vào `data_files.match_source` — TẦNG NÀO đã quyết định vị trí cột.
MATCH_BUILTIN = "builtin-template"
MATCH_OFFICER = "officer-map"
MATCH_KEYWORD = "keyword"
MATCH_DEFAULT = "default"
# Bố cục mở rộng: map suy từ dòng đánh số của chính file, chứng minh bằng đẳng thức
# của biểu (ADR #15). KHÔNG gộp vào `keyword` — cơ chế khác hẳn, gọi sai tên là nói
# với cán bộ rằng cột đã khớp tiêu đề trong khi không nhãn nào được đọc.
MATCH_EXTENDED = "extended-layout"

@dataclass(frozen=True)
class BuiltinTemplate:
    """Một họ biểu đã curate.

    `signatures` là TẬP: cùng một họ có thể ra nhiều vân tay khi DN thêm/bớt cột phụ
    ở đuôi mà vùng cột nghiệp vụ không đổi.

    `column_map` chỉ khai các cột KHÁC mặc định của slot — parser merge lên `_COL`,
    nên template của họ chuẩn có thể để rỗng và chỉ đóng vai trò "đã xác nhận cấu
    trúc này".
    """

    id: str
    name: str
    slot: str
    signatures: frozenset[str]
    data_start: int
    column_map: dict[str, int] = field(default_factory=dict)
    note: str = ""


# Seed từ census cấu trúc file thật 2026-07-31 (475 file / 976 sheet / 11 DN) —
# `.ai/notes/2026-07-31-ktstq-5-nam-template-ky-quyet-toan.md`. Vân tay đo bằng
# `app.adapters.form_signature.compute_form_signature` trên đúng sheet mà
# `select_sheet` chọn cho slot đó.
BUILTIN_TEMPLATES: tuple[BuiltinTemplate, ...] = (
    BuiltinTemplate(
        id="m15-tt39-chuan",
        name="Mẫu 15 TT39 — bố cục chuẩn",
        slot="m15",
        signatures=frozenset({"b7035babb726b641bf1af28751c8a41d"}),
        data_start=9,
        note="32 file / 8 DN trong census 2026-07-31; cột đúng mặc định slot.",
    ),
    BuiltinTemplate(
        id="m15-tt39-bien-the",
        name="Mẫu 15 TT39 — biến thể tiêu đề dài",
        slot="m15",
        signatures=frozenset({"7379daa7332c5a9530cb9a0c39734993"}),
        data_start=11,
        note="24 file / 3 DN; tiêu đề chiếm thêm 2 dòng, vị trí cột không đổi.",
    ),
    BuiltinTemplate(
        id="m15a-tt39-chuan",
        name="Mẫu 15a TT39 — bố cục chuẩn",
        slot="m15a",
        signatures=frozenset({"f01f5ab9b1ee59959c7219658f061c05"}),
        data_start=9,
        note="25 file / 8 DN; cột đúng mặc định slot.",
    ),
    BuiltinTemplate(
        id="m15a-tt39-bien-the",
        name="Mẫu 15a TT39 — biến thể tiêu đề dài",
        slot="m15a",
        signatures=frozenset({"93e0b9b896d6ff9334ebe3187fa82049"}),
        data_start=12,
        note="19 file / 3 DN; tiêu đề chiếm thêm 3 dòng, vị trí cột không đổi.",
    ),
)


def match_template(
    slot: str, signature: str | None, data_start: int | None = None
) -> BuiltinTemplate | None:
    """Template builtin khớp vân tay của slot; None nếu không họ nào khớp.

    Khớp đòi CẢ `data_start` dò được trùng với `data_start` lúc curate. Vân tay chỉ
    hash vùng tiêu đề nên hai file cùng vân tay vẫn có thể bắt đầu dữ liệu ở dòng
    khác (đã gặp trong census: một file lệch 1 dòng). Nhận nhầm ở đó sẽ dời điểm đọc
    và nuốt mất một dòng dữ liệu, im lặng — nên thà không khớp.
    """
    if not signature:
        return None
    for tpl in BUILTIN_TEMPLATES:
        if tpl.slot != slot or signature not in tpl.signatures:
            continue
        if data_start is not None and data_start != tpl.data_start:
            continue
        return tpl
    return None


def column_groups(raw: Mapping[str, object] | None) -> dict[str, list[int]]:
    """Chuẩn hoá map cột về `trường → [cột…]`.

    Giá trị lưu được phép là `int` (một cột — mọi map cũ trong DB và toàn bộ đường
    bố cục chuẩn) hoặc `list[int]` (một trường đọc bằng TỔNG nhiều cột con, chỉ có ở
    bố cục mở rộng: `(6a)+(6b)`). Một hàm chuẩn hoá duy nhất để chỗ nào so map với
    map cũng so cùng một hình dạng — #95 sinh ra từ việc map lưu chỉ giữ được cột đầu
    nhóm. Giá trị hỏng bị bỏ, không đoán.
    """
    out: dict[str, list[int]] = {}
    for f, value in (raw or {}).items():
        items = value if isinstance(value, list | tuple) else [value]
        cols: list[int] = []
        for item in items:
            try:
                cols.append(int(item))
            except (TypeError, ValueError):
                cols = []
                break
        if cols:
            out[f] = cols
    return out


def officer_column_groups(
    officer_maps: Mapping[str, Mapping[str, object]] | None,
    form_sig: str | None,
    known_fields: Iterable[str],
) -> dict[str, list[int]]:
    """Map cột cán bộ đã xác nhận áp cho ĐÚNG vân tay này, dạng nhóm (rỗng nếu chưa có).

    Khoá map là `(DN, slot, vân tay form)` — người gọi đã lọc theo DN + slot, ở đây
    chỉ còn lọc vân tay. Bỏ field slot không đọc: map lưu là dữ liệu cũ trong DB,
    một field lạ không được phép tạo cột mới cho parser.
    """
    if not officer_maps or not form_sig:
        return {}
    known = set(known_fields)
    saved = column_groups(officer_maps.get(form_sig))
    return {f: cols for f, cols in saved.items() if f in known}


def officer_columns(
    officer_maps: Mapping[str, Mapping[str, object]] | None,
    form_sig: str | None,
    known_fields: Iterable[str],
) -> dict[str, int]:
    """Như trên nhưng cho đường bố cục CHUẨN — mỗi trường đúng MỘT cột.

    Đường chuẩn đọc một ô cho mỗi trường, không cộng được nhóm cột, nên trường nào
    map lưu ghi nhiều cột thì KHÔNG áp (áp cột đầu là im lặng bỏ phần còn lại). Không
    áp thì cũng không gắn nhãn "cán bộ xác nhận" — trạng thái "cần xác nhận" ở lại,
    hiện ra. Màn xác nhận đã chặn từ đầu: file bố cục chuẩn không nhận nhiều cột.
    """
    return {
        f: cols[0]
        for f, cols in officer_column_groups(officer_maps, form_sig, known_fields).items()
        if len(cols) == 1
    }


def resolve_columns(
    base_col: dict[str, int],
    template: BuiltinTemplate | None,
    officer_maps: dict[str, dict[str, int]] | None,
    form_sig: str | None,
) -> tuple[dict[str, int], dict[str, int]]:
    """`(map cột sẽ đọc, phần map cán bộ đã áp)` — ưu tiên cán bộ > template > mặc định.

    Trộn ở MỨC TỪNG TRƯỜNG: cán bộ xác nhận một cột không làm mất các cột khác mà
    template đã curate, và ngược lại template không che cột cán bộ vừa sửa.
    """
    officer = officer_columns(officer_maps, form_sig, base_col)
    col = {**base_col, **(template.column_map if template else {}), **officer}
    return col, officer


def match_source_for(
    officer: dict[str, int],
    template: BuiltinTemplate | None,
    evidence: dict[str, str],
) -> str:
    """Tầng đã quyết định vị trí cột — giá trị ghi vào `data_files.match_source`.

    Nhánh bố cục mở rộng KHÔNG đi qua đây: ở đó tầng quyết định là dòng đánh số của
    chính file (``MATCH_EXTENDED``), không suy được từ evidence.
    """
    if officer:
        return MATCH_OFFICER
    if template is not None:
        return MATCH_BUILTIN
    matched = any(src != POSITION_ONLY for src in evidence.values())
    return MATCH_KEYWORD if matched else MATCH_DEFAULT


def apply_officer_evidence(
    evidence: dict[str, str], officer: dict[str, int]
) -> dict[str, str]:
    """Đánh dấu `officer-confirmed` cho ĐÚNG các cột đã đọc bằng vị trí của cán bộ."""
    for f in officer:
        if f in evidence:
            evidence[f] = OFFICER_CONFIRMED
    return evidence


def resolve_template_evidence(
    template: BuiltinTemplate | None,
    evidence_fields: tuple[str, ...],
    column_map: dict[str, int],
    form_sig: str,
    fallback: Callable[[], dict[str, str]],
    officer: dict[str, int] | None = None,
) -> tuple[dict[str, str], dict]:
    """`(evidence, provenance detail)` cho đường parse chuẩn của một slot.

    Khớp template → mọi cột mang nguồn `builtin-template` (rank giữa khớp-tiêu-đề và
    map-cán-bộ) nên cổng review tự qua. Không khớp → giữ nguyên đường cũ (dò từ khoá
    rồi cổng review). Cột nào đọc theo vị trí CÁN BỘ chỉ định thì mang
    `officer-confirmed` bất kể hai nhánh trên. `match_source` luôn nói rõ đang đọc
    bằng gì — không đường nào parse im lặng.
    """
    officer = officer or {}
    if template is not None:
        evidence = {f: BUILTIN_TEMPLATE for f in evidence_fields if f in column_map}
    else:
        evidence = fallback()
    apply_officer_evidence(evidence, officer)
    detail = {
        "form_signature": form_sig,
        "column_map": {f: column_map[f] for f in evidence if f in column_map},
        "template_id": template.id if template is not None else None,
        "match_source": match_source_for(officer, template, evidence),
    }
    if template is not None:
        detail["template_name"] = template.name
    return evidence, detail


def template_by_id(template_id: str | None) -> BuiltinTemplate | None:
    if not template_id:
        return None
    for tpl in BUILTIN_TEMPLATES:
        if tpl.id == template_id:
            return tpl
    return None


__all__ = [
    "BUILTIN_TEMPLATES",
    "MATCH_BUILTIN",
    "MATCH_DEFAULT",
    "MATCH_EXTENDED",
    "MATCH_KEYWORD",
    "MATCH_OFFICER",
    "BuiltinTemplate",
    "apply_officer_evidence",
    "column_groups",
    "match_source_for",
    "match_template",
    "officer_column_groups",
    "officer_columns",
    "resolve_columns",
    "resolve_template_evidence",
    "template_by_id",
]
