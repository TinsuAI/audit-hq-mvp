"""UOM resolution helpers — chuẩn hoá đơn vị tính qua DB (canonical + alias).

Logic so sánh 2 đơn vị (cho C3.3):
- EQUIVALENT: cùng canonical_code (alias OK) → skip rule.
- SAME_FAMILY: khác canonical, cùng family (convertible) → INFO.
- UNRESOLVED: ít nhất một vế không tra được → chưa kết luận được (#115).
- DIFFERENT: cả hai vế tra được VÀ khác family → CRITICAL.

UNRESOLVED tách khỏi DIFFERENT vì hai câu khác nhau: "đã đo và thấy lệch" so với
"không tra được nên chưa đo". Gộp lại thì mọi chuỗi đơn vị thiếu trong bảng bí danh
ra Nghiêm trọng như thể đã chứng minh sai (#115: 53/148 phát hiện C3.3 thuộc ca này).

Cache canonical/alias in-memory cho hot path (run_checks chạy nhiều mã).
Cache invalidate khi admin sửa qua route /admin/units.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import UomAlias, UomCanonical

# Separator chars dùng trong text đơn vị tính của user (Cái/Chiếc, KG, GAM...).
_SEP_RE = re.compile(r"[/,;|]+")


class UomMatch(StrEnum):
    EQUIVALENT = "equivalent"    # cùng canonical → không fire
    SAME_FAMILY = "same_family"  # cùng family, khác canonical → INFO
    UNRESOLVED = "unresolved"    # ≥1 vế không tra được → chưa kết luận (#115)
    DIFFERENT = "different"      # cả hai tra được, khác family → CRITICAL


@dataclass
class _UomCache:
    aliases: dict[str, str]    # raw_upper → canonical_code
    families: dict[str, str]   # canonical_code → family


_cache: _UomCache | None = None
_lock = threading.Lock()


def _load_cache(session: Session) -> _UomCache:
    aliases = {
        a.alias.strip().upper(): a.canonical_code
        for a in session.scalars(select(UomAlias)).all()
    }
    families = {
        c.code: c.family
        for c in session.scalars(select(UomCanonical)).all()
    }
    # Mỗi canonical code cũng là alias của chính nó.
    for code in families:
        aliases.setdefault(code.upper(), code)
    return _UomCache(aliases=aliases, families=families)


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


def resolve_code_set(session: Session, unit: str | None) -> set[str]:
    """Tập canonical mà chuỗi này CÓ THỂ mang. Rỗng = không tra được phần nào.

    Một phần tử = chốt được. Nhiều phần tử = chuỗi ghép mà các phần trỏ những
    canonical khác nhau (`Kiện/Hộp/Bao/Gói` → BOX lẫn PKG). Ba hàm dưới đây đều
    suy từ tập này, để chúng không bao giờ trả lời lệch nhau.
    """
    norm = normalize(unit)
    if norm is None:
        return set()
    cache = get_cache(session)
    # Direct alias hit.
    direct = cache.aliases.get(norm)
    if direct is not None:
        return {direct}
    # Compound text với separator: split → match từng phần.
    if not _SEP_RE.search(norm):
        return set()
    parts = [p.strip() for p in _SEP_RE.split(norm) if p.strip()]
    return {code for code in (cache.aliases.get(p) for p in parts) if code is not None}


def resolve_canonical(session: Session, unit: str | None) -> str | None:
    """Tìm canonical code từ raw unit. Trả None nếu không match.

    Hỗ trợ compound unit text với separator (vd "Cái/Chiếc", "KG, GAM"):
    nếu split ra mà mọi phần tra được đều về cùng canonical → trả canonical đó.
    Các phần trỏ hai canonical khác nhau → None (nhập nhằng, xem `resolve_families`).
    """
    codes = resolve_code_set(session, unit)
    if len(codes) == 1:
        return next(iter(codes))
    return None


def get_family(session: Session, unit: str | None) -> str | None:
    """Trả family ('mass', 'length', ...) hoặc None nếu không resolve được."""
    code = resolve_canonical(session, unit)
    if code is None:
        return None
    return get_cache(session).families.get(code)


def resolve_families(session: Session, unit: str | None) -> set[str]:
    """Tập họ đơn vị mà chuỗi này CÓ THỂ mang. Rỗng = không tra được phần nào.

    Chốt được canonical thì tập có đúng một họ. Không chốt được thì vẫn còn biết
    được HỌ — đủ để kết luận lệch với một đơn vị khối lượng, mà không phải giả vờ
    đã chốt được canonical.
    """
    cache = get_cache(session)
    return {
        cache.families[code]
        for code in resolve_code_set(session, unit)
        if code in cache.families
    }


def compare(session: Session, unit_a: str | None, unit_b: str | None) -> UomMatch:
    """Trả mức độ tương đương của 2 đơn vị (ladder cho C3.3 severity)."""
    a_norm = normalize(unit_a)
    b_norm = normalize(unit_b)
    if a_norm == b_norm:
        return UomMatch.EQUIVALENT

    # Dùng resolve_canonical (hỗ trợ separator split) thay vì lookup trực tiếp.
    canon_a = resolve_canonical(session, unit_a)
    canon_b = resolve_canonical(session, unit_b)

    # Không chốt được canonical thì lùi một bậc: so theo HỌ đơn vị. Chuỗi ghép nhập
    # nhằng canonical (`Kiện/Hộp/Bao/Gói` → BOX lẫn PKG) vẫn nói rõ đây là đơn vị
    # đóng gói, đủ để kết luận lệch với khối lượng. Chỉ khi không tra được phần nào
    # mới là chưa biết — trả UNRESOLVED chứ không hạ xuống DIFFERENT.
    if canon_a is None or canon_b is None:
        fams_a = resolve_families(session, unit_a)
        fams_b = resolve_families(session, unit_b)
        if not fams_a or not fams_b:
            return UomMatch.UNRESOLVED
        if fams_a & fams_b:
            # Hai chuỗi cùng tập canonical là cùng một điều, chỉ khác thứ tự chữ
            # ("Hộp/Gói" vs "Gói/Hộp"). Ngoài ra chỉ dám kết luận tới mức cùng họ.
            if resolve_code_set(session, unit_a) == resolve_code_set(session, unit_b):
                return UomMatch.EQUIVALENT
            return UomMatch.SAME_FAMILY
        return UomMatch.DIFFERENT

    if canon_a == canon_b:
        return UomMatch.EQUIVALENT
    cache = get_cache(session)
    fam_a = cache.families.get(canon_a)
    fam_b = cache.families.get(canon_b)
    if fam_a is not None and fam_a == fam_b:
        return UomMatch.SAME_FAMILY
    return UomMatch.DIFFERENT
