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
from app.models import AiConversation, AiMessage


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


def check_daily_budget(db: Session) -> None:
    """Tổng cost_usd hôm nay. Vượt daily_budget_usd → 503."""
    budget = float(get_setting("daily_budget_usd", db=db))
    if budget <= 0:
        return  # 0 = tắt budget cap
    today_start = datetime.now(UTC).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    spent = db.scalar(
        select(func.coalesce(func.sum(AiMessage.cost_usd), 0.0))
        .where(AiMessage.created_at >= today_start)
    ) or 0.0
    if spent >= budget:
        raise HTTPException(
            status_code=503,
            detail=f"Đã dùng hết ngân sách ngày: ${spent:.2f}/${budget:.2f}. "
                   f"Liên hệ admin điều chỉnh /admin/ai.",
        )


def usage_today(db: Session) -> dict:
    """Stats cho /admin/ai audit section."""
    today_start = datetime.now(UTC).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    row = db.execute(
        select(
            func.coalesce(func.sum(AiMessage.cost_usd), 0.0),
            func.coalesce(func.sum(AiMessage.tokens_in), 0),
            func.coalesce(func.sum(AiMessage.tokens_out), 0),
            func.count(AiMessage.id),
        ).where(AiMessage.created_at >= today_start)
    ).one()
    spent, tokens_in, tokens_out, msg_count = row

    distinct_users = db.scalar(
        select(func.count(func.distinct(AiConversation.user)))
        .where(AiConversation.started_at >= today_start)
    ) or 0

    return {
        "cost_usd": round(float(spent), 4),
        "tokens_in": int(tokens_in),
        "tokens_out": int(tokens_out),
        "messages": int(msg_count),
        "users": int(distinct_users),
        "budget_usd": float(get_setting("daily_budget_usd", db=db)),
        "rate_limit_per_hour": int(get_setting("rate_limit_per_hour", db=db)),
    }
