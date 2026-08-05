"""Helper đọc/ghi `app_settings` — cấu hình runtime của admin.

Cache 30s (process-local) để tránh hit DB mỗi request. Ghi gọi `invalidate_cache()`
để lần read kế TRONG CÙNG process đọc lại DB ngay. Deploy pilot chạy 1 process +
worker cùng process → cache dùng chung, flip toggle áp ngay. Multi-process (uvicorn
--workers >1 / gunicorn): process khác chỉ nhận giá trị mới sau tối đa 30s TTL.
"""

from __future__ import annotations

import json
import time
from threading import Lock

from sqlalchemy.orm import Session

from app.models.app_setting import AppSetting

# --- Ngưỡng hạng rủi ro (5 hạng) ---

# Cận trên (inclusive) cho 5 hạng score 0-1000. Hạng cuối = 1000 luôn.
DEFAULT_RISK_TIER_UPPERS: tuple[int, ...] = (50, 100, 300, 600, 1000)

# Nhãn 5 hạng — giữ tên cũ neutral, không trùng "Mức N" TT 81/2019.
RISK_TIER_LABELS: tuple[str, ...] = (
    "Dữ liệu nhất quán",
    "Có chênh lệch nhỏ",
    "Cần rà soát",
    "Có dấu hiệu bất thường",
    "Bất thường nghiêm trọng",
)

RISK_TIER_CSS: tuple[str, ...] = (
    "tier-green",
    "tier-yellow-green",
    "tier-yellow",
    "tier-orange",
    "tier-red",
)

KEY_RISK_TIER_UPPERS = "risk_tier_uppers"

# --- Combo (D4) toàn cục ---

# Bật/tắt phát hiện kết hợp (§2.7) trên toàn hệ thống. Mặc định TẮT vì 2/4 combo
# neo trên C4.3 đang đổi định nghĩa (số nhân = sản lượng) — bật lại sau khi C4.3
# chốt + revalidate. Xem ADR #18 Revision — WS2.
KEY_COMBOS_ENABLED = "combos_enabled"
DEFAULT_COMBOS_ENABLED = False

# --- Định dạng số trên giao diện ---

# `vi` = 1.234,56 · `en` = 1,234.56. Mặc định `vi` cho khớp UI tiếng Việt; đổi
# được vì bản xuất ECUS và Excel của cán bộ có thể theo quy ước khác.
KEY_NUMBER_FORMAT = "number_format"
DEFAULT_NUMBER_FORMAT = "vi"
NUMBER_FORMAT_LABELS: dict[str, str] = {
    "vi": "Kiểu Việt Nam — 1.234,56",
    "en": "Kiểu Anh/Mỹ — 1,234.56",
}

_CACHE_TTL_SECONDS = 30.0
_cache: dict[str, tuple[float, object]] = {}
_lock = Lock()


def invalidate_cache() -> None:
    with _lock:
        _cache.clear()


def _get_cached(key: str):
    with _lock:
        entry = _cache.get(key)
        if entry and (time.monotonic() - entry[0]) < _CACHE_TTL_SECONDS:
            return entry[1]
    return None


def _put_cached(key: str, value) -> None:
    with _lock:
        _cache[key] = (time.monotonic(), value)


def get_risk_tier_uppers(db: Session | None = None) -> tuple[int, ...]:
    """Đọc 5 cận trên hạng rủi ro. Fallback DEFAULT nếu chưa cấu hình."""
    cached = _get_cached(KEY_RISK_TIER_UPPERS)
    if cached is not None:
        return cached

    own_session = db is None
    if own_session:
        # Late import: tests monkey-patch app.database.SessionLocal sau import.
        from app.database import SessionLocal
        s = SessionLocal()
    else:
        s = db
    try:
        row = s.get(AppSetting, KEY_RISK_TIER_UPPERS)
        if row and row.value:
            try:
                data = json.loads(row.value)
                if isinstance(data, list) and len(data) == 5:
                    uppers = tuple(int(x) for x in data)
                    if _is_valid_uppers(uppers):
                        _put_cached(KEY_RISK_TIER_UPPERS, uppers)
                        return uppers
            except (ValueError, TypeError):
                pass
    finally:
        if own_session:
            s.close()

    _put_cached(KEY_RISK_TIER_UPPERS, DEFAULT_RISK_TIER_UPPERS)
    return DEFAULT_RISK_TIER_UPPERS


def _is_valid_uppers(uppers: tuple[int, ...]) -> bool:
    if len(uppers) != 5:
        return False
    if any(u <= 0 for u in uppers):
        return False
    if uppers[-1] != 1000:
        return False
    for a, b in zip(uppers, uppers[1:], strict=False):
        if a >= b:
            return False
    return True


class ValidationError(ValueError):
    pass


def save_risk_tier_uppers(uppers: list[int], updated_by: str, db: Session) -> None:
    """Validate + lưu. Raise ValidationError nếu sai."""
    if len(uppers) != 5:
        raise ValidationError("Phải có đúng 5 ngưỡng.")
    try:
        normalized = tuple(int(x) for x in uppers)
    except (ValueError, TypeError) as exc:
        raise ValidationError("Ngưỡng phải là số nguyên.") from exc
    if not _is_valid_uppers(normalized):
        raise ValidationError(
            "Ngưỡng phải tăng dần, dương, và ngưỡng cuối = 1000."
        )

    row = db.get(AppSetting, KEY_RISK_TIER_UPPERS)
    payload = json.dumps(list(normalized))
    if row is None:
        db.add(AppSetting(
            key=KEY_RISK_TIER_UPPERS, value=payload, updated_by=updated_by,
        ))
    else:
        row.value = payload
        row.updated_by = updated_by
    db.commit()
    invalidate_cache()


def get_tiers(db: Session | None = None) -> tuple[tuple[int, str, str], ...]:
    """Trả về tuple 5 tuple `(upper, label, css)` cho scoring/template."""
    uppers = get_risk_tier_uppers(db)
    return tuple(
        (u, RISK_TIER_LABELS[i], RISK_TIER_CSS[i])
        for i, u in enumerate(uppers)
    )


def get_combos_enabled(db: Session | None = None) -> bool:
    """Đọc cờ combos_enabled. Fallback DEFAULT_COMBOS_ENABLED nếu chưa cấu hình."""
    cached = _get_cached(KEY_COMBOS_ENABLED)
    if cached is not None:
        return bool(cached)

    own_session = db is None
    if own_session:
        from app.database import SessionLocal
        s = SessionLocal()
    else:
        s = db
    try:
        row = s.get(AppSetting, KEY_COMBOS_ENABLED)
        if row and row.value:
            try:
                value = bool(json.loads(row.value))
                _put_cached(KEY_COMBOS_ENABLED, value)
                return value
            except (ValueError, TypeError):
                pass
    finally:
        if own_session:
            s.close()

    _put_cached(KEY_COMBOS_ENABLED, DEFAULT_COMBOS_ENABLED)
    return DEFAULT_COMBOS_ENABLED


def set_combos_enabled(enabled: bool, updated_by: str, db: Session) -> None:
    """Ghi cờ combos_enabled + bust cache."""
    row = db.get(AppSetting, KEY_COMBOS_ENABLED)
    payload = json.dumps(bool(enabled))
    if row is None:
        db.add(AppSetting(key=KEY_COMBOS_ENABLED, value=payload, updated_by=updated_by))
    else:
        row.value = payload
        row.updated_by = updated_by
    db.commit()
    invalidate_cache()


def get_number_format(db: Session | None = None) -> str:
    """Quy ước phân cách số đang chọn: `vi` hoặc `en`.

    Gọi ở MỌI ô số trên giao diện nên phải rẻ — cache 30s gánh phần đó; giá trị
    lạ trong DB rơi về mặc định thay vì ném lỗi giữa lúc render.
    """
    cached = _get_cached(KEY_NUMBER_FORMAT)
    if cached is not None:
        return str(cached)

    own_session = db is None
    if own_session:
        from app.database import SessionLocal
        s = SessionLocal()
    else:
        s = db
    try:
        row = s.get(AppSetting, KEY_NUMBER_FORMAT)
        if row and row.value in NUMBER_FORMAT_LABELS:
            _put_cached(KEY_NUMBER_FORMAT, row.value)
            return row.value
    finally:
        if own_session:
            s.close()

    _put_cached(KEY_NUMBER_FORMAT, DEFAULT_NUMBER_FORMAT)
    return DEFAULT_NUMBER_FORMAT


def set_number_format(style: str, updated_by: str, db: Session) -> None:
    """Ghi quy ước phân cách số + bust cache. Giá trị ngoài `vi`/`en` bị từ chối."""
    if style not in NUMBER_FORMAT_LABELS:
        raise ValidationError("Quy ước định dạng số không hợp lệ.")
    row = db.get(AppSetting, KEY_NUMBER_FORMAT)
    if row is None:
        db.add(AppSetting(key=KEY_NUMBER_FORMAT, value=style, updated_by=updated_by))
    else:
        row.value = style
        row.updated_by = updated_by
    db.commit()
    invalidate_cache()
