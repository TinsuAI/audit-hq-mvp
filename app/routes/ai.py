"""POST /api/chat — main AI chat endpoint.

Flow (Day 3, non-streaming):
1. Auth + check master switch.
2. Resume/create conversation. Verify ownership.
3. Load history (last N turns) + build system prompt với page context.
4. Tool-call loop tối đa `tool_call_cap` iterations (DB setting, default 10).
5. Save user/assistant/tool messages vào audit log.
6. Return JSON với content + tool_calls trace.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from openai import APIError, APIStatusError
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.ai.client import (
    cache_supports_anthropic,
    call_with_fallback,
    fallback_model_for,
    make_client,
    make_fallback_client,
)
from app.ai.config import get_setting
from app.ai.conversation_scope import (
    late_assign_company,
    resolve_company_for_new_conversation,
    visible_company_by_ident,
)
from app.ai.cost import estimate_cost
from app.ai.guardrails import apply_guardrails
from app.ai.limits import check_daily_budget, check_rate_limit
from app.ai.system_prompt import build_messages_system
from app.ai.tools import get_tool_schemas, run_tool
from app.ai.usage import conversation_ref, record_usage
from app.audit import ACTION_EXPORT_QUERY, ACTION_RUN_CHECKS, log_access
from app.auth import SessionUser, require_user
from app.auth_users import get_user_by_username
from app.database import get_db
from app.jobs import enqueue_job
from app.models import AiConversation, AiMessage, AiUsage, Company, Finding
from app.models.job import JobKind
from app.scoping import allowed_company_codes, can_access_company_id, get_company_or_404

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

HISTORY_TURN_LIMIT = 20  # message count, not round-trip


def _resolve_mentions(
    db: Session, raw: object, allowed_codes: set[str] | None
) -> list[dict]:
    """Resolve mention từ client (@DN/@finding) → dict đã XÁC THỰC LẠI phạm vi.

    KHÔNG tin code/id client gửi: tra DB + chặn theo `allowed_codes` (officer). Mục
    đích là đưa định danh CHÍNH XÁC vào ngữ cảnh để AI gọi tool đúng, không phải lối
    đi vòng để truy cập DN ngoài phạm vi.
    """
    out: list[dict] = []
    if not isinstance(raw, list):
        return out
    for m in raw[:10]:
        if not isinstance(m, dict):
            continue
        if m.get("type") == "company":
            code = m.get("code")
            if not code or (allowed_codes is not None and code not in allowed_codes):
                continue
            c = db.scalar(select(Company).where(Company.code == code))
            if c:
                out.append({"type": "company", "code": c.code, "name": c.name})
        elif m.get("type") == "finding":
            try:
                fid = int(m.get("id"))
            except (TypeError, ValueError):
                continue
            f = db.get(Finding, fid)
            if f is None:
                continue
            comp = db.get(Company, f.company_id)
            if comp is None or (allowed_codes is not None and comp.code not in allowed_codes):
                continue
            out.append({"type": "finding", "id": f.id, "title": f.title, "company_code": comp.code})
    return out


def _conversation_lock(db: Session, conv: AiConversation, user: SessionUser) -> str | None:
    """Lý do cuộc bị khoá gửi, hoặc None nếu gửi được (ADR #20).

    Cuộc gắn DN mà cán bộ không còn được phân công: transcript vẫn ĐỌC được
    (quyền đọc theo sở hữu cuộc, không đổi), nhưng không gửi thêm. Thay cho cảnh
    hỏi được mà câu nào cũng bị tool từ chối, không nói vì sao.
    """
    if conv.company_id is None or can_access_company_id(db, user, conv.company_id):
        return None
    company = db.get(Company, conv.company_id)
    name = company.name if company else f"#{conv.company_id}"
    return (
        f"Cuộc trò chuyện này gắn với doanh nghiệp {name}, hiện bạn không còn được phân công "
        "doanh nghiệp đó nên không gửi thêm được. Nội dung cũ vẫn đọc được. "
        "Liên hệ quản trị nếu cần phân công lại."
    )


def _conversation_company(db: Session, conv: AiConversation) -> dict | None:
    """`{code, name}` của DN gắn cuộc — nạp vào system prompt làm chủ đề."""
    if conv.company_id is None:
        return None
    label = _company_labels(db, {conv.company_id}).get(conv.company_id)
    return {"code": label["code"], "name": label["name"]} if label else None


def _resume_or_create_conversation(
    db: Session,
    user: SessionUser,
    conv_id: int | None,
    *,
    page_context: dict,
    mentions: list[dict],
    user_message: str,
) -> AiConversation:
    """Resume cuộc cũ (kiểm sở hữu) hoặc tạo cuộc mới đã gắn DN (ADR #20).

    Dùng chung cho `/api/chat` và `/api/chat/stream` — nhận diện DN phải giống
    hệt nhau ở hai đường, nếu không nhãn sẽ phụ thuộc vào việc client có stream
    hay không.
    """
    if conv_id:
        conv = db.get(AiConversation, conv_id)
        if conv is None or conv.user != user.name:
            raise HTTPException(status_code=404, detail="Conversation không tồn tại.")
        locked = _conversation_lock(db, conv, user)
        if locked:
            raise HTTPException(status_code=403, detail=locked)
        # Cuộc còn trống → nhắc đúng một @DN thì gắn rồi cố định.
        late_assign_company(db, conv, mentions, user)
        return conv
    conv = AiConversation(
        user=user.name,
        page_url_seed=page_context.get("url"),
        title=user_message[:80],
        company_id=resolve_company_for_new_conversation(db, user, page_context),
    )
    db.add(conv)
    db.flush()
    # Cuộc mới không nhận được tín hiệu nào từ trang → mention của chính lượt này.
    late_assign_company(db, conv, mentions, user)
    return conv


def _clean_tool_args(raw: str) -> str:
    """Chuẩn hoá `arguments` của tool-call về JSON hợp lệ.

    Một số provider (vd Gemini) phát nhiều call song song có thể khiến args bị nối
    thành '{...}{...}'. Lấy object JSON ĐẦU TIÊN + bỏ phần thừa → tránh: (a) JSON
    parse lỗi khi chạy tool, (b) provider 400 khi gửi lại message với args hỏng.
    """
    if not raw or not raw.strip():
        return "{}"
    try:
        obj, _ = json.JSONDecoder().raw_decode(raw.strip())
        return json.dumps(obj, ensure_ascii=False)
    except (json.JSONDecodeError, ValueError):
        return raw  # để run_tool báo lỗi rõ nếu vẫn không parse được


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
    # Mỗi assistant turn = MỘT lời gọi LLM tính tiền (vòng tool sinh nhiều turn,
    # nên cũng nhiều dòng sổ — đúng ý "một dòng mỗi lời gọi").
    if cost_usd is not None and role == "assistant":
        conv = db.get(AiConversation, conv_id)
        record_usage(
            db,
            kind=AiUsage.KIND_CHAT,
            ref=conversation_ref(conv_id),
            model=model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost_usd,
            user=conv.user if conv is not None else None,
        )
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

    # Ranh giới phân quyền DN cho tool (officer: chỉ DN được phân công; admin: None).
    allowed_codes = allowed_company_codes(db, user)

    try:
        body = await request.json()
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Body JSON lỗi: {e}") from e

    user_message: str = (body.get("message") or "").strip()
    conv_id: int | None = body.get("conversation_id")
    page_context: dict = body.get("page_context") or {}

    # Mention @DN/@finding → resolve + xác thực lại phạm vi rồi nhét vào ngữ cảnh.
    mentions = _resolve_mentions(db, body.get("mentions"), allowed_codes)
    if mentions:
        page_context = {**page_context, "mentions": mentions}

    if not user_message:
        raise HTTPException(status_code=400, detail="Message không được trống.")

    # Resume hay tạo mới conversation
    conv = _resume_or_create_conversation(
        db, user, conv_id,
        page_context=page_context, mentions=mentions, user_message=user_message,
    )

    # Save user message
    _save_msg(db, conv.id, "user", user_message)
    db.commit()

    # Build messages cho API
    system_msgs = build_messages_system(
        page_context=page_context,
        enable_cache=get_setting("prompt_cache_enabled") and cache_supports_anthropic(),
        conversation_company=_conversation_company(db, conv),
    )
    history = _load_history(db, conv.id)
    messages = system_msgs + history

    client = make_client()
    fb_client = make_fallback_client()
    fb_model = fallback_model_for("default")
    model = get_setting("model_default")
    temperature = float(get_setting("temperature"))
    max_tokens = int(get_setting("max_tokens"))

    tool_trace: list[dict] = []
    final_text = ""
    total_in = 0
    total_out = 0
    tool_call_cap = int(get_setting("tool_call_cap"))

    used_model = model  # Tracking nào provider thực sự trả lời (primary hay fallback).

    for _ in range(tool_call_cap):
        t0 = time.time()
        try:
            resp, used_model = call_with_fallback(
                primary_client=client,
                primary_model=model,
                fallback_client=fb_client,
                fallback_model=fb_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=get_tool_schemas(),
                return_model=True,
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
                    "function": {
                        "name": tc.function.name,
                        "arguments": _clean_tool_args(tc.function.arguments),
                    },
                }
                for tc in msg.tool_calls
            ]
            # Lưu assistant turn (content có thể rỗng)
            _save_msg(
                db, conv.id, "assistant",
                content=msg.content or "",
                tool_args_json=json.dumps(tool_calls_payload, ensure_ascii=False),
                tool_call_id="batch",  # marker để _load_history nhận biết
                model=used_model,
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
                result_str = run_tool(tool_name, tool_args, db, allowed_codes)
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
            model=used_model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
        )
        db.commit()
        break
    else:
        # Exceeded tool_call_cap without a stop — model is looping.
        raise HTTPException(
            status_code=500,
            detail=f"Model vượt {tool_call_cap} vòng tool call mà chưa trả lời.",
        )

    return {
        "conversation_id": conv.id,
        "message": final_text,
        "tool_calls": tool_trace,
        "usage": {
            "model": used_model,
            "fallback_used": used_model != model,
            "tokens_in": total_in,
            "tokens_out": total_out,
        },
    }


def _company_labels(db: Session, company_ids: set[int | None]) -> dict[int, dict]:
    """Nạp mã/slug/tên cho tập company_id trong MỘT câu — tránh N+1 khi render list."""
    ids = {i for i in company_ids if i is not None}
    if not ids:
        return {}
    rows = db.execute(
        select(Company.id, Company.code, Company.slug, Company.name).where(Company.id.in_(ids))
    ).all()
    return {r.id: {"code": r.code, "slug": r.slug, "name": r.name} for r in rows}


UNASSIGNED = "none"  # giá trị `company_id` cho nhóm "Chưa gán doanh nghiệp"


def _visible_conversations(user: SessionUser, mine: bool):
    """Ràng buộc "cuộc nào user này được thấy" — dùng chung cho list và nhóm.

    Officer: chỉ cuộc của chính mình (không có công tắc). Admin: mặc định cũng
    chỉ của mình ("Chỉ của tôi" BẬT sẵn) — giám sát cuộc người khác là thao tác
    phải bấm, không phải mặc định.
    """
    stmt = select(AiConversation)
    if mine or not user.is_admin:
        stmt = stmt.where(AiConversation.user == user.name)
    return stmt


def _search_clause(q: str):
    """Lọc theo tiêu đề cuộc HOẶC mã/tên DN — cùng nhãn với chip trên mỗi dòng."""
    like = f"%{q}%"
    return or_(
        AiConversation.title.ilike(like),
        AiConversation.company_id.in_(
            select(Company.id).where(or_(Company.code.ilike(like), Company.name.ilike(like)))
        ),
    )


def _last_activity_at(db: Session, conv_ids: list[int]) -> dict[int, datetime]:
    """Mốc tin nhắn cuối của mỗi cuộc — dùng cho quy tắc nối lại 24h."""
    if not conv_ids:
        return {}
    return {
        cid: ts
        for cid, ts in db.execute(
            select(AiMessage.conversation_id, func.max(AiMessage.created_at))
            .where(AiMessage.conversation_id.in_(conv_ids))
            .group_by(AiMessage.conversation_id)
        ).all()
    }


def _message_stats(db: Session, conv_ids: list[int]) -> tuple[dict[int, int], dict[int, str]]:
    """(số tin nhắn, tin nhắn user đầu tiên) cho nhiều cuộc — 2 câu, không N+1."""
    if not conv_ids:
        return {}, {}
    counts = {
        cid: n
        for cid, n in db.execute(
            select(AiMessage.conversation_id, func.count())
            .where(AiMessage.conversation_id.in_(conv_ids))
            .group_by(AiMessage.conversation_id)
        ).all()
    }
    first_ids = select(func.min(AiMessage.id)).where(
        AiMessage.conversation_id.in_(conv_ids), AiMessage.role == "user"
    ).group_by(AiMessage.conversation_id).scalar_subquery()
    firsts = {
        cid: content
        for cid, content in db.execute(
            select(AiMessage.conversation_id, AiMessage.content).where(AiMessage.id.in_(first_ids))
        ).all()
    }
    return counts, firsts


@router.get("/chat/conversations")
def list_conversations(
    company_id: str | None = Query(default=None, description="id DN, hoặc 'none' = chưa gán"),
    q: str = Query(default=""),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=30, ge=1, le=200),
    mine: bool = Query(default=True),
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> dict:
    """Danh sách cuộc trò chuyện, phân trang TRONG một nhóm doanh nghiệp.

    `company_id` bỏ trống = mọi nhóm (sidebar dùng danh sách phẳng). Trang `/chat`
    gọi một lần cho mỗi section nên bỏ được cap 30 toàn cục cũ.
    """
    stmt = _visible_conversations(user, mine)
    if company_id == UNASSIGNED:
        stmt = stmt.where(AiConversation.company_id.is_(None))
    elif company_id:
        try:
            stmt = stmt.where(AiConversation.company_id == int(company_id))
        except ValueError as e:
            raise HTTPException(status_code=400, detail="company_id không hợp lệ.") from e
    if q.strip():
        stmt = stmt.where(_search_clause(q.strip()))

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    convs = db.scalars(
        stmt.order_by(AiConversation.id.desc()).offset(offset).limit(limit)
    ).all()

    companies = _company_labels(db, {c.company_id for c in convs})
    counts, firsts = _message_stats(db, [c.id for c in convs])
    last_seen = _last_activity_at(db, [c.id for c in convs])
    out = []
    for c in convs:
        first = firsts.get(c.id)
        title = c.title or (first[:80] if first else "(trống)")
        label = companies.get(c.company_id) or {}
        last_at = last_seen.get(c.id) or c.started_at
        out.append({
            "id": c.id,
            "title": title,
            "started_at": c.started_at.isoformat() if c.started_at else None,
            "last_message_at": last_at.isoformat() if last_at else None,
            "msg_count": counts.get(c.id, 0),
            "page_url_seed": c.page_url_seed,
            "owner": c.user,  # admin xem list của nhiều user → FE hiện chủ + ẩn nút xoá cuộc người khác
            # Nhãn DN đọc từ dòng cuộc — FE KHÔNG suy từ page_url_seed nữa.
            "company_id": c.company_id,
            "company_code": label.get("code"),
            "company_slug": label.get("slug"),
            "company_name": label.get("name"),
        })
    return {"conversations": out, "total": total, "has_more": offset + len(out) < total}


@router.get("/chat/conversation-groups")
def list_conversation_groups(
    q: str = Query(default=""),
    mine: bool = Query(default=True),
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> dict:
    """Header section của trang `/chat`: mỗi doanh nghiệp + số cuộc.

    Sắp theo tên doanh nghiệp; nhóm chưa gán xếp CUỐI. Header section chính là
    doanh nghiệp — không có tầng "thư mục" nào ở giữa.
    """
    stmt = _visible_conversations(user, mine)
    if q.strip():
        stmt = stmt.where(_search_clause(q.strip()))
    sub = stmt.subquery()
    rows = db.execute(
        select(sub.c.company_id, func.count()).group_by(sub.c.company_id)
    ).all()

    labels = _company_labels(db, {cid for cid, _ in rows})
    groups = []
    unassigned = 0
    for cid, n in rows:
        if cid is None:
            unassigned = n
            continue
        label = labels.get(cid) or {}
        groups.append({
            "company_id": cid,
            "company_code": label.get("code"),
            "company_slug": label.get("slug"),
            "company_name": label.get("name") or label.get("code") or f"#{cid}",
            "count": n,
        })
    groups.sort(key=lambda g: g["company_name"].lower())
    if unassigned:
        groups.append({
            "company_id": None,
            "company_code": None,
            "company_slug": None,
            "company_name": "Chưa gán doanh nghiệp",
            "count": unassigned,
        })
    return {"groups": groups}


@router.patch("/chat/conversations/{conv_id}")
async def update_conversation_company(
    conv_id: int,
    request: Request,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> dict:
    """Đổi doanh nghiệp của một cuộc. `{"company_code": null}` = gỡ nhãn.

    Chủ cuộc sửa cuộc của mình; quản trị sửa mọi cuộc. Officer chỉ chọn được DN
    mình có quyền — chặn ở ĐÂY, không chỉ ở danh sách đổ vào ô chọn.
    """
    conv = db.get(AiConversation, conv_id)
    if conv is None or (conv.user != user.name and not user.is_admin):
        raise HTTPException(status_code=404, detail="Conversation không tồn tại.")

    try:
        body = await request.json()
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Body JSON lỗi: {e}") from e

    code = body.get("company_code")
    if code in (None, ""):
        conv.company_id = None
    else:
        # get_company_or_404 áp đúng ranh giới ADR #14 (404 cho DN ngoài phạm vi).
        conv.company_id = get_company_or_404(db, str(code), user).id
    db.commit()

    label = _company_labels(db, {conv.company_id}).get(conv.company_id) or {}
    return {
        "id": conv.id,
        "company_id": conv.company_id,
        "company_code": label.get("code"),
        "company_slug": label.get("slug"),
        "company_name": label.get("name"),
    }


@router.get("/chat/conversations/{conv_id}/messages")
def get_conversation_messages(
    conv_id: int,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> dict:
    """Resume — render full transcript của 1 conversation. Admin đọc được của mọi user."""
    conv = db.get(AiConversation, conv_id)
    if conv is None or (conv.user != user.name and not user.is_admin):
        raise HTTPException(status_code=404, detail="Conversation không tồn tại.")
    msgs = db.scalars(
        select(AiMessage)
        .where(AiMessage.conversation_id == conv.id)
        .order_by(AiMessage.id)
    ).all()
    label = _company_labels(db, {conv.company_id}).get(conv.company_id) or {}
    # Admin đọc cuộc người khác: chỉ để giám sát, không gửi tiếp vào cuộc đó.
    lock = (
        "Đây là cuộc trò chuyện của cán bộ khác — chỉ xem, không gửi thêm."
        if conv.user != user.name else _conversation_lock(db, conv, user)
    )
    return {
        "conversation_id": conv.id,
        "title": conv.title,
        "started_at": conv.started_at.isoformat() if conv.started_at else None,
        "can_send": lock is None,
        "lock_reason": lock,
        "company_id": conv.company_id,
        "company_code": label.get("code"),
        "company_slug": label.get("slug"),
        "company_name": label.get("name"),
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


RESUME_WINDOW_HOURS = 24


@router.get("/chat/resume")
def resume_conversation(
    company_code: str | None = Query(default=None),
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> dict:
    """Cuộc gần nhất CÙNG doanh nghiệp còn trong cửa sổ 24 giờ, hoặc không có.

    Sidebar gọi khi mở panel: có thì nối lại và báo rõ đang tiếp tục cuộc nào,
    không thì mở cuộc mới trong phạm vi đó. Quy tắc 24h ở SERVER (một chỗ, test
    được) chứ không rải trong JS.

    Mốc đo là tin nhắn CUỐI, không phải lúc mở cuộc: "gần nhất" theo nghĩa cán
    bộ vừa dùng. Cửa sổ tồn tại vì resume nạp lại 20 message vào MỌI prompt sau
    đó — cuộc để lâu neo câu trả lời vào dữ liệu có thể đã nạp lại từ lúc ấy.
    """
    company = visible_company_by_ident(db, company_code, user)
    if company_code and company is None:
        return {"conversation_id": None}

    # Sắp theo hoạt động cuối trong SQL, không nạp N dòng rồi lọc trong Python:
    # một cuộc cũ nhưng vừa dùng lại phải thắng, kể cả khi nó nằm sâu trong danh
    # sách theo thứ tự tạo.
    last_msg = (
        select(
            AiMessage.conversation_id.label("cid"),
            func.max(AiMessage.created_at).label("last_at"),
        )
        .group_by(AiMessage.conversation_id)
        .subquery()
    )
    activity = func.coalesce(last_msg.c.last_at, AiConversation.started_at)
    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=RESUME_WINDOW_HOURS)
    row = db.execute(
        select(AiConversation, activity.label("at"))
        .outerjoin(last_msg, last_msg.c.cid == AiConversation.id)
        .where(
            AiConversation.user == user.name,
            AiConversation.company_id == company.id if company is not None
            else AiConversation.company_id.is_(None),
            activity >= cutoff,
        )
        .order_by(activity.desc())
        .limit(1)
    ).first()
    if row is None:
        return {"conversation_id": None}
    best, best_at = row[0], row[1]

    label = _company_labels(db, {best.company_id}).get(best.company_id) or {}
    return {
        "conversation_id": best.id,
        "title": best.title,
        "company_id": best.company_id,
        "company_code": label.get("code"),
        "company_name": label.get("name"),
        "last_message_at": best_at.isoformat() if best_at else None,
    }


@router.get("/chat/companies")
def chat_companies(
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> dict:
    """DN cán bộ được phép chọn — đổ vào ô chọn khi gán/đổi DN của cuộc."""
    stmt = select(Company).order_by(Company.name)
    allowed = allowed_company_codes(db, user)
    if allowed is not None:
        stmt = stmt.where(Company.code.in_(allowed))
    return {
        "companies": [
            {"id": c.id, "code": c.code, "slug": c.slug, "name": c.name}
            for c in db.scalars(stmt).all()
        ]
    }


@router.get("/chat/mentions")
def chat_mentions(
    q: str = Query(""),
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> dict:
    """Autocomplete mention @DN/@finding — LỌC theo DN được phân công (cùng ranh giới).

    Officer chỉ thấy DN của mình + finding thuộc DN đó. Admin (`allowed=None`) thấy tất.
    """
    qs = (q or "").strip()
    allowed = allowed_company_codes(db, user)
    items: list[dict] = []

    cstmt = select(Company)
    if allowed is not None:
        cstmt = cstmt.where(Company.code.in_(allowed))
    if qs:
        like = f"%{qs}%"
        cstmt = cstmt.where(or_(Company.name.ilike(like), Company.slug.ilike(like), Company.code.ilike(like)))
    for c in db.scalars(cstmt.order_by(Company.name).limit(6)).all():
        items.append({"type": "company", "code": c.code, "slug": c.slug, "name": c.name, "label": c.name})

    fstmt = select(Finding).join(Company, Finding.company_id == Company.id)
    if allowed is not None:
        fstmt = fstmt.where(Company.code.in_(allowed))
    if qs:
        conds = [Finding.title.ilike(f"%{qs}%")]
        if qs.isdigit():
            conds.append(Finding.id == int(qs))
        fstmt = fstmt.where(or_(*conds))
    for f in db.scalars(fstmt.order_by(Finding.id.desc()).limit(6)).all():
        comp = db.get(Company, f.company_id)
        items.append({
            "type": "finding", "id": f.id, "title": f.title,
            "company_code": comp.code if comp else None,
            "label": f"#{f.id} {f.title or ''}".strip(),
        })
    return {"items": items}


@router.get("/ai/meta")
def ai_meta(user: SessionUser = Depends(require_user)) -> dict:
    """Frontend dùng để biết có nên render sidebar không."""
    return {
        "enabled": bool(get_setting("enabled")),
        "configured": bool(get_setting("api_key")),
        "model": get_setting("model_default"),
        "is_admin": user.is_admin,
        "username": user.name,
    }


def _sse(event: str, data: Any) -> str:
    """Format 1 SSE event."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _extract_action(result_str: str) -> dict | None:
    """Lấy payload `_ui_action` từ kết quả tool (vd propose_check_run). None nếu không có."""
    try:
        data = json.loads(result_str)
    except (json.JSONDecodeError, TypeError):
        return None
    if isinstance(data, dict) and data.get("_ui_action") == "run_checks":
        return {
            "action": "run_checks",
            "company_code": data.get("company_code"),
            "year": data.get("year"),
            "label": data.get("label"),
            "note": data.get("note"),
        }
    return None


def _extract_download(result_str: str) -> dict:
    """Lấy download_url (export_excel/generate_report) để FE render chip tải. {} nếu không có."""
    try:
        data = json.loads(result_str)
    except (json.JSONDecodeError, TypeError):
        return {}
    if isinstance(data, dict) and data.get("download_url"):
        return {
            "download_url": data["download_url"],
            "year": data.get("year"),
            "title": data.get("title"),
        }
    return {}


@router.post("/chat/run-checks")
async def chat_run_checks(
    request: Request,
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> dict:
    """Cán bộ XÁC NHẬN chạy kiểm tra từ đề xuất của AI → enqueue job.

    Đây là điểm con-người-bấm-nút: AI chỉ đề xuất (propose_check_run), chỉ endpoint
    này (do cán bộ kích hoạt) mới thực sự tạo job. Trả JSON để sidebar hiện link.
    """
    try:
        body = await request.json()
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Body JSON lỗi: {e}") from e

    company_code = (body.get("company_code") or "").strip()
    year = body.get("year")
    if not company_code:
        raise HTTPException(status_code=400, detail="Thiếu company_code.")

    company = get_company_or_404(db, company_code, user)

    user_row = get_user_by_username(db, user.name)
    if user_row is None:
        raise HTTPException(status_code=403, detail="Session user không tồn tại.")

    if year is None:
        job = enqueue_job(
            db, kind=JobKind.BATCH_RUN, payload={"company_code": company_code},
            created_by=user_row.id, company_id=company.id, period_year=None,
        )
    else:
        year = int(year)
        job = enqueue_job(
            db, kind=JobKind.RUN_CHECKS,
            payload={"company_code": company_code, "year": year},
            created_by=user_row.id, company_id=company.id, period_year=year,
        )
    log_access(db, username=user.name, action=ACTION_RUN_CHECKS, company_code=company_code,
               detail=("batch" if year is None else f"year={year}"))
    return {"job_id": job.id, "status_url": f"/jobs/{job.id}", "company_code": company_code, "year": year}


@router.get("/chat/export-query")
def chat_export_query(
    sql: str = Query(...),
    title: str | None = Query(default=None),
    user: SessionUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> Response:
    """Xuất Excel tùy biến từ câu SQL (do tool export_query_excel sinh link).

    Guard chỉ-đọc chạy lại ở đây (validate_sql trong build_query_export) — an toàn
    dù SQL đến từ query string.
    """
    from app.pipeline.export import build_query_export

    # Cùng ranh giới DN với query_sql — officer chỉ xuất được DN được phân công.
    allowed_codes = allowed_company_codes(db, user)
    try:
        payload = build_query_export(
            db, sql, title=title, row_cap=int(get_setting("sql_export_row_cap")),
            allowed_codes=allowed_codes,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Không xuất được: {e}") from e
    log_access(db, username=user.name, action=ACTION_EXPORT_QUERY, detail=sql)
    return Response(
        content=payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=audit-hq_truy-van-tuy-bien.xlsx"},
    )


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

    # Ranh giới phân quyền DN cho tool (officer: chỉ DN được phân công; admin: None).
    allowed_codes = allowed_company_codes(db, user)

    try:
        body = await request.json()
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Body JSON lỗi: {e}") from e
    user_message: str = (body.get("message") or "").strip()
    conv_id: int | None = body.get("conversation_id")
    page_context: dict = body.get("page_context") or {}

    # Mention @DN/@finding → resolve + xác thực lại phạm vi rồi nhét vào ngữ cảnh.
    mentions = _resolve_mentions(db, body.get("mentions"), allowed_codes)
    if mentions:
        page_context = {**page_context, "mentions": mentions}

    if not user_message:
        raise HTTPException(status_code=400, detail="Message không được trống.")

    conv = _resume_or_create_conversation(
        db, user, conv_id,
        page_context=page_context, mentions=mentions, user_message=user_message,
    )

    _save_msg(db, conv.id, "user", user_message)
    db.commit()
    conv_id_resolved = conv.id

    system_msgs = build_messages_system(
        page_context=page_context,
        enable_cache=get_setting("prompt_cache_enabled") and cache_supports_anthropic(),
        conversation_company=_conversation_company(db, conv),
    )
    history = _load_history(db, conv.id)
    messages = system_msgs + history

    client = make_client()
    fb_client = make_fallback_client()
    fb_model = fallback_model_for("default")
    model = get_setting("model_default")
    temperature = float(get_setting("temperature"))
    max_tokens = int(get_setting("max_tokens"))

    tool_call_cap = int(get_setting("tool_call_cap"))

    def event_gen() -> Iterator[str]:
        # Reuse messages mutate-in-place qua các iteration tool loop.
        total_in = 0
        total_out = 0
        used_model = model
        try:
            for _ in range(tool_call_cap):
                t0 = time.time()
                # Fallback chỉ kích hoạt nếu primary lỗi TRƯỚC khi stream bắt đầu.
                # Khi stream đã yield chunk thì giữ nguyên — không retry mid-stream.
                stream, used_model = call_with_fallback(
                    primary_client=client,
                    primary_model=model,
                    fallback_client=fb_client,
                    fallback_model=fb_model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    tools=get_tool_schemas(),
                    stream=True,
                    stream_options={"include_usage": True},
                    return_model=True,
                )

                acc_text = ""
                # Gom tool-call. Khoá theo `index`; provider KHÔNG đánh index (vd Gemini phát
                # nhiều call song song với index=None) → khoá theo `id` để args các call khác
                # nhau không bị nối thành '{...}{...}'. Chunk nối tiếp (không id/index) → nối
                # vào call gần nhất.
                acc_tool_calls: dict = {}
                last_tc_key = None
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
                            if tc.index is not None:
                                key = tc.index
                            elif tc.id:
                                key = tc.id
                            elif last_tc_key is not None:
                                key = last_tc_key
                            else:
                                key = 0
                            last_tc_key = key
                            slot = acc_tool_calls.setdefault(
                                key, {"id": "", "name": "", "arguments": ""}
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
                            "function": {
                                "name": tc["name"],
                                "arguments": _clean_tool_args(tc["arguments"]),
                            },
                        }
                        for tc in sorted(acc_tool_calls.values(), key=lambda x: x.get("id", ""))
                    ]
                    # Append assistant turn vào messages history + audit.
                    _save_msg(
                        db, conv_id_resolved, "assistant",
                        content=acc_text,
                        tool_args_json=json.dumps(tool_calls_payload, ensure_ascii=False),
                        tool_call_id="batch",
                        model=used_model,
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
                        result_str = run_tool(name, args, db, allowed_codes)
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
                        evt = {"name": name, "preview": result_str[:300]}
                        evt.update(_extract_download(result_str))
                        yield _sse("tool_result", evt)
                        # Tool đề xuất hành động (chạy kiểm tra) → phát event riêng để FE
                        # render nút xác nhận. Cán bộ bấm mới enqueue (AI không tự chạy).
                        action = _extract_action(result_str)
                        if action is not None:
                            yield _sse("action_proposal", action)
                    db.commit()
                    continue

                # finish_reason in ("stop", "length") → final answer
                clean_text = apply_guardrails(acc_text, conv_id=conv_id_resolved)
                _save_msg(
                    db, conv_id_resolved, "assistant",
                    content=clean_text,
                    model=used_model,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    latency_ms=latency_ms,
                )
                db.commit()
                yield _sse("done", {
                    "conversation_id": conv_id_resolved,
                    "usage": {
                        "model": used_model,
                        "fallback_used": used_model != model,
                        "tokens_in": total_in,
                        "tokens_out": total_out,
                    },
                })
                return
            yield _sse("error", {"detail": f"Vượt {tool_call_cap} vòng tool call."})
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
