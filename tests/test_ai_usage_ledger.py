"""TQ-1 (ADR #21 mục 10-11) — sổ chi phí `ai_usage`.

Điểm chịu lực: trần ngày phải thấy CẢ chi phí sinh tổng quan. Trước đó nó cộng
`ai_messages.cost_usd`, còn overview ghi trên `check_overviews` — bảng upsert
một dòng mỗi bộ ba, nên sinh lại ba lần trong ngày chỉ còn chi phí lần cuối.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.ai.limits import check_daily_budget, check_rate_limit, spent_today, usage_today
from app.ai.usage import conversation_ref, overview_ref, record_usage
from app.database import Base
from app.models import AiConversation, AiMessage, AiUsage


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with factory() as s:
        yield s
    engine.dispose()


@pytest.fixture(autouse=True)
def _settings(db):
    """Trần ngày $1, rate limit 5/giờ — đọc từ chính session của test."""
    from app.ai.config import bust_cache, set_setting

    bust_cache()
    set_setting("daily_budget_usd", 1.0, "test", db=db)
    set_setting("rate_limit_per_hour", 5, "test", db=db)
    db.commit()
    yield
    bust_cache()


def _spend(db, kind, cost, *, when=None, user="off"):
    row = record_usage(
        db, kind=kind, ref="r", model="m", tokens_in=10, tokens_out=5,
        cost_usd=cost, user=user,
    )
    if when is not None:
        row.created_at = when
    db.commit()
    return row


# ───────────────────────── ghi sổ ─────────────────────────

def test_record_usage_writes_one_row(db):
    record_usage(db, kind=AiUsage.KIND_CHAT, ref=conversation_ref(7), model="m",
                 tokens_in=100, tokens_out=20, cost_usd=0.01, user="off")
    db.commit()
    row = db.scalars(select(AiUsage)).one()
    assert (row.kind, row.ref, row.tokens_in, row.tokens_out) == ("chat", "conv:7", 100, 20)
    assert row.cost_usd == 0.01
    assert row.user == "off"


def test_overview_ref_shape():
    assert overview_ref(9, 2025, "C1.1") == "overview:9:2025:C1.1"


# ───────────────────────── trần ngày ─────────────────────────

def test_daily_budget_counts_both_kinds(db):
    _spend(db, AiUsage.KIND_CHAT, 0.4)
    check_daily_budget(db)          # 0.40 < 1.00 → qua
    _spend(db, AiUsage.KIND_OVERVIEW, 0.7)
    with pytest.raises(HTTPException) as e:
        check_daily_budget(db)      # 1.10 ≥ 1.00 → chặn
    assert e.value.status_code == 503


def test_regenerating_same_overview_accumulates(db):
    """Sinh lại cùng một tổng quan ba lần trong ngày → ba dòng sổ.

    Đây là lý do sổ tồn tại: `check_overviews` chỉ giữ chi phí lần cuối.
    """
    for _ in range(3):
        record_usage(db, kind=AiUsage.KIND_OVERVIEW, ref=overview_ref(1, 2025, "C1.6"),
                     model="m", tokens_in=1, tokens_out=1, cost_usd=0.5, user="off")
    db.commit()
    assert db.scalar(select(AiUsage).where(AiUsage.ref == overview_ref(1, 2025, "C1.6"))) is not None
    assert len(db.scalars(select(AiUsage)).all()) == 3
    assert spent_today(db) == pytest.approx(1.5)
    with pytest.raises(HTTPException):
        check_daily_budget(db)


def test_yesterday_spend_does_not_count(db):
    _spend(db, AiUsage.KIND_CHAT, 5.0,
           when=datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1))
    assert spent_today(db) == 0.0
    check_daily_budget(db)


def test_budget_zero_disables_cap(db):
    from app.ai.config import bust_cache, set_setting

    _spend(db, AiUsage.KIND_OVERVIEW, 99.0)
    set_setting("daily_budget_usd", 0.0, "test", db=db)
    db.commit()
    bust_cache()
    check_daily_budget(db)  # không raise


# ───────────────── rate limit giờ vẫn là guard của CHAT ─────────────────

def test_hourly_rate_limit_ignores_overview(db):
    """Một lượt gộp 12 lời gọi tổng quan không được khoá trợ lý của cán bộ."""
    for _ in range(20):
        _spend(db, AiUsage.KIND_OVERVIEW, 0.0)
    check_rate_limit("off", db)  # không raise

    conv = AiConversation(user="off", title="t")
    db.add(conv)
    db.flush()
    for _ in range(5):
        db.add(AiMessage(conversation_id=conv.id, role="user", content="hỏi"))
    db.commit()
    with pytest.raises(HTTPException) as e:
        check_rate_limit("off", db)
    assert e.value.status_code == 429


# ───────────────────────── thống kê /admin/ai ─────────────────────────

def test_usage_today_splits_by_kind(db):
    _spend(db, AiUsage.KIND_CHAT, 0.10)
    _spend(db, AiUsage.KIND_CHAT, 0.20)
    _spend(db, AiUsage.KIND_OVERVIEW, 0.30)
    u = usage_today(db)
    assert u["cost_usd"] == pytest.approx(0.60)
    assert u["by_kind"]["chat"]["cost_usd"] == pytest.approx(0.30)
    assert u["by_kind"]["chat"]["calls"] == 2
    assert u["by_kind"]["overview"]["cost_usd"] == pytest.approx(0.30)
    assert u["by_kind"]["overview"]["calls"] == 1
    assert u["calls"] == 3


def test_usage_today_empty_ledger(db):
    u = usage_today(db)
    assert u["cost_usd"] == 0.0
    assert u["by_kind"]["chat"]["calls"] == 0
    assert u["by_kind"]["overview"]["calls"] == 0


# ───────────────────────── seed của migration ─────────────────────────

def test_migration_seed_statements(db):
    """Chạy đúng 2 câu INSERT của migration f2a3b4c5d6e7 trên schema hiện tại."""
    import re
    from pathlib import Path

    from sqlalchemy import text

    from app.models import CheckOverview, Company

    c = Company(code="DN_X", slug="dn-x", name="X", tax_id="1")
    db.add(c)
    db.flush()
    db.add_all([
        # Có chi phí → vào sổ.
        CheckOverview(company_id=c.id, period_year=2025, check_code="C1.1", content="x",
                      model="m", tokens_in=10, tokens_out=5, cost_usd=0.02),
        # Chưa từng gọi LLM (cost 0) → KHÔNG vào sổ.
        CheckOverview(company_id=c.id, period_year=2025, check_code="C1.2", content="x",
                      cost_usd=0.0),
    ])
    conv = AiConversation(user="off", title="t")
    db.add(conv)
    db.flush()
    db.add_all([
        AiMessage(conversation_id=conv.id, role="assistant", content="hôm nay",
                  model="m", tokens_in=7, tokens_out=3, cost_usd=0.05),
        AiMessage(conversation_id=conv.id, role="user", content="không tính tiền"),
        AiMessage(conversation_id=conv.id, role="assistant", content="hôm qua",
                  model="m", tokens_in=7, tokens_out=3, cost_usd=0.09,
                  created_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(days=1)),
    ])
    db.commit()

    src = Path("migrations/versions/f2a3b4c5d6e7_ai_usage_ledger.py").read_text()
    stmts = re.findall(r'sa\.text\("""(.*?)"""\)', src, re.S)
    assert len(stmts) == 2, "migration phải còn đúng 2 câu seed"
    for s in stmts:
        db.execute(text(s))
    db.commit()

    rows = db.scalars(select(AiUsage).order_by(AiUsage.kind)).all()
    kinds = sorted(r.kind for r in rows)
    assert kinds == ["chat", "overview"], "một dòng chat hôm nay + một dòng overview"
    chat = next(r for r in rows if r.kind == "chat")
    assert chat.ref == f"conv:{conv.id}"
    assert chat.user == "off"
    assert chat.cost_usd == pytest.approx(0.05)   # tin nhắn hôm qua KHÔNG được seed
    ov = next(r for r in rows if r.kind == "overview")
    assert ov.ref == f"overview:{c.id}:2025:C1.1"
    assert ov.cost_usd == pytest.approx(0.02)
