"""Kho map cột đã xác nhận + resolve `officer-confirmed` (WS1-3, ADR #18).

- ``save_column_map`` — upsert map cho `(DN, slot, vân tay form)` (idempotent theo khoá).
- ``load_column_map`` — nạp map đã lưu (None nếu chưa có).
- ``resolve_officer_confirmed`` — nâng nguồn bằng chứng các cột có map lưu lên
  ``officer-confirmed`` (→ `verified`). Keyed theo `company_id` nên DN khác cùng
  shape KHÔNG kế thừa; vân tay không chứa năm nên CÙNG DN tái dùng chéo năm.
"""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.evidence import OFFICER_CONFIRMED
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


def save_column_map(
    session: Session,
    company_id: int,
    slot: str,
    form_signature: str,
    column_map: dict[str, int],
    evidence: dict[str, str] | None = None,
    confirmed_by: int | None = None,
) -> SavedColumnMap:
    """Upsert map cột cho `(DN, slot, vân tay)`. Idempotent: khoá đã có → ghi đè map.

    Không commit — người gọi quyết định ranh giới transaction.
    """
    row = load_column_map(session, company_id, slot, form_signature)
    col_json = json.dumps(column_map, ensure_ascii=False)
    ev_json = json.dumps(evidence, ensure_ascii=False) if evidence is not None else None
    if row is None:
        row = SavedColumnMap(
            company_id=company_id,
            slot=slot,
            form_signature=form_signature,
            column_map=col_json,
            evidence=ev_json,
            confirmed_by=confirmed_by,
        )
        session.add(row)
    else:
        row.column_map = col_json
        row.evidence = ev_json
        row.confirmed_by = confirmed_by
    # Flush để lần upsert kế trong CÙNG transaction thấy dòng vừa thêm (session
    # autoflush=False) — giữ idempotent theo khoá mà không commit.
    session.flush()
    return row


def resolve_officer_confirmed(
    session: Session,
    company_id: int,
    slot: str,
    form_signature: str | None,
    evidence: dict[str, str],
) -> dict[str, str]:
    """Trả bản sao `evidence` với các cột có map lưu nâng lên ``officer-confirmed``.

    Không có vân tay hoặc không có map lưu → trả nguyên (bản sao). Chỉ nâng field
    vừa nằm trong map lưu vừa có trong evidence hiện tại (map khớp ⇒ cùng bố cục).
    """
    resolved = dict(evidence)
    if not form_signature:
        return resolved
    saved = load_column_map(session, company_id, slot, form_signature)
    if saved is None:
        return resolved
    for field in saved.column_map_obj:
        if field in resolved:
            resolved[field] = OFFICER_CONFIRMED
    return resolved


__all__ = ["load_column_map", "resolve_officer_confirmed", "save_column_map"]
