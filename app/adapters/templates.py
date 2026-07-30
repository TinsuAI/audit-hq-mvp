"""Tầng BUILTIN của template registry — cấu trúc biểu đã được curate (ADR #23 T3).

Mỗi entry mô tả MỘT họ biểu: tập vân tay `form_signature`, map cột và dòng bắt đầu
dữ liệu. Thứ tự resolve khi parse:

    map officer-confirmed của DN  →  template builtin khớp vân tay
                                  →  dò từ khoá  →  cổng review

Khớp template = TỰ QUA cổng review. Cổng review canh CẤU TRÚC chưa có người xem;
template là cấu trúc đã được xem lúc curate (code + PR + test fixture), nên bắt mỗi
DN bấm xác nhận lại là bắt họ review lại đúng thứ mình đã review, không thêm được
kiểm tra nào cổng thực sự làm. Rủi ro chấp nhận: một template curate SAI sẽ áp im
lặng trên diện rộng — chặn bằng ba lớp: test fixture cho từng template, badge
"Khớp mẫu: <tên>" luôn hiển thị, và map officer per-DN rank CAO HƠN nên vẫn thắng.

**Tầng này sống trong CODE, đổi qua PR.** ADR #23 đã chốt yêu cầu tương lai: quản
lý template qua UI (bảng DB seed từ code). CHƯA build.

Vân tay tính từ vùng tiêu đề (`app.adapters.form_signature`) — chỉ cấu trúc cột,
không chứa mã số thuế, tên DN hay số liệu, nên hằng số dưới đây an toàn để commit.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from app.adapters.evidence import BUILTIN_TEMPLATE, POSITION_ONLY

# Nguồn khớp ghi vào `data_files.match_source`.
MATCH_BUILTIN = "builtin-template"
MATCH_OFFICER = "officer-map"
MATCH_KEYWORD = "keyword"
MATCH_DEFAULT = "default"

MATCH_LABEL_VI = {
    MATCH_BUILTIN: "Khớp mẫu",
    MATCH_OFFICER: "Map đã xác nhận",
    MATCH_KEYWORD: "Dò từ khoá",
    MATCH_DEFAULT: "Mặc định (cột cố định)",
}


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


def resolve_template_evidence(
    template: BuiltinTemplate | None,
    evidence_fields: tuple[str, ...],
    column_map: dict[str, int],
    form_sig: str,
    fallback: Callable[[], dict[str, str]],
) -> tuple[dict[str, str], dict]:
    """`(evidence, provenance detail)` cho đường parse chuẩn của một slot.

    Khớp template → mọi cột mang nguồn `builtin-template` (rank giữa khớp-tiêu-đề và
    map-cán-bộ) nên cổng review tự qua. Không khớp → giữ nguyên đường cũ (dò từ khoá
    rồi cổng review), và `match_source` nói rõ đang đọc bằng gì — không đường nào
    parse im lặng.
    """
    if template is not None:
        evidence = {f: BUILTIN_TEMPLATE for f in evidence_fields if f in column_map}
        detail = {
            "form_signature": form_sig,
            "column_map": {f: column_map[f] for f in evidence},
            "template_id": template.id,
            "template_name": template.name,
            "match_source": MATCH_BUILTIN,
        }
        return evidence, detail

    evidence = fallback()
    matched = any(src != POSITION_ONLY for src in evidence.values())
    return evidence, {
        "form_signature": form_sig,
        "column_map": {f: column_map[f] for f in evidence if f in column_map},
        "template_id": None,
        "match_source": MATCH_KEYWORD if matched else MATCH_DEFAULT,
    }


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
    "MATCH_KEYWORD",
    "MATCH_LABEL_VI",
    "MATCH_OFFICER",
    "BuiltinTemplate",
    "match_template",
    "resolve_template_evidence",
    "template_by_id",
]
