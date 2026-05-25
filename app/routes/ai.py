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
from collections.abc import Iterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from openai import APIError, APIStatusError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.client import cache_supports_anthropic, make_client
from app.ai.config import get_setting
from app.ai.cost import estimate_cost
from app.ai.guardrails import apply_guardrails
from app.ai.limits import check_daily_budget, check_rate_limit
from app.ai.system_prompt import build_messages_system
from app.ai.tools import TOOL_SCHEMAS, run_tool
from app.auth import SessionUser, require_user
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
    cost_usd: float | None = None,
) -> AiMessage:
    # Auto-estimate cost nếu chưa cung cấp (role=assistant + có model + tokens).
    if cost_usd is None and role == "assistant" and model and (tokens_in or tokens_out):
        cost_usd = estimate_cost(model, tokens_in or 0, tokens_out or 0).total_usd
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
        cost_usd=cost_usd,
    )
    db.add(msg)
    db.flush()
    return msg


@router.post("/chat")
async def chat(
    request: Request,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> dict:
    if not get_setting("enabled"):
        raise HTTPException(status_code=503, detail="AI assistant đang tắt. Bật trong /admin/ai.")
    if not get_setting("api_key"):
        raise HTTPException(status_code=503, detail="Chưa cấu hình API key. Cấu hình ở /admin/ai.")
    check_rate_limit(user.name, db)
    check_daily_budget(db)

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
        if conv is None or conv.user != user.name:
            raise HTTPException(status_code=404, detail="Conversation không tồn tại.")
    else:
        conv = AiConversation(
            user=user.name,
            page_url_seed=page_context.get("url"),
            title=user_message[:80],
        )
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
        final_text = apply_guardrails(msg.content or "", conv_id=conv.id)
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


@router.get("/chat/conversations")
def list_conversations(
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> dict:
    """List conversation của user — 30 cái gần nhất."""
    convs = db.scalars(
        select(AiConversation)
        .where(AiConversation.user == user.name)
        .order_by(AiConversation.id.desc())
        .limit(30)
    ).all()
    out = []
    for c in convs:
        # Count messages
        msg_count = db.scalar(
            select(func.count())
            .select_from(AiMessage)
            .where(AiMessage.conversation_id == c.id)
        ) or 0
        # First user msg để làm preview/title fallback
        first_user_msg = db.scalar(
            select(AiMessage)
            .where(AiMessage.conversation_id == c.id, AiMessage.role == "user")
            .order_by(AiMessage.id)
            .limit(1)
        )
        title = c.title or (first_user_msg.content[:80] if first_user_msg else "(trống)")
        out.append({
            "id": c.id,
            "title": title,
            "started_at": c.started_at.isoformat() if c.started_at else None,
            "msg_count": msg_count,
            "page_url_seed": c.page_url_seed,
        })
    return {"conversations": out}


@router.get("/chat/conversations/{conv_id}/messages")
def get_conversation_messages(
    conv_id: int,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> dict:
    """Resume — render full transcript của 1 conversation."""
    conv = db.get(AiConversation, conv_id)
    if conv is None or conv.user != user.name:
        raise HTTPException(status_code=404, detail="Conversation không tồn tại.")
    msgs = db.scalars(
        select(AiMessage)
        .where(AiMessage.conversation_id == conv.id)
        .order_by(AiMessage.id)
    ).all()
    return {
        "conversation_id": conv.id,
        "title": conv.title,
        "started_at": conv.started_at.isoformat() if conv.started_at else None,
        "messages": [
            {
                "role": m.role,
                "content": m.content,
                "tool_name": m.tool_name,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in msgs
            # Skip internal "batch" assistant marker — UI chỉ cần message
            # có content (user/assistant text + tool result).
            if not (m.role == "assistant" and m.tool_call_id == "batch" and not m.content)
        ],
    }


@router.delete("/chat/conversations/{conv_id}")
def delete_conversation(
    conv_id: int,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> dict:
    conv = db.get(AiConversation, conv_id)
    if conv is None or conv.user != user.name:
        raise HTTPException(status_code=404, detail="Conversation không tồn tại.")
    db.delete(conv)  # cascade xoá messages
    db.commit()
    return {"deleted": conv_id}


@router.get("/ai/meta")
def ai_meta(user: SessionUser = Depends(require_user)) -> dict:
    """Frontend dùng để biết có nên render sidebar không."""
    return {
        "enabled": bool(get_setting("enabled")),
        "configured": bool(get_setting("api_key")),
        "model": get_setting("model_default"),
        "is_admin": user.is_admin,
    }


def _sse(event: str, data: Any) -> str:
    """Format 1 SSE event."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/chat/stream")
async def chat_stream(
    request: Request,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Streaming version of /api/chat — Server-Sent Events.

    Events:
      content     {"text": str}         — token delta cho assistant reply
      tool_call   {"name", "args"}      — model bắt đầu gọi tool (sau finish_reason=tool_calls)
      tool_result {"name", "preview"}   — tool executed, preview cho UI
      done        {conversation_id, usage}
      error       {"detail": str}
    """
    if not get_setting("enabled"):
        raise HTTPException(status_code=503, detail="AI assistant đang tắt.")
    if not get_setting("api_key"):
        raise HTTPException(status_code=503, detail="Chưa cấu hình API key.")

    try:
        body = await request.json()
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Body JSON lỗi: {e}") from e
    user_message: str = (body.get("message") or "").strip()
    conv_id: int | None = body.get("conversation_id")
    page_context: dict = body.get("page_context") or {}

    if not user_message:
        raise HTTPException(status_code=400, detail="Message không được trống.")

    if conv_id:
        conv = db.get(AiConversation, conv_id)
        if conv is None or conv.user != user.name:
            raise HTTPException(status_code=404, detail="Conversation không tồn tại.")
    else:
        conv = AiConversation(
            user=user.name,
            page_url_seed=page_context.get("url"),
            title=user_message[:80],
        )
        db.add(conv)
        db.flush()

    _save_msg(db, conv.id, "user", user_message)
    db.commit()
    conv_id_resolved = conv.id

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

    def event_gen() -> Iterator[str]:
        # Reuse messages mutate-in-place qua các iteration tool loop.
        total_in = 0
        total_out = 0
        try:
            for _ in range(MAX_TOOL_LOOP):
                t0 = time.time()
                stream = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    tools=TOOL_SCHEMAS,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=True,
                    stream_options={"include_usage": True},
                )

                acc_text = ""
                # Accumulate tool calls by index — chunks gửi delta arguments.
                acc_tool_calls: dict[int, dict] = {}
                finish_reason: str | None = None
                tokens_in = 0
                tokens_out = 0

                for chunk in stream:
                    # Usage info trên chunk cuối (khi include_usage=True).
                    usage = getattr(chunk, "usage", None)
                    if usage is not None:
                        tokens_in = usage.prompt_tokens or 0
                        tokens_out = usage.completion_tokens or 0

                    if not chunk.choices:
                        continue
                    choice = chunk.choices[0]
                    delta = choice.delta

                    if delta and delta.content:
                        acc_text += delta.content
                        yield _sse("content", {"text": delta.content})

                    if delta and delta.tool_calls:
                        for tc in delta.tool_calls:
                            idx = tc.index
                            slot = acc_tool_calls.setdefault(
                                idx, {"id": "", "name": "", "arguments": ""}
                            )
                            if tc.id:
                                slot["id"] = tc.id
                            if tc.function:
                                if tc.function.name:
                                    slot["name"] = tc.function.name
                                if tc.function.arguments:
                                    slot["arguments"] += tc.function.arguments

                    if choice.finish_reason:
                        finish_reason = choice.finish_reason

                latency_ms = int((time.time() - t0) * 1000)
                total_in += tokens_in
                total_out += tokens_out

                if finish_reason == "tool_calls" and acc_tool_calls:
                    tool_calls_payload = [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {"name": tc["name"], "arguments": tc["arguments"]},
                        }
                        for tc in sorted(acc_tool_calls.values(), key=lambda x: x.get("id", ""))
                    ]
                    # Append assistant turn vào messages history + audit.
                    _save_msg(
                        db, conv_id_resolved, "assistant",
                        content=acc_text,
                        tool_args_json=json.dumps(tool_calls_payload, ensure_ascii=False),
                        tool_call_id="batch",
                        model=model,
                        tokens_in=tokens_in,
                        tokens_out=tokens_out,
                        latency_ms=latency_ms,
                    )
                    messages.append({
                        "role": "assistant",
                        "content": acc_text or None,
                        "tool_calls": tool_calls_payload,
                    })

                    for tc in tool_calls_payload:
                        name = tc["function"]["name"]
                        args = tc["function"]["arguments"] or "{}"
                        yield _sse("tool_call", {"name": name, "args": args})
                        result_str = run_tool(name, args, db)
                        _save_msg(
                            db, conv_id_resolved, "tool",
                            content=result_str,
                            tool_call_id=tc["id"],
                            tool_name=name,
                            tool_args_json=args,
                        )
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": result_str,
                        })
                        yield _sse("tool_result", {"name": name, "preview": result_str[:300]})
                    db.commit()
                    continue

                # finish_reason in ("stop", "length") → final answer
                clean_text = apply_guardrails(acc_text, conv_id=conv_id_resolved)
                _save_msg(
                    db, conv_id_resolved, "assistant",
                    content=clean_text,
                    model=model,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    latency_ms=latency_ms,
                )
                db.commit()
                yield _sse("done", {
                    "conversation_id": conv_id_resolved,
                    "usage": {"model": model, "tokens_in": total_in, "tokens_out": total_out},
                })
                return
            # exceeded MAX_TOOL_LOOP
            yield _sse("error", {"detail": f"Vượt {MAX_TOOL_LOOP} vòng tool call."})
        except APIStatusError as e:
            log.warning("LLM API status error: %s", e)
            yield _sse("error", {"detail": f"Provider lỗi {e.status_code}: {str(e)[:200]}"})
        except APIError as e:
            log.warning("LLM API error: %s", e)
            yield _sse("error", {"detail": f"Lỗi LLM: {e}"})
        except Exception as e:  # noqa: BLE001
            log.exception("Unexpected error in chat_stream")
            yield _sse("error", {"detail": f"{type(e).__name__}: {e}"})

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering nếu sau này có
        },
    )
