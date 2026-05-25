"""Retention cron — xóa AI conversation/message cũ theo settings.

Chạy dưới dạng asyncio background task trong lifespan. Kiểm tra 1 lần mỗi 24h.
`history_retention_days=0` → tắt xóa (giữ vĩnh viễn).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

log = logging.getLogger(__name__)

_INTERVAL_S = 24 * 60 * 60  # check once per day


async def run_retention_loop() -> None:
    """Background loop chạy cleanup mỗi 24h."""
    await asyncio.sleep(60)  # initial delay để app boot xong
    while True:
        try:
            _cleanup_once()
        except Exception:
            log.exception("AI retention cleanup failed (non-fatal)")
        await asyncio.sleep(_INTERVAL_S)


def _cleanup_once() -> None:
    from sqlalchemy import delete

    from app.ai.config import get_setting
    from app.database import SessionLocal
    from app.models import AiConversation, AiMessage

    history_days = int(get_setting("history_retention_days") or 0)
    audit_days = int(get_setting("audit_retention_days") or 0)

    if not history_days and not audit_days:
        return

    now = datetime.utcnow()
    with SessionLocal() as db:
        deleted_convs = 0
        if history_days > 0:
            cutoff = now - timedelta(days=history_days)
            # CASCADE sẽ xóa messages kèm theo khi FK enabled
            result = db.execute(
                delete(AiConversation).where(AiConversation.started_at < cutoff)
            )
            deleted_convs = result.rowcount
        # Audit messages không gắn với conversation (orphan nếu có) — xóa theo audit_days
        if audit_days > 0:
            audit_cutoff = now - timedelta(days=audit_days)
            db.execute(
                delete(AiMessage).where(AiMessage.created_at < audit_cutoff)
            )
        db.commit()

    if deleted_convs:
        log.info("Retention: xóa %d conversation cũ hơn %d ngày", deleted_convs, history_days)
