"""Kho map cột đã xác nhận + resolve `officer-confirmed` (WS1-3, ADR #18).

- ``save_column_map`` — upsert map cho `(DN, slot, vân tay form)` (idempotent theo khoá).
- ``load_column_map`` — nạp map đã lưu (None nếu chưa có).
- ``officer_maps`` — mọi map đã lưu của một DN, gom theo slot rồi theo vân tay, đúng
  hình dạng các adapter nhận để ÁP VỊ TRÍ CỘT lúc đọc file (ADR #24 mục 5).
- ``resolve_officer_confirmed`` — nâng nguồn bằng chứng các cột có map lưu lên
  ``officer-confirmed`` (→ `verified`). Keyed theo `company_id` nên DN khác cùng
  shape KHÔNG kế thừa; vân tay không chứa năm nên CÙNG DN tái dùng chéo năm.

Không hàm nào ở đây tự mở phiên DB — người gọi truyền `Session` vào, để không đọc
trúng DB dev của máy khi chạy test.
"""

from __future__ import annotations

import json
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.evidence import OFFICER_CONFIRMED
from app.adapters.templates import column_groups
from app.models.saved_column_map import SavedColumnMap


def load_column_map(
    session: Session, company_id: int, slot: str, form_signature: str
) -> SavedColumnMap | None:
    """Map đã lưu cho `(DN, slot, vân tay)`; None nếu chưa xác nhận."""
    return session.scalar(
        select(SavedColumnMap).where(
            SavedColumnMap.company_id == company_id,
            SavedColumnMap.slot == slot,
            SavedColumnMap.form_signature == form_signature,
        )
    )


def _reject_overlap(
    column_map: dict[str, int | list[int]], absent_fields: list[str] | None,
) -> list[str] | None:
    """`column_map` ∩ `absent_fields` = ∅. Giao khác rỗng là mâu thuẫn, không phải ưu tiên.

    Một trường vừa "đọc ở cột 5" vừa "không có trong file" thì không có cách đọc nào
    đúng cả hai, và đoán một bên là quay lại đúng lớp lỗi đọc sai im lặng. Từ chối.
    """
    if absent_fields is None:
        return None
    absent = sorted(set(absent_fields))
    clash = sorted(set(absent) & set(column_map))
    if clash:
        raise ValueError(
            f"Trường {', '.join(clash)} vừa được gán cột vừa bị đánh dấu không có "
            "trong file. Một trường chỉ ở đúng một trạng thái."
        )
    return absent


def save_column_map(
    session: Session,
    company_id: int,
    slot: str,
    form_signature: str,
    column_map: dict[str, int | list[int]],
    evidence: dict[str, str] | None = None,
    confirmed_by: int | None = None,
    absent_fields: list[str] | None = None,
) -> SavedColumnMap:
    """Upsert map cột cho `(DN, slot, vân tay)`. Idempotent: khoá đã có → ghi đè map.

    Giá trị mỗi trường là `int` (một cột) hoặc `list[int]` (một trường đọc bằng TỔNG
    nhiều cột con — bố cục mở rộng, #95). Không commit — người gọi quyết định ranh
    giới transaction.

    `absent_fields` = trường cán bộ XÁC NHẬN không có trong file (#112). Bất biến hai
    tập rời nhau được khẳng định ở ĐÂY và chỉ ở đây — mọi đường ghi map đều đi qua hàm
    này, nên không có chỗ thứ hai để hai tập lệch nhau.
    """
    absent = _reject_overlap(column_map, absent_fields)
    row = load_column_map(session, company_id, slot, form_signature)
    col_json = json.dumps(column_map, ensure_ascii=False)
    ev_json = json.dumps(evidence, ensure_ascii=False) if evidence is not None else None
    absent_json = json.dumps(absent, ensure_ascii=False) if absent is not None else None
    if row is None:
        row = SavedColumnMap(
            company_id=company_id,
            slot=slot,
            form_signature=form_signature,
            column_map=col_json,
            evidence=ev_json,
            confirmed_by=confirmed_by,
            absent_fields=absent_json,
        )
        session.add(row)
    else:
        row.column_map = col_json
        row.evidence = ev_json
        row.confirmed_by = confirmed_by
        row.absent_fields = absent_json
    # Flush để lần upsert kế trong CÙNG transaction thấy dòng vừa thêm (session
    # autoflush=False) — giữ idempotent theo khoá mà không commit.
    session.flush()
    return row


def absent_fields_for(
    session: Session, company_id: int, slot: str, form_signature: str | None,
) -> list[str]:
    """Trường cán bộ đã xác nhận VẮNG cho `(DN, slot, vân tay)`. Rỗng nếu chưa ai nói gì."""
    if not form_signature:
        return []
    row = load_column_map(session, company_id, slot, form_signature)
    return row.absent_fields_obj if row is not None else []


def officer_maps(session: Session, company_id: int) -> dict[str, dict[str, dict[str, list[int]]]]:
    """`{slot: {vân tay: {field: [chỉ số cột…]}}}` — map cán bộ đã xác nhận của một DN.

    Đúng hình dạng tham số `officer_maps` của các adapter: parser tính vân tay lúc
    mở file rồi tra thẳng, nên không phải mở file hai lần chỉ để biết tra khoá nào.
    Chuẩn hoá về NHÓM cột ngay ở đây: map cũ trong DB lưu một `int` mỗi trường, map
    của bố cục mở rộng lưu danh sách — người đọc chỉ nên gặp một hình dạng.
    """
    out: dict[str, dict[str, dict[str, list[int]]]] = defaultdict(dict)
    rows = session.scalars(
        select(SavedColumnMap).where(SavedColumnMap.company_id == company_id)
    ).all()
    for row in rows:
        out[row.slot][row.form_signature] = column_groups(row.column_map_obj)
    return dict(out)


def resolve_officer_confirmed(
    session: Session,
    company_id: int,
    slot: str,
    form_signature: str | None,
    evidence: dict[str, str],
    applied_columns: dict[str, int | list[int]] | None = None,
) -> dict[str, str]:
    """Trả bản sao `evidence` với các cột có map lưu nâng lên ``officer-confirmed``.

    Không có vân tay hoặc không có map lưu → trả nguyên (bản sao). Chỉ nâng field
    vừa nằm trong map lưu vừa có trong evidence hiện tại (map khớp ⇒ cùng bố cục).

    ``applied_columns`` là map cột lượt đọc THẬT SỰ đã dùng. Truyền vào thì chỉ nâng
    field mà vị trí đã đọc ĐÚNG bằng vị trí trong map lưu — dán nhãn "cán bộ xác nhận"
    lên một cột đọc theo vị trí khác là nói sai với người đọc badge. So sánh theo NHÓM
    cột đã chuẩn hoá: map cũ lưu `5`, lượt đọc ghi `[5]`, hai cái đó là một.
    """
    resolved = dict(evidence)
    if not form_signature:
        return resolved
    saved = load_column_map(session, company_id, slot, form_signature)
    if saved is None:
        return resolved
    applied = column_groups(applied_columns) if applied_columns is not None else None
    for field, cols in column_groups(saved.column_map_obj).items():
        if field not in resolved:
            continue
        if applied is not None and applied.get(field) != cols:
            continue
        resolved[field] = OFFICER_CONFIRMED
    return resolved


__all__ = [
    "absent_fields_for",
    "load_column_map",
    "officer_maps",
    "resolve_officer_confirmed",
    "save_column_map",
]
