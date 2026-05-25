"""Admin routes — cấu hình AI assistant.

Mỗi section 1 form + 1 POST riêng để save không reload toàn page state.
API key đặc biệt: input password rỗng theo default; submit rỗng = giữ key cũ.
Test connection: endpoint JSON, FE fetch() và render kết quả inline.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.ai.config import (
    SETTINGS_REGISTRY,
    get_all_settings,
    get_available_models,
    get_setting,
    set_setting,
    test_connection,
)
from app.auth import require_user

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")

router = APIRouter(prefix="/admin/ai")


def _group_models_by_provider(models: list[str]) -> list[tuple[str, list[str]]]:
    """Group `provider/model` thành list optgroup → (provider, [model_ids]).

    Provider không có `/` → vào nhóm "khác". Sort theo prefix.
    """
    from collections import defaultdict
    grouped: dict[str, list[str]] = defaultdict(list)
    for m in models:
        # Loại bỏ `~` prefix (OpenRouter alias) khỏi group key nhưng giữ trong value.
        clean = m.lstrip("~")
        provider, _, _ = clean.partition("/")
        provider = provider or "khác"
        grouped[provider].append(m)
    for v in grouped.values():
        v.sort()
    return sorted(grouped.items())


@router.get("", response_class=HTMLResponse)
def admin_ai_page(
    request: Request,
    saved: str | None = Query(default=None),
    error: str | None = Query(default=None),
    refresh_models: int = Query(default=0),
    user: str = Depends(require_user),
) -> HTMLResponse:
    settings = get_all_settings()
    # Fetch model list từ provider để render dropdown. None nếu key sai / chưa cấu hình.
    available = get_available_models(refresh=bool(refresh_models))
    grouped_models = _group_models_by_provider(available) if available else None
    return templates.TemplateResponse(
        request,
        "admin_ai.html",
        {
            "user": user,
            "settings": settings,
            "registry": {k: {"description": v.description} for k, v in SETTINGS_REGISTRY.items()},
            "saved": saved,
            "error": error,
            "grouped_models": grouped_models,
            "models_count": len(available) if available else 0,
        },
    )


def _flash_redirect(saved: str | None = None, error: str | None = None) -> RedirectResponse:
    params = []
    if saved:
        params.append(f"saved={saved}")
    if error:
        from urllib.parse import quote
        params.append(f"error={quote(error)}")
    url = "/admin/ai" + (f"?{'&'.join(params)}" if params else "")
    return RedirectResponse(url=url, status_code=303)


@router.post("/connection", response_model=None)
def save_connection(
    base_url: str = Form(...),
    api_key: str = Form(""),  # rỗng = giữ key cũ
    extra_headers: str = Form("{}"),
    user: str = Depends(require_user),
) -> RedirectResponse:
    base_url = base_url.strip()
    if not base_url:
        return _flash_redirect(error="Base URL không được trống")
    if not base_url.startswith(("http://", "https://")):
        return _flash_redirect(error="Base URL phải bắt đầu bằng http:// hoặc https://")

    try:
        headers_dict = json.loads(extra_headers) if extra_headers.strip() else {}
        if not isinstance(headers_dict, dict):
            raise ValueError("must be JSON object")
        for k, v in headers_dict.items():
            if not isinstance(k, str) or not isinstance(v, str):
                raise ValueError("keys/values phải là string")
    except (json.JSONDecodeError, ValueError) as e:
        return _flash_redirect(error=f"Extra headers không hợp lệ: {e}")

    set_setting("base_url", base_url, user)
    set_setting("extra_headers", headers_dict, user)
    # API key: empty = không đổi (giữ giá trị cũ).
    if api_key.strip():
        set_setting("api_key", api_key.strip(), user)

    return _flash_redirect(saved="connection")


@router.post("/models", response_model=None)
def save_models(
    model_default: str = Form(...),
    model_fast: str = Form(...),
    model_deep: str = Form(...),
    temperature: float = Form(...),
    max_tokens: int = Form(...),
    user: str = Depends(require_user),
) -> RedirectResponse:
    if not (0.0 <= temperature <= 2.0):
        return _flash_redirect(error="Temperature phải trong [0.0, 2.0]")
    if not (16 <= max_tokens <= 16384):
        return _flash_redirect(error="Max tokens phải trong [16, 16384]")
    for m in (model_default, model_fast, model_deep):
        if not m.strip():
            return _flash_redirect(error="Tên model không được trống")

    set_setting("model_default", model_default.strip(), user)
    set_setting("model_fast", model_fast.strip(), user)
    set_setting("model_deep", model_deep.strip(), user)
    set_setting("temperature", temperature, user)
    set_setting("max_tokens", max_tokens, user)

    return _flash_redirect(saved="models")


@router.post("/flags", response_model=None)
def save_flags(
    enabled: str = Form(default=""),  # checkbox: "on" khi tích, rỗng khi không
    prompt_cache_enabled: str = Form(default=""),
    user: str = Depends(require_user),
) -> RedirectResponse:
    set_setting("enabled", enabled == "on", user)
    set_setting("prompt_cache_enabled", prompt_cache_enabled == "on", user)
    return _flash_redirect(saved="flags")


@router.post("/test-connection", response_class=JSONResponse)
def admin_test_connection(
    base_url: str = Form(...),
    api_key: str = Form(""),
    extra_headers: str = Form("{}"),
    user: str = Depends(require_user),
) -> JSONResponse:
    """Test ping với credential từ form (chưa save).

    api_key rỗng → dùng key đã lưu trong DB (nếu có) để user không phải
    paste lại khi chỉ thử đổi base_url.
    """
    base_url = base_url.strip()
    if not base_url.startswith(("http://", "https://")):
        return JSONResponse(
            {"ok": False, "error": "Base URL phải bắt đầu bằng http:// hoặc https://"},
            status_code=400,
        )

    # Resolve effective api_key
    effective_key = api_key.strip() or get_setting("api_key")
    if not effective_key:
        return JSONResponse(
            {"ok": False, "error": "Chưa có API key. Nhập key trước khi test."},
        )

    try:
        headers_dict = json.loads(extra_headers) if extra_headers.strip() else {}
        if not isinstance(headers_dict, dict):
            raise ValueError("không phải JSON object")
    except (json.JSONDecodeError, ValueError) as e:
        return JSONResponse({"ok": False, "error": f"Extra headers lỗi: {e}"}, status_code=400)

    result = test_connection(
        base_url=base_url,
        api_key=effective_key,
        extra_headers=headers_dict,
        timeout_s=10,
    )
    return JSONResponse({
        "ok": result.ok,
        "error": result.error,
        "models": result.models[:30] if result.models else None,
        "latency_ms": result.latency_ms,
        "total_models": len(result.models) if result.models else 0,
    })
