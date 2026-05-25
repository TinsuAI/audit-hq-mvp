"""AI assistant config — DB-backed settings + helpers.

Admin sửa qua /admin/ai, không cần redeploy. Env vars chỉ làm default lần đầu
khi bảng `ai_settings` trống (seed_defaults).

Cache: process-level dict với TTL 30s. `set_setting` bust toàn cache.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import AiSetting

# ---------- Setting registry ----------

# Mỗi key: (type, default, description, is_secret).
# `type` quyết định cách (de)serialize. `is_secret` → mask khi expose qua API.
@dataclass(frozen=True)
class SettingSpec:
    type: type
    default: Any
    description: str
    is_secret: bool = False


SETTINGS_REGISTRY: dict[str, SettingSpec] = {
    # Master switch & connection
    "enabled": SettingSpec(bool, False, "Bật/tắt AI assistant toàn cục"),
    "base_url": SettingSpec(
        str, "https://openrouter.ai/api/v1",
        "OpenAI-compatible API endpoint (vd OpenRouter / OpenAI / Anthropic compat)"
    ),
    "api_key": SettingSpec(str, "", "API key cho provider", is_secret=True),
    "extra_headers": SettingSpec(
        dict,
        {"HTTP-Referer": "https://audit-hq-demo.tinsu.ai", "X-Title": "Audit-HQ"},
        "Headers thêm khi gọi API (vd OpenRouter ranking)"
    ),
    # Models
    "model_default": SettingSpec(str, "anthropic/claude-sonnet-4", "Model chính cho chat"),
    "model_fast": SettingSpec(str, "anthropic/claude-haiku-4-5", "Model rẻ cho summarize/explain"),
    "model_deep": SettingSpec(str, "anthropic/claude-opus-4-7", "Model reasoning sâu (gated)"),
    "temperature": SettingSpec(float, 0.2, "Sampling temperature 0-2"),
    "max_tokens": SettingSpec(int, 1024, "Tokens tối đa mỗi response"),
    # Limits & retention
    "request_timeout_s": SettingSpec(int, 60, "Timeout 1 API call"),
    "daily_budget_usd": SettingSpec(float, 20.0, "Hard cap chi phí AI/ngày"),
    "rate_limit_per_hour": SettingSpec(int, 50, "Số message tối đa/user/giờ"),
    "history_retention_days": SettingSpec(int, 30, "Giữ conversation cũ"),
    "audit_retention_days": SettingSpec(int, 365, "Giữ audit log"),
    # Flags
    "prompt_cache_enabled": SettingSpec(bool, True, "Bật prompt caching khi provider hỗ trợ"),
}

# Env var prefix dùng cho seed lần đầu.
ENV_PREFIX = "AI_"


# ---------- Cache ----------

_CACHE: dict[str, tuple[float, Any]] = {}
_TTL_S = 30.0


def _cache_get(key: str) -> Any | None:
    entry = _CACHE.get(key)
    if entry is None:
        return None
    expires_at, value = entry
    if time.time() > expires_at:
        _CACHE.pop(key, None)
        return None
    return value


def _cache_set(key: str, value: Any) -> None:
    _CACHE[key] = (time.time() + _TTL_S, value)


def bust_cache() -> None:
    """Xoá toàn bộ cache — gọi sau khi set_setting hoặc seed_defaults."""
    _CACHE.clear()
    _bust_models_cache()


# Models list cache riêng (TTL dài hơn settings vì ít đổi).
_MODELS_CACHE: tuple[float, list[str]] | None = None
_MODELS_TTL_S = 300.0  # 5 phút


def _bust_models_cache() -> None:
    global _MODELS_CACHE
    _MODELS_CACHE = None


def get_available_models(refresh: bool = False) -> list[str] | None:
    """Fetch danh sách model từ {base_url}/models. None nếu lỗi (key sai, network...).

    Cache 5 phút. `refresh=True` để force fetch lại (vd sau khi đổi key).
    """
    global _MODELS_CACHE
    if not refresh and _MODELS_CACHE is not None:
        expires_at, models = _MODELS_CACHE
        if time.time() < expires_at:
            return models
    result = test_connection(timeout_s=8)
    if not result.ok or result.models is None:
        return None
    _MODELS_CACHE = (time.time() + _MODELS_TTL_S, result.models)
    return result.models


# ---------- (De)serialization ----------

def _serialize(value: Any, spec: SettingSpec) -> str:
    if spec.type is bool:
        return "true" if bool(value) else "false"
    if spec.type in (int, float):
        return str(spec.type(value))
    if spec.type is str:
        return str(value)
    if spec.type is dict:
        return json.dumps(value, ensure_ascii=False)
    raise ValueError(f"Unknown setting type: {spec.type}")


def _deserialize(raw: str, spec: SettingSpec) -> Any:
    if spec.type is bool:
        return raw.lower() in ("true", "1", "yes", "on")
    if spec.type is int:
        return int(raw) if raw else spec.default
    if spec.type is float:
        return float(raw) if raw else spec.default
    if spec.type is str:
        return raw
    if spec.type is dict:
        if not raw:
            return spec.default
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return spec.default
    raise ValueError(f"Unknown setting type: {spec.type}")


# ---------- Public API ----------

def get_setting(key: str, db: Session | None = None) -> Any:
    """Đọc 1 setting. Trả về typed value, fallback default từ registry."""
    spec = SETTINGS_REGISTRY.get(key)
    if spec is None:
        raise KeyError(f"Unknown setting key: {key}")

    cached = _cache_get(key)
    if cached is not None:
        return cached

    own = db is None
    s = db or SessionLocal()
    try:
        row = s.scalar(select(AiSetting).where(AiSetting.key == key))
        value = _deserialize(row.value, spec) if row is not None else spec.default
        _cache_set(key, value)
        return value
    finally:
        if own:
            s.close()


def set_setting(key: str, value: Any, user: str, db: Session | None = None) -> None:
    """Ghi 1 setting. Bust cache toàn process."""
    spec = SETTINGS_REGISTRY.get(key)
    if spec is None:
        raise KeyError(f"Unknown setting key: {key}")

    serialized = _serialize(value, spec)
    own = db is None
    s = db or SessionLocal()
    try:
        row = s.scalar(select(AiSetting).where(AiSetting.key == key))
        if row is None:
            row = AiSetting(key=key, value=serialized, updated_by=user)
            s.add(row)
        else:
            row.value = serialized
            row.updated_by = user
            # updated_at: dùng server_default; set explicit khi cần audit chính xác.
        s.commit()
    finally:
        if own:
            s.close()
    bust_cache()


def _mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "•" * len(value)
    return f"{value[:4]}•••••{value[-4:]}"


def get_all_settings(db: Session | None = None) -> dict[str, dict[str, Any]]:
    """Trả về toàn bộ settings cho admin UI. Mask secret keys.

    Mỗi key → {value, description, is_secret, type}.
    Secret value đổi thành masked string + thêm `has_value: bool` để UI biết.
    """
    result: dict[str, dict[str, Any]] = {}
    for key, spec in SETTINGS_REGISTRY.items():
        raw_value = get_setting(key, db=db)
        entry: dict[str, Any] = {
            "description": spec.description,
            "is_secret": spec.is_secret,
            "type": spec.type.__name__,
        }
        if spec.is_secret:
            entry["value"] = _mask_secret(str(raw_value))
            entry["has_value"] = bool(raw_value)
        else:
            entry["value"] = raw_value
        result[key] = entry
    return result


def seed_defaults(db: Session | None = None) -> int:
    """Seed default settings khi bảng trống. Idempotent.

    Override default bằng env var `AI_<KEY_UPPER>` nếu có (1-time, chỉ khi seed).
    Trả về số dòng được insert.
    """
    own = db is None
    s = db or SessionLocal()
    inserted = 0
    try:
        existing = {row.key for row in s.scalars(select(AiSetting)).all()}
        for key, spec in SETTINGS_REGISTRY.items():
            if key in existing:
                continue
            # Check env override
            env_key = f"{ENV_PREFIX}{key.upper()}"
            env_value = os.environ.get(env_key)
            if env_value is not None:
                try:
                    if spec.type is bool:
                        value: Any = env_value.lower() in ("true", "1", "yes", "on")
                    elif spec.type is int:
                        value = int(env_value)
                    elif spec.type is float:
                        value = float(env_value)
                    elif spec.type is dict:
                        value = json.loads(env_value)
                    else:
                        value = env_value
                except (ValueError, json.JSONDecodeError):
                    value = spec.default
            else:
                value = spec.default
            s.add(AiSetting(
                key=key, value=_serialize(value, spec), updated_by="seed"
            ))
            inserted += 1
        if inserted:
            s.commit()
    finally:
        if own:
            s.close()
    if inserted:
        bust_cache()
    return inserted


# ---------- Test connection ----------

@dataclass
class ConnectionTestResult:
    ok: bool
    error: str | None = None
    models: list[str] | None = None
    latency_ms: int | None = None


def test_connection(
    base_url: str | None = None,
    api_key: str | None = None,
    extra_headers: dict[str, str] | None = None,
    timeout_s: int = 10,
) -> ConnectionTestResult:
    """Ping {base_url}/models để verify config trước khi save.

    Nếu không truyền tham số → dùng setting hiện tại trong DB.
    """
    if base_url is None:
        base_url = get_setting("base_url")
    if api_key is None:
        api_key = get_setting("api_key")
    if extra_headers is None:
        extra_headers = get_setting("extra_headers")

    if not api_key:
        return ConnectionTestResult(ok=False, error="API key chưa cấu hình")

    url = f"{base_url.rstrip('/')}/models"
    headers = {"Authorization": f"Bearer {api_key}", **(extra_headers or {})}
    t0 = time.time()
    try:
        r = httpx.get(url, headers=headers, timeout=timeout_s)
        latency = int((time.time() - t0) * 1000)
        if r.status_code != 200:
            return ConnectionTestResult(
                ok=False,
                error=f"HTTP {r.status_code}: {r.text[:200]}",
                latency_ms=latency,
            )
        payload = r.json()
        # OpenAI format: {"data": [{"id": "..."}, ...]}
        models_list = payload.get("data", []) if isinstance(payload, dict) else []
        ids = [m.get("id") for m in models_list if m.get("id")]
        return ConnectionTestResult(ok=True, models=ids[:50], latency_ms=latency)
    except httpx.HTTPError as e:
        return ConnectionTestResult(
            ok=False, error=f"{type(e).__name__}: {e}", latency_ms=int((time.time() - t0) * 1000)
        )
