"""POST /api/chat — main AI chat endpoint.

Flow (Day 3, non-streaming):
1. Auth + check master switch.
2. Resume/create conversation. Verify ownership.
3. Load history (last N turns) + build system prompt với page context.
4. Tool-call loop tối đa MAX_TOOL_LOOP iterations.
5. Save user/assistant/tool messages vào audit log.
6. Return JSON với content + tool_calls trace.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from openai import APIError, APIStatusError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.client import cache_supports_anthropic, make_client
from app.ai.config import get_setting
from app.ai.system_prompt import build_messages_system
from app.ai.tools import TOOL_SCHEMAS, run_tool
from app.auth import require_user
from app.database import get_db
from app.models import AiConversation, AiMessage

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

MAX_TOOL_LOOP = 5
HISTORY_TURN_LIMIT = 20  # message count, not round-trip


def _load_history(db: Session, conv_id: int) -> list[dict]:
    """Reload toàn bộ message của conversation thành OpenAI format.

    Cắt còn HISTORY_TURN_LIMIT message cuối cùng.
    """
    rows = db.scalars(
        select(AiMessage)
        .where(AiMessage.conversation_id == conv_id)
        .order_by(AiMessage.id.desc())
        .limit(HISTORY_TURN_LIMIT)
    ).all()
    rows = list(reversed(rows))
    out: list[dict] = []
    for r in rows:
        if r.role == "tool":
            out.append({
                "role": "tool",
                "tool_call_id": r.tool_call_id or "",
                "content": r.content,
            })
        elif r.role == "assistant" and r.tool_call_id:
            # Assistant turn that issued tool calls — stored with tool_call_id pointing to
            # the JSON array of calls. content may be empty.
            try:
                tool_calls = json.loads(r.tool_args_json or "[]")
            except json.JSONDecodeError:
                tool_calls = []
            msg: dict[str, Any] = {"role": "assistant", "content": r.content or None}
            if tool_calls:
                msg["tool_calls"] = tool_calls
            out.append(msg)
        else:
            out.append({"role": r.role, "content": r.content})
    return out


def _save_msg(
    db: Session,
    conv_id: int,
    role: str,
    content: str,
    *,
    tool_call_id: str | None = None,
    tool_name: str | None = None,
    tool_args_json: str | None = None,
    model: str | None = None,
    tokens_in: int | None = None,
    tokens_out: int | None = None,
    latency_ms: int | None = None,
) -> AiMessage:
    msg = AiMessage(
        conversation_id=conv_id,
        role=role,
        content=content,
        tool_call_id=tool_call_id,
        tool_name=tool_name,
        tool_args_json=tool_args_json,
        model=model,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        latency_ms=latency_ms,
    )
    db.add(msg)
    db.flush()
    return msg


@router.post("/chat")
async def chat(
    request: Request,
    user: str = Depends(require_user),
    db: Session = Depends(get_db),
) -> dict:
    if not get_setting("enabled"):
        raise HTTPException(status_code=503, detail="AI assistant đang tắt. Bật trong /admin/ai.")
    if not get_setting("api_key"):
        raise HTTPException(status_code=503, detail="Chưa cấu hình API key. Cấu hình ở /admin/ai.")

    try:
        body = await request.json()
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Body JSON lỗi: {e}") from e

    user_message: str = (body.get("message") or "").strip()
    conv_id: int | None = body.get("conversation_id")
    page_context: dict = body.get("page_context") or {}

    if not user_message:
        raise HTTPException(status_code=400, detail="Message không được trống.")

    # Resume hay tạo mới conversation
    if conv_id:
        conv = db.get(AiConversation, conv_id)
        if conv is None or conv.user != user:
            raise HTTPException(status_code=404, detail="Conversation không tồn tại.")
    else:
        conv = AiConversation(user=user, page_url_seed=page_context.get("url"))
        db.add(conv)
        db.flush()

    # Save user message
    _save_msg(db, conv.id, "user", user_message)
    db.commit()

    # Build messages cho API
    system_msgs = build_messages_system(
        page_context=page_context,
        enable_cache=get_setting("prompt_cache_enabled") and cache_supports_anthropic(),
    )
    history = _load_history(db, conv.id)
    messages = system_msgs + history

    client = make_client()
    model = get_setting("model_default")
    temperature = float(get_setting("temperature"))
    max_tokens = int(get_setting("max_tokens"))

    tool_trace: list[dict] = []
    final_text = ""
    total_in = 0
    total_out = 0

    for _ in range(MAX_TOOL_LOOP):
        t0 = time.time()
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=TOOL_SCHEMAS,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except APIStatusError as e:
            log.warning("LLM API status error: %s", e)
            raise HTTPException(
                status_code=502,
                detail=f"Provider lỗi {e.status_code}: {str(e)[:200]}",
            ) from e
        except APIError as e:
            log.warning("LLM API error: %s", e)
            raise HTTPException(status_code=502, detail=f"Lỗi gọi LLM: {e}") from e
        latency_ms = int((time.time() - t0) * 1000)

        usage = getattr(resp, "usage", None)
        tokens_in = getattr(usage, "prompt_tokens", 0) or 0
        tokens_out = getattr(usage, "completion_tokens", 0) or 0
        total_in += tokens_in
        total_out += tokens_out

        choice = resp.choices[0]
        msg = choice.message
        finish_reason = choice.finish_reason

        if finish_reason == "tool_calls" and msg.tool_calls:
            # Serialise tool_calls để gửi lại lần sau + lưu audit.
            tool_calls_payload = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in msg.tool_calls
            ]
            # Lưu assistant turn (content có thể rỗng)
            _save_msg(
                db, conv.id, "assistant",
                content=msg.content or "",
                tool_args_json=json.dumps(tool_calls_payload, ensure_ascii=False),
                tool_call_id="batch",  # marker để _load_history nhận biết
                model=model,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                latency_ms=latency_ms,
            )
            # Append vào messages cho turn sau
            messages.append({
                "role": "assistant",
                "content": msg.content or None,
                "tool_calls": tool_calls_payload,
            })
            # Execute từng tool
            for tc in msg.tool_calls:
                tool_name = tc.function.name
                tool_args = tc.function.arguments or "{}"
                result_str = run_tool(tool_name, tool_args, db)
                tool_trace.append({
                    "name": tool_name,
                    "args": tool_args,
                    "result_preview": result_str[:300],
                })
                _save_msg(
                    db, conv.id, "tool",
                    content=result_str,
                    tool_call_id=tc.id,
                    tool_name=tool_name,
                    tool_args_json=tool_args,
                )
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result_str,
                })
            db.commit()
            continue  # loop tiếp để LLM consume tool results

        # finish_reason in ("stop", "length", ...) — break loop
        final_text = msg.content or ""
        _save_msg(
            db, conv.id, "assistant",
            content=final_text,
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
        )
        db.commit()
        break
    else:
        # Hit MAX_TOOL_LOOP without "stop" — chắc model loop. Refuse.
        raise HTTPException(
            status_code=500,
            detail=f"Model vượt {MAX_TOOL_LOOP} vòng tool call mà chưa trả lời.",
        )

    return {
        "conversation_id": conv.id,
        "message": final_text,
        "tool_calls": tool_trace,
        "usage": {
            "model": model,
            "tokens_in": total_in,
            "tokens_out": total_out,
        },
    }
