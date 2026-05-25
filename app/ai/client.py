"""OpenAI SDK client factory — dùng DB settings.

Mọi request mới gọi `make_client()` để pick up settings cập nhật (cache 30s).
"""

from __future__ import annotations

from openai import OpenAI

from app.ai.config import get_setting


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


def cache_supports_anthropic(base_url: str | None = None) -> bool:
    """Provider có hỗ trợ Anthropic-style cache_control hay không.

    OpenRouter route đến Anthropic và Anthropic OpenAI-compat endpoint đều hỗ trợ.
    OpenAI vanilla + most other providers → không, silent skip.
    """
    if base_url is None:
        base_url = get_setting("base_url")
    return any(p in base_url for p in ("openrouter.ai", "anthropic.com"))
