"""Admin routes — cấu hình AI assistant.

Mỗi section 1 form + 1 POST riêng để save không reload toàn page state.
API key đặc biệt: input password rỗng theo default; submit rỗng = giữ key cũ.
Test connection: endpoint JSON, FE fetch() và render kết quả inline.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.ai.config import (
    SETTINGS_REGISTRY,
    get_all_settings,
    get_available_models,
    get_setting,
    set_setting,
    test_connection,
)
from app.ai.limits import usage_today
from app.auth import SessionUser, require_admin
from app.database import get_db
from app.models import AiConversation, AiMessage
from app.version import VERSION, version_string

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=BASE_DIR / "templates")
templates.env.globals["app_version_string"] = version_string()
templates.env.globals["app_version"] = VERSION

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
    user: SessionUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    settings = get_all_settings()
    # Fetch model list từ provider để render dropdown. None nếu key sai / chưa cấu hình.
    available = get_available_models(refresh=bool(refresh_models))
    grouped_models = _group_models_by_provider(available) if available else None

    # Audit section 5: KPI hôm nay + 20 conversation gần nhất.
    usage = usage_today(db)
    recent_convs_rows = db.execute(
        select(
            AiConversation,
            func.count(AiMessage.id),
            func.coalesce(func.sum(AiMessage.cost_usd), 0.0),
            func.coalesce(func.sum(AiMessage.tokens_in), 0),
            func.coalesce(func.sum(AiMessage.tokens_out), 0),
        )
        .outerjoin(AiMessage, AiMessage.conversation_id == AiConversation.id)
        .group_by(AiConversation.id)
        .order_by(desc(AiConversation.started_at))
        .limit(20)
    ).all()
    recent_convs = [
        {
            "id": conv.id,
            "user": conv.user,
            "title": (conv.title or "(chưa đặt)")[:60],
            "started_at": conv.started_at,
            "msg_count": int(n),
            "cost_usd": round(float(cost), 4),
            "tokens_in": int(t_in),
            "tokens_out": int(t_out),
        }
        for conv, n, cost, t_in, t_out in recent_convs_rows
    ]

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
            "usage": usage,
            "recent_convs": recent_convs,
            # Tạm ẩn cost UI khỏi admin/ai — số chi phí dễ gây hiểu nhầm trong giai
            # đoạn demo HQ. Đổi về True để hiển thị lại.
            "show_cost": False,
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
    user: SessionUser = Depends(require_admin),
) -> RedirectResponse:
    base_url = base_url.strip()
    if not base_url:
        return _flash_redirect(error="Địa chỉ máy chủ không được trống")
    if not base_url.startswith(("http://", "https://")):
        return _flash_redirect(error="Địa chỉ máy chủ phải bắt đầu bằng http:// hoặc https://")

    try:
        headers_dict = json.loads(extra_headers) if extra_headers.strip() else {}
        if not isinstance(headers_dict, dict):
            raise ValueError("phải là đối tượng JSON")
        for k, v in headers_dict.items():
            if not isinstance(k, str) or not isinstance(v, str):
                raise ValueError("khoá/giá trị phải là chuỗi")
    except (json.JSONDecodeError, ValueError) as e:
        return _flash_redirect(error=f"Tiêu đề HTTP bổ sung không hợp lệ: {e}")

    set_setting("base_url", base_url, user.name)
    set_setting("extra_headers", headers_dict, user.name)
    # API key: empty = không đổi (giữ giá trị cũ).
    if api_key.strip():
        set_setting("api_key", api_key.strip(), user.name)

    return _flash_redirect(saved="connection")


@router.post("/models", response_model=None)
def save_models(
    model_default: str = Form(...),
    model_fast: str = Form(...),
    model_deep: str = Form(...),
    temperature: float = Form(...),
    max_tokens: int = Form(...),
    user: SessionUser = Depends(require_admin),
) -> RedirectResponse:
    if not (0.0 <= temperature <= 2.0):
        return _flash_redirect(error="Độ ngẫu nhiên phải trong [0.0, 2.0]")
    if not (16 <= max_tokens <= 16384):
        return _flash_redirect(error="Tối đa token phải trong [16, 16384]")
    for m in (model_default, model_fast, model_deep):
        if not m.strip():
            return _flash_redirect(error="Tên mô hình không được trống")

    set_setting("model_default", model_default.strip(), user.name)
    set_setting("model_fast", model_fast.strip(), user.name)
    set_setting("model_deep", model_deep.strip(), user.name)
    set_setting("temperature", temperature, user.name)
    set_setting("max_tokens", max_tokens, user.name)

    return _flash_redirect(saved="models")


@router.post("/limits", response_model=None)
def save_limits(
    daily_budget_usd: float = Form(...),
    rate_limit_per_hour: int = Form(...),
    request_timeout_s: int = Form(...),
    tool_call_cap: int = Form(...),
    history_retention_days: int = Form(...),
    audit_retention_days: int = Form(...),
    user: SessionUser = Depends(require_admin),
) -> RedirectResponse:
    if daily_budget_usd < 0 or daily_budget_usd > 10000:
        return _flash_redirect(error="Hạn mức theo ngày phải trong [0, 10000] USD.")
    if rate_limit_per_hour < 0 or rate_limit_per_hour > 10000:
        return _flash_redirect(error="Giới hạn tần suất phải trong [0, 10000].")
    if request_timeout_s < 5 or request_timeout_s > 600:
        return _flash_redirect(error="Thời gian chờ phản hồi phải trong [5, 600] giây.")
    if tool_call_cap < 1 or tool_call_cap > 50:
        return _flash_redirect(error="Giới hạn lệnh gọi công cụ phải trong [1, 50].")
    if history_retention_days < 1 or audit_retention_days < 1:
        return _flash_redirect(error="Thời gian lưu giữ phải >= 1 ngày.")

    set_setting("daily_budget_usd", daily_budget_usd, user.name)
    set_setting("rate_limit_per_hour", rate_limit_per_hour, user.name)
    set_setting("request_timeout_s", request_timeout_s, user.name)
    set_setting("tool_call_cap", tool_call_cap, user.name)
    set_setting("history_retention_days", history_retention_days, user.name)
    set_setting("audit_retention_days", audit_retention_days, user.name)
    return _flash_redirect(saved="limits")


@router.post("/fallback", response_model=None)
def save_fallback(
    fallback_enabled: str = Form(default=""),
    fallback_base_url: str = Form(...),
    fallback_api_key: str = Form(""),
    fallback_model_default: str = Form(...),
    fallback_model_fast: str = Form(...),
    fallback_model_deep: str = Form(...),
    user: SessionUser = Depends(require_admin),
) -> RedirectResponse:
    enabled = fallback_enabled.lower() in ("on", "true", "1", "yes")
    base_url = fallback_base_url.strip()
    if enabled and not base_url.startswith(("http://", "https://")):
        return _flash_redirect(error="Địa chỉ máy chủ phụ phải bắt đầu bằng http:// hoặc https://")
    for m in (fallback_model_default, fallback_model_fast, fallback_model_deep):
        if not m.strip():
            return _flash_redirect(error="Tên mô hình phụ không được trống")

    set_setting("fallback_enabled", enabled, user.name)
    set_setting("fallback_base_url", base_url, user.name)
    if fallback_api_key.strip():
        set_setting("fallback_api_key", fallback_api_key.strip(), user.name)
    set_setting("fallback_model_default", fallback_model_default.strip(), user.name)
    set_setting("fallback_model_fast", fallback_model_fast.strip(), user.name)
    set_setting("fallback_model_deep", fallback_model_deep.strip(), user.name)
    return _flash_redirect(saved="fallback")


@router.post("/flags", response_model=None)
def save_flags(
    enabled: str = Form(default=""),  # checkbox: "on" khi tích, rỗng khi không
    prompt_cache_enabled: str = Form(default=""),
    user: SessionUser = Depends(require_admin),
) -> RedirectResponse:
    set_setting("enabled", enabled == "on", user.name)
    set_setting("prompt_cache_enabled", prompt_cache_enabled == "on", user.name)
    return _flash_redirect(saved="flags")


@router.post("/test-connection", response_class=JSONResponse)
def admin_test_connection(
    base_url: str = Form(...),
    api_key: str = Form(""),
    extra_headers: str = Form("{}"),
    user: SessionUser = Depends(require_admin),
) -> JSONResponse:
    """Test ping với credential từ form (chưa save).

    api_key rỗng → dùng key đã lưu trong DB (nếu có) để user không phải
    paste lại khi chỉ thử đổi base_url.
    """
    base_url = base_url.strip()
    if not base_url.startswith(("http://", "https://")):
        return JSONResponse(
            {"ok": False, "error": "Địa chỉ máy chủ phải bắt đầu bằng http:// hoặc https://"},
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
            raise ValueError("phải là đối tượng JSON")
    except (json.JSONDecodeError, ValueError) as e:
        return JSONResponse({"ok": False, "error": f"Tiêu đề HTTP bổ sung lỗi: {e}"}, status_code=400)

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


@router.get("/conversations/{conv_id}", response_class=HTMLResponse)
def admin_conversation_detail(
    conv_id: int,
    request: Request,
    user: SessionUser = Depends(require_admin),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    """Full transcript của 1 conversation — debug khi AI sai / user complain."""
    conv = db.get(AiConversation, conv_id)
    if conv is None:
        raise HTTPException(status_code=404, detail="Cuộc trò chuyện không tồn tại")
    msgs = db.scalars(
        select(AiMessage)
        .where(AiMessage.conversation_id == conv_id)
        .order_by(AiMessage.id)
    ).all()
    cost_total = sum(m.cost_usd or 0.0 for m in msgs)
    tokens_total_in = sum(m.tokens_in or 0 for m in msgs)
    tokens_total_out = sum(m.tokens_out or 0 for m in msgs)
    return templates.TemplateResponse(
        request,
        "admin_ai_conversation.html",
        {
            "user": user,
            "conv": conv,
            "msgs": msgs,
            "cost_total": round(cost_total, 4),
            "tokens_total_in": tokens_total_in,
            "tokens_total_out": tokens_total_out,
            "show_cost": False,
        },
    )
