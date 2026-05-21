"""UOM resolution helpers — chuẩn hoá đơn vị tính qua DB (canonical + alias).

Logic so sánh 2 đơn vị (cho C3.3):
- EQUIVALENT: cùng canonical_code (alias OK) → skip rule.
- SAME_FAMILY: khác canonical, cùng family (convertible) → INFO.
- DIFFERENT: khác family → CRITICAL.

Cache canonical/alias in-memory cho hot path (run_checks chạy nhiều mã).
Cache invalidate khi admin sửa qua route /admin/units.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import UomAlias, UomCanonical


class UomMatch(StrEnum):
    EQUIVALENT = "equivalent"   # cùng canonical → không fire
    SAME_FAMILY = "same_family" # cùng family, khác canonical → INFO
    DIFFERENT = "different"      # khác family hoặc unknown → CRITICAL


@dataclass
class _UomCache:
    aliases: dict[str, str]            # raw_upper → canonical_code
    canonical: dict[str, UomCanonical]  # code → row


_cache: _UomCache | None = None
_lock = threading.Lock()


def _load_cache(session: Session) -> _UomCache:
    aliases = {
        a.alias.strip().upper(): a.canonical_code
        for a in session.scalars(select(UomAlias)).all()
    }
    canonical = {c.code: c for c in session.scalars(select(UomCanonical)).all()}
    # Mỗi canonical code cũng là alias của chính nó.
    for code in canonical:
        aliases.setdefault(code.upper(), code)
    return _UomCache(aliases=aliases, canonical=canonical)


def get_cache(session: Session) -> _UomCache:
    global _cache
    if _cache is None:
        with _lock:
            if _cache is None:
                _cache = _load_cache(session)
    return _cache


def invalidate_cache() -> None:
    """Gọi sau khi admin sửa canonical/alias qua route."""
    global _cache
    with _lock:
        _cache = None


def normalize(unit: str | None) -> str | None:
    if not unit:
        return None
    return unit.strip().upper()


def resolve_canonical(session: Session, unit: str | None) -> str | None:
    """Tìm canonical code từ raw unit. Trả None nếu không match."""
    norm = normalize(unit)
    if norm is None:
        return None
    return get_cache(session).aliases.get(norm)


def get_family(session: Session, unit: str | None) -> str | None:
    """Trả family ('mass', 'length', ...) hoặc None nếu không resolve được."""
    code = resolve_canonical(session, unit)
    if code is None:
        return None
    row = get_cache(session).canonical.get(code)
    return row.family if row else None


def compare(session: Session, unit_a: str | None, unit_b: str | None) -> UomMatch:
    """Trả mức độ tương đương của 2 đơn vị (ladder cho C3.3 severity)."""
    a_norm = normalize(unit_a)
    b_norm = normalize(unit_b)
    if a_norm == b_norm:
        return UomMatch.EQUIVALENT

    cache = get_cache(session)
    canon_a = cache.aliases.get(a_norm) if a_norm else None
    canon_b = cache.aliases.get(b_norm) if b_norm else None

    if canon_a and canon_b:
        if canon_a == canon_b:
            return UomMatch.EQUIVALENT
        fam_a = cache.canonical.get(canon_a).family if cache.canonical.get(canon_a) else None
        fam_b = cache.canonical.get(canon_b).family if cache.canonical.get(canon_b) else None
        if fam_a is not None and fam_a == fam_b:
            return UomMatch.SAME_FAMILY
        return UomMatch.DIFFERENT

    # 1 trong 2 unit unknown — chỉ raw compare đã làm trên.
    return UomMatch.DIFFERENT
