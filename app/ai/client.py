"""OpenAI SDK client factory + fallback chain.

Mỗi request mới gọi `make_client()` để pick up settings cập nhật (cache 30s).
Khi `fallback_enabled=True`, `call_with_fallback` thử primary, nếu gặp 429/5xx/
connection error → retry với fallback client.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from openai import (
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
    OpenAI,
    RateLimitError,
)

from app.ai.config import get_setting

log = logging.getLogger(__name__)

ModelSlot = Literal["default", "fast", "deep"]


def make_client() -> OpenAI:
    base_url = get_setting("base_url")
    api_key = get_setting("api_key")
    extra_headers = get_setting("extra_headers") or {}
    timeout = float(get_setting("request_timeout_s"))

    return OpenAI(
        base_url=base_url,
        api_key=api_key,
        timeout=timeout,
        default_headers=extra_headers or None,
    )


def make_fallback_client() -> OpenAI | None:
    """Trả OpenAI client cho provider fallback, hoặc None nếu disabled / chưa cấu hình."""
    if not bool(get_setting("fallback_enabled")):
        return None
    base_url = get_setting("fallback_base_url")
    api_key = get_setting("fallback_api_key")
    if not base_url or not api_key:
        return None
    timeout = float(get_setting("request_timeout_s"))
    return OpenAI(base_url=base_url, api_key=api_key, timeout=timeout)


def fallback_model_for(slot: ModelSlot) -> str | None:
    """Tên model fallback cho 1 slot ('default'|'fast'|'deep')."""
    if not bool(get_setting("fallback_enabled")):
        return None
    key = f"fallback_model_{slot}"
    return get_setting(key) or None


def cache_supports_anthropic(base_url: str | None = None) -> bool:
    """Provider có hỗ trợ Anthropic-style cache_control hay không.

    OpenRouter route đến Anthropic và Anthropic OpenAI-compat endpoint đều hỗ trợ.
    OpenAI vanilla + most other providers → không, silent skip.
    """
    if base_url is None:
        base_url = get_setting("base_url")
    return any(p in base_url for p in ("openrouter.ai", "anthropic.com"))


# ─────────────────────────── Fallback logic ───────────────────────────

# Status codes worth retrying on a different provider.
# 402: out of credits / payment required — fallback provider has independent billing.
# 429: rate limit / quota — different provider has independent quota.
# 5xx: provider outage.
# 404: model not on this provider (e.g. switched provider but model name stale).
# 408/424: timeout-ish.
_RETRY_STATUSES = {402, 404, 408, 424, 429, 500, 502, 503, 504}


def should_fallback(exc: BaseException) -> bool:
    """True nếu loại lỗi này đáng retry trên provider phụ.

    Không fallback khi: 400 (bad request), 401/403 (auth) — vấn đề config,
    đổi provider không giúp.
    """
    if isinstance(exc, (APIConnectionError, APITimeoutError)):
        return True
    if isinstance(exc, RateLimitError):
        return True
    if isinstance(exc, APIStatusError):
        return exc.status_code in _RETRY_STATUSES
    # Generic APIError catch-all: only if it has a status_code attr in retry set.
    if isinstance(exc, APIError):
        code = getattr(exc, "status_code", None)
        return code in _RETRY_STATUSES if code else False
    return False


def call_with_fallback(
    *,
    primary_client: OpenAI,
    primary_model: str,
    fallback_client: OpenAI | None,
    fallback_model: str | None,
    messages: list[dict[str, Any]],
    temperature: float,
    max_tokens: int,
    return_model: bool = False,
    **kwargs: Any,
) -> Any:
    """Gọi chat.completions.create với fallback chain.

    Forward toàn bộ `kwargs` (tools, stream, stream_options...) vào cả 2 lần gọi.

    Mặc định trả về response (backward-compat). Với `return_model=True` trả về
    tuple `(response, model_used)` để caller ghi audit chính xác provider nào
    thực sự trả lời.
    """
    try:
        resp = primary_client.chat.completions.create(
            model=primary_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )
        return (resp, primary_model) if return_model else resp
    except Exception as exc:  # noqa: BLE001 — re-raise unless we choose fallback
        if not should_fallback(exc):
            raise
        if fallback_client is None or not fallback_model:
            raise
        log.warning(
            "Primary LLM failed (%s); falling back to %s",
            type(exc).__name__, fallback_model,
        )
        resp = fallback_client.chat.completions.create(
            model=fallback_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )
        return (resp, fallback_model) if return_model else resp
