"""Tests cho cost estimator + rate limit + daily budget."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException

from app.ai.cost import DEFAULT_PRICE, PRICING, estimate_cost
from app.ai.limits import check_daily_budget, check_rate_limit, usage_today
from app.models import AiConversation, AiMessage

# ─────────────────────────── cost ───────────────────────────

def test_estimate_cost_known_model():
    cb = estimate_cost("~anthropic/claude-sonnet-latest", 1_000_000, 500_000)
    assert cb.pricing_known is True
    # input 3.0 per 1M, output 15.0 per 1M
    assert cb.input_usd == pytest.approx(3.0)
    assert cb.output_usd == pytest.approx(7.5)
    assert cb.total_usd == pytest.approx(10.5)


def test_estimate_cost_unknown_model_uses_default():
    cb = estimate_cost("self-host/llama-3", 1_000_000, 1_000_000)
    assert cb.pricing_known is False
    assert cb.input_usd == pytest.approx(DEFAULT_PRICE["input"])
    assert cb.output_usd == pytest.approx(DEFAULT_PRICE["output"])


def test_estimate_cost_zero_tokens():
    cb = estimate_cost("openai/gpt-4o", 0, 0)
    assert cb.total_usd == 0.0


def test_estimate_cost_none_tokens_handled():
    cb = estimate_cost("openai/gpt-4o", None, None)
    assert cb.total_usd == 0.0


def test_pricing_table_has_floats():
    for model, prices in PRICING.items():
        assert "input" in prices, f"{model} thiếu input price"
        assert "output" in prices, f"{model} thiếu output price"
        assert prices["input"] >= 0
        assert prices["output"] >= 0


# ─────────────────────────── rate limit ───────────────────────────

def _make_conv_with_user_msgs(session, count: int, user: str = "admin", age_minutes: int = 5):
    """Helper: tạo conv + N user message tuổi `age_minutes` phút."""
    from app.ai.config import bust_cache
    bust_cache()
    conv = AiConversation(user=user, page_url_seed=None)
    session.add(conv)
    session.flush()
    ts = datetime.now(UTC) - timedelta(minutes=age_minutes)
    for i in range(count):
        session.add(AiMessage(
            conversation_id=conv.id, role="user", content=f"msg {i}",
            created_at=ts + timedelta(seconds=i),
        ))
    session.commit()
    return conv


def test_check_rate_limit_under_threshold(session):
    """Default rate_limit = 50. Tạo 10 msg → OK."""
    _make_conv_with_user_msgs(session, count=10)
    check_rate_limit("admin", session)  # không raise


def test_check_rate_limit_over_threshold(session):
    """Set rate_limit = 5, tạo 5 msg trong giờ → raise 429."""
    from app.ai.config import set_setting
    set_setting("rate_limit_per_hour", 5, "test", db=session)
    _make_conv_with_user_msgs(session, count=5)
    with pytest.raises(HTTPException) as exc:
        check_rate_limit("admin", session)
    assert exc.value.status_code == 429


def test_check_rate_limit_disabled_when_zero(session):
    """rate_limit = 0 → bypass cả khi có nhiều msg."""
    from app.ai.config import set_setting
    set_setting("rate_limit_per_hour", 0, "test", db=session)
    _make_conv_with_user_msgs(session, count=100)
    check_rate_limit("admin", session)  # không raise


def test_check_rate_limit_excludes_old_messages(session):
    """Message > 1h cũ không tính."""
    from app.ai.config import set_setting
    set_setting("rate_limit_per_hour", 3, "test", db=session)
    # 10 msg cũ (2h)
    _make_conv_with_user_msgs(session, count=10, age_minutes=120)
    # Mới 0 msg → OK
    check_rate_limit("admin", session)


def test_check_rate_limit_isolates_by_user(session):
    """User A vượt giới hạn không ảnh hưởng user B."""
    from app.ai.config import set_setting
    set_setting("rate_limit_per_hour", 3, "test", db=session)
    _make_conv_with_user_msgs(session, count=5, user="alice")
    # User bob chưa có msg → OK
    check_rate_limit("bob", session)
    with pytest.raises(HTTPException) as exc:
        check_rate_limit("alice", session)
    assert exc.value.status_code == 429


# ─────────────────────────── budget ───────────────────────────

def _add_cost_msg(session, cost: float, age_hours: int = 0, conv_id: int | None = None):
    """Helper: thêm 1 assistant msg với cost."""
    if conv_id is None:
        conv = AiConversation(user="admin")
        session.add(conv)
        session.flush()
        conv_id = conv.id
    ts = datetime.now(UTC) - timedelta(hours=age_hours)
    msg = AiMessage(
        conversation_id=conv_id, role="assistant", content="reply",
        cost_usd=cost, created_at=ts,
    )
    session.add(msg)
    session.commit()
    return conv_id


def test_check_daily_budget_under_threshold(session):
    """Default 20 USD, chi 5 → OK."""
    from app.ai.config import bust_cache
    bust_cache()
    _add_cost_msg(session, cost=5.0)
    check_daily_budget(session)  # không raise


def test_check_daily_budget_exceeded(session):
    from app.ai.config import set_setting
    set_setting("daily_budget_usd", 1.0, "test", db=session)
    _add_cost_msg(session, cost=1.5)
    with pytest.raises(HTTPException) as exc:
        check_daily_budget(session)
    assert exc.value.status_code == 503
    assert "1.50" in exc.value.detail or "1.5" in exc.value.detail


def test_check_daily_budget_disabled_when_zero(session):
    from app.ai.config import set_setting
    set_setting("daily_budget_usd", 0.0, "test", db=session)
    _add_cost_msg(session, cost=1000.0)
    check_daily_budget(session)  # không raise


def test_check_daily_budget_excludes_yesterday(session):
    """Cost > 24h trước không tính."""
    from app.ai.config import set_setting
    set_setting("daily_budget_usd", 5.0, "test", db=session)
    _add_cost_msg(session, cost=10.0, age_hours=48)
    check_daily_budget(session)  # OK vì cost cũ


# ─────────────────────────── usage_today ───────────────────────────

def test_usage_today_aggregates(session):
    from app.ai.config import bust_cache
    bust_cache()
    conv_id = _add_cost_msg(session, cost=0.5)
    # Add another msg same conv
    session.add(AiMessage(
        conversation_id=conv_id, role="assistant", content="b",
        tokens_in=100, tokens_out=50, cost_usd=0.3,
    ))
    # User msg (no cost)
    session.add(AiMessage(
        conversation_id=conv_id, role="user", content="q",
    ))
    session.commit()
    stats = usage_today(session)
    assert stats["cost_usd"] == pytest.approx(0.8, abs=0.001)
    assert stats["messages"] == 3
    assert stats["tokens_in"] == 100
    assert stats["users"] == 1
