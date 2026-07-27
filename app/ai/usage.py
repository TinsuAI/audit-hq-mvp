"""Ghi sổ chi phí AI (ADR #21 mục 10).

Một hàm ghi duy nhất để mọi lời gọi LLM tính tiền đi qua cùng một cửa. Trần
ngày và thống kê `/admin/ai` đọc sổ này; telemetry trên `ai_messages` /
`check_overviews` vẫn giữ (chi phí của chính dòng đó).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import AiUsage


def record_usage(
    db: Session,
    *,
    kind: str,
    model: str | None,
    tokens_in: int | None,
    tokens_out: int | None,
    cost_usd: float | None,
    ref: str | None = None,
    user: str | None = None,
) -> AiUsage:
    """Thêm MỘT dòng sổ. Không commit — để chung transaction với thứ vừa sinh ra nó."""
    row = AiUsage(
        kind=kind,
        ref=ref,
        model=model,
        tokens_in=int(tokens_in or 0),
        tokens_out=int(tokens_out or 0),
        cost_usd=float(cost_usd or 0.0),
        user=user,
    )
    db.add(row)
    db.flush()
    return row


def conversation_ref(conversation_id: int) -> str:
    return f"conv:{conversation_id}"


def overview_ref(company_id: int, period_year: int, check_code: str) -> str:
    return f"overview:{company_id}:{period_year}:{check_code}"
