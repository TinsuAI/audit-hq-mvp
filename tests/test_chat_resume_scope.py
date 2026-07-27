"""CHAT-3 (ADR #20) — nối lại cuộc gần nhất CÙNG doanh nghiệp trong 24 giờ.

Quy tắc 24h nằm ở `/api/chat/resume` (server) chứ không rải trong JS, nên test
được thẳng: cùng DN + còn hạn → nối; quá hạn → không; DN khác → không bao giờ.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import AiConversation, AiMessage, Company


@pytest.fixture
def world():
    import app.database as dbmod
    from app.auth_users import create_user, seed_default_admin

    new_engine = dbmod.create_engine(
        "sqlite://", connect_args={"check_same_thread": False},
        poolclass=StaticPool, future=True,
    )
    new_session = dbmod.sessionmaker(
        bind=new_engine, autoflush=False, autocommit=False, future=True
    )
    dbmod.engine, dbmod.SessionLocal = new_engine, new_session
    Base.metadata.create_all(new_engine)
    ids = {}
    with new_session() as db:
        seed_default_admin(db, "admin", "admin")
        a = Company(code="DN_AAA", slug="dn-aaa", name="Alfa", tax_id="1")
        b = Company(code="DN_BBB", slug="dn-bbb", name="Beta", tax_id="2")
        db.add_all([a, b])
        db.flush()
        off = create_user(db, "off", "offpw", "officer")
        off.companies = [a, b]
        db.commit()
        ids["a"], ids["b"] = a.id, b.id
        ids["session"] = new_session
    try:
        yield ids
    finally:
        new_engine.dispose()
        dbmod.engine, dbmod.SessionLocal = engine, SessionLocal


def _conv(world, *, company_id, minutes_ago, user="off", title="t") -> int:
    """Cuộc có MỘT tin nhắn tại mốc `minutes_ago` phút trước (naive UTC như app)."""
    at = datetime.utcnow() - timedelta(minutes=minutes_ago)
    with world["session"]() as db:
        c = AiConversation(user=user, title=title, company_id=company_id, started_at=at)
        db.add(c)
        db.flush()
        db.add(AiMessage(conversation_id=c.id, role="user", content="hỏi", created_at=at))
        db.commit()
        return c.id


def _client() -> TestClient:
    c = TestClient(app)
    assert c.post("/login", data={"user": "off", "password": "offpw"},
                  follow_redirects=False).status_code == 303
    return c


def test_resumes_recent_conversation_of_same_company(world):
    cid = _conv(world, company_id=world["a"], minutes_ago=30)
    r = _client().get("/api/chat/resume?company_code=DN_AAA").json()
    assert r["conversation_id"] == cid
    assert r["company_name"] == "Alfa"


def test_does_not_resume_past_24h(world):
    _conv(world, company_id=world["a"], minutes_ago=25 * 60)
    assert _client().get("/api/chat/resume?company_code=DN_AAA").json()["conversation_id"] is None


def test_never_resumes_other_company(world):
    _conv(world, company_id=world["b"], minutes_ago=10)
    assert _client().get("/api/chat/resume?company_code=DN_AAA").json()["conversation_id"] is None


def test_picks_most_recently_active_not_newest_row(world):
    """"Gần nhất" = hoạt động cuối, không phải dòng tạo sau."""
    old_row_active_now = _conv(world, company_id=world["a"], minutes_ago=20 * 60)
    with world["session"]() as db:
        db.add(AiMessage(conversation_id=old_row_active_now, role="user", content="mới",
                         created_at=datetime.utcnow() - timedelta(minutes=2)))
        db.commit()
    _conv(world, company_id=world["a"], minutes_ago=10 * 60)
    r = _client().get("/api/chat/resume?company_code=DN_AAA").json()
    assert r["conversation_id"] == old_row_active_now


def test_resume_without_company_uses_unassigned_group(world):
    unassigned = _conv(world, company_id=None, minutes_ago=5)
    _conv(world, company_id=world["a"], minutes_ago=1)
    assert _client().get("/api/chat/resume").json()["conversation_id"] == unassigned


def test_resume_ignores_other_users_conversations(world):
    _conv(world, company_id=world["a"], minutes_ago=5, user="admin")
    assert _client().get("/api/chat/resume?company_code=DN_AAA").json()["conversation_id"] is None


def test_resume_refuses_company_outside_scope(world):
    """Officer không có quyền DN → không nối, không lộ cuộc nào."""
    import app.database as dbmod
    with dbmod.SessionLocal() as db:
        from app.auth_users import create_user
        narrow = create_user(db, "off3", "off3pw", "officer")
        narrow.companies = []
        db.commit()
    _conv(world, company_id=world["a"], minutes_ago=5, user="off3")
    c = TestClient(app)
    assert c.post("/login", data={"user": "off3", "password": "off3pw"},
                  follow_redirects=False).status_code == 303
    assert c.get("/api/chat/resume?company_code=DN_AAA").json()["conversation_id"] is None


def test_conversation_without_messages_falls_back_to_started_at(world):
    with world["session"]() as db:
        c = AiConversation(user="off", title="trống", company_id=world["a"],
                           started_at=datetime.utcnow() - timedelta(minutes=5))
        db.add(c)
        db.commit()
        cid = c.id
    assert _client().get("/api/chat/resume?company_code=DN_AAA").json()["conversation_id"] == cid


def test_list_exposes_last_message_at(world):
    cid = _conv(world, company_id=world["a"], minutes_ago=5)
    convs = _client().get("/api/chat/conversations").json()["conversations"]
    row = next(c for c in convs if c["id"] == cid)
    assert row["last_message_at"] is not None


def test_sidebar_markup_has_scope_and_mismatch_chrome(world):
    html = _client().get("/companies").text
    assert 'id="ai-scope"' in html
    assert 'id="ai-history-company"' in html
    assert 'id="ai-scope-mismatch"' in html
