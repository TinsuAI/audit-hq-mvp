"""Rate limit + daily budget cap guards cho AI endpoint.

Cả 2 helper raise HTTPException khi vượt — gọi sớm trong handler trước
khi tốn token. Đọc threshold từ ai_settings DB (cache 30s).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.config import get_setting
from app.models import AiConversation, AiMessage, AiUsage


def check_rate_limit(user: str, db: Session) -> None:
    """Đếm user-message của user này trong 1 giờ qua. Vượt → 429."""
    limit = int(get_setting("rate_limit_per_hour", db=db))
    if limit <= 0:
        return  # 0 = tắt rate limit
    cutoff = datetime.now(UTC) - timedelta(hours=1)
    count = db.scalar(
        select(func.count())
        .select_from(AiMessage)
        .join(AiConversation, AiConversation.id == AiMessage.conversation_id)
        .where(
            AiConversation.user == user,
            AiMessage.role == "user",
            AiMessage.created_at >= cutoff,
        )
    ) or 0
    if count >= limit:
        raise HTTPException(
            status_code=429,
            detail=f"Vượt giới hạn {limit} tin nhắn/giờ. Thử lại sau ít phút.",
        )


def _today_start() -> datetime:
    return datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


def spent_today(db: Session) -> float:
    """Tổng chi phí hôm nay theo SỔ — gồm cả chat lẫn sinh tổng quan (ADR #21)."""
    return float(
        db.scalar(
            select(func.coalesce(func.sum(AiUsage.cost_usd), 0.0))
            .where(AiUsage.created_at >= _today_start())
        ) or 0.0
    )


def check_daily_budget(db: Session) -> None:
    """Chi tiêu hôm nay theo sổ. Vượt daily_budget_usd → 503.

    Đọc `ai_usage` chứ không cộng `ai_messages`: chi phí sinh tổng quan là một
    loại lời gọi tính tiền và phải vào trần như chat.
    """
    budget = float(get_setting("daily_budget_usd", db=db))
    if budget <= 0:
        return  # 0 = tắt budget cap
    spent = spent_today(db)
    if spent >= budget:
        raise HTTPException(
            status_code=503,
            detail=f"Đã dùng hết ngân sách ngày: ${spent:.2f}/${budget:.2f}. "
                   f"Liên hệ admin điều chỉnh /admin/ai.",
        )


def usage_today(db: Session) -> dict:
    """Stats cho /admin/ai audit section — tổng + tách theo loại lời gọi."""
    today_start = _today_start()
    by_kind: dict[str, dict] = {}
    for kind, cost, t_in, t_out, n in db.execute(
        select(
            AiUsage.kind,
            func.coalesce(func.sum(AiUsage.cost_usd), 0.0),
            func.coalesce(func.sum(AiUsage.tokens_in), 0),
            func.coalesce(func.sum(AiUsage.tokens_out), 0),
            func.count(AiUsage.id),
        ).where(AiUsage.created_at >= today_start).group_by(AiUsage.kind)
    ).all():
        by_kind[kind] = {
            "cost_usd": round(float(cost), 4),
            "tokens_in": int(t_in),
            "tokens_out": int(t_out),
            "calls": int(n),
        }
    empty = {"cost_usd": 0.0, "tokens_in": 0, "tokens_out": 0, "calls": 0}
    chat = by_kind.get(AiUsage.KIND_CHAT, empty)
    overview = by_kind.get(AiUsage.KIND_OVERVIEW, empty)

    # `messages` vẫn đếm tin nhắn chat (nhãn trên giao diện là "tin nhắn"), tách
    # khỏi số LỜI GỌI của sổ — một lượt chat có vòng tool sinh nhiều lời gọi.
    msg_count = db.scalar(
        select(func.count(AiMessage.id)).where(AiMessage.created_at >= today_start)
    ) or 0
    distinct_users = db.scalar(
        select(func.count(func.distinct(AiConversation.user)))
        .where(AiConversation.started_at >= today_start)
    ) or 0

    return {
        "cost_usd": round(chat["cost_usd"] + overview["cost_usd"], 4),
        "tokens_in": chat["tokens_in"] + overview["tokens_in"],
        "tokens_out": chat["tokens_out"] + overview["tokens_out"],
        "calls": chat["calls"] + overview["calls"],
        "by_kind": {"chat": chat, "overview": overview},
        "messages": int(msg_count),
        "users": int(distinct_users),
        "budget_usd": float(get_setting("daily_budget_usd", db=db)),
        "rate_limit_per_hour": int(get_setting("rate_limit_per_hour", db=db)),
    }
