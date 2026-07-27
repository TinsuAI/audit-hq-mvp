"""CHAT-4 (ADR #20) — chủ đề cuộc vào system prompt + khoá gửi khi mất quyền DN.

Hai nửa tách nhau: chủ đề là một khối text trong system prompt (test thuần hàm),
khoá gửi là 403 ở đường gửi tin + cờ `can_send` cho giao diện (test qua endpoint).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool

from app.ai.system_prompt import build_conversation_topic, build_messages_system
from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import AiConversation, AiMessage, Company

# ───────────────────────── chủ đề trong system prompt ─────────────────────────


def test_topic_block_names_company():
    block = build_conversation_topic("DN_AAA", "Công ty Alfa")
    assert "Công ty Alfa" in block and "DN_AAA" in block
    # Chủ đề resolve câu hỏi trống ngữ cảnh…
    assert "KHÔNG nêu rõ doanh nghiệp" in block
    # …nhưng KHÔNG được đọc thành giới hạn truy cập.
    assert "KHÔNG phải giới hạn truy cập" in block


def test_topic_block_empty_without_company():
    assert build_conversation_topic(None, None) == ""


def test_system_prompt_carries_topic():
    msgs = build_messages_system(
        page_context={"dn_code": "DN_BBB"},
        conversation_company={"code": "DN_AAA", "name": "Alfa"},
    )
    text = msgs[0]["content"]
    assert "Chủ đề cuộc trò chuyện" in text
    # Ngữ cảnh trang vẫn còn — chủ đề bổ sung chứ không thay thế.
    assert "DN_BBB" in text


def test_system_prompt_without_topic_unchanged():
    msgs = build_messages_system(page_context={"dn_code": "DN_BBB"})
    assert "Chủ đề cuộc trò chuyện" not in msgs[0]["content"]


def test_topic_survives_cache_segmentation():
    msgs = build_messages_system(
        page_context={"dn_code": "DN_BBB"},
        enable_cache=True,
        conversation_company={"code": "DN_AAA", "name": "Alfa"},
    )
    blocks = [b["text"] for b in msgs[0]["content"]]
    assert any("Chủ đề cuộc trò chuyện" in b for b in blocks)


# ───────────────────────── khoá gửi khi mất quyền DN ─────────────────────────


@pytest.fixture
def world():
    import app.database as dbmod
    from app.ai.config import bust_cache, set_setting
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
        # Bật AI + khoá API giả: nếu không, `/api/chat` trả 503 ở guard đầu và
        # test khoá-gửi sẽ xanh vì lý do khác hẳn.
        bust_cache()
        set_setting("enabled", True, "test", db=db)
        set_setting("api_key", "sk-test", "test", db=db)
        a = Company(code="DN_AAA", slug="dn-aaa", name="Alfa", tax_id="1")
        b = Company(code="DN_BBB", slug="dn-bbb", name="Beta", tax_id="2")
        db.add_all([a, b])
        db.flush()
        off = create_user(db, "off", "offpw", "officer")
        off.companies = [a]  # KHÔNG có Beta
        db.flush()
        kept = AiConversation(user="off", title="còn quyền", company_id=a.id)
        lost = AiConversation(user="off", title="mất quyền", company_id=b.id)
        free = AiConversation(user="off", title="chưa gắn")
        db.add_all([kept, lost, free])
        db.flush()
        for c in (kept, lost, free):
            db.add(AiMessage(conversation_id=c.id, role="user", content="nội dung cũ"))
        db.commit()
        ids |= {"kept": kept.id, "lost": lost.id, "free": free.id}
    try:
        yield ids
    finally:
        bust_cache()   # cấu hình AI của test không rò sang test khác
        new_engine.dispose()
        dbmod.engine, dbmod.SessionLocal = engine, SessionLocal


def _client(u="off", p="offpw") -> TestClient:
    c = TestClient(app)
    assert c.post("/login", data={"user": u, "password": p},
                  follow_redirects=False).status_code == 303
    return c


def test_transcript_still_readable_after_losing_company(world):
    r = _client().get(f"/api/chat/conversations/{world['lost']}/messages")
    assert r.status_code == 200
    body = r.json()
    assert [m["content"] for m in body["messages"]] == ["nội dung cũ"]
    assert body["can_send"] is False
    assert "không còn được phân công" in body["lock_reason"]
    assert "Beta" in body["lock_reason"]


def test_send_refused_with_reason(world):
    for path in ("/api/chat", "/api/chat/stream"):
        r = _client().post(path, json={
            "message": "hỏi tiếp", "conversation_id": world["lost"], "page_context": {},
        })
        assert r.status_code == 403, path
        assert "không còn được phân công" in r.json()["detail"]


def test_conversation_in_scope_is_not_locked(world):
    body = _client().get(f"/api/chat/conversations/{world['kept']}/messages").json()
    assert body["can_send"] is True
    assert body["lock_reason"] is None


def test_unassigned_conversation_is_not_locked(world):
    body = _client().get(f"/api/chat/conversations/{world['free']}/messages").json()
    assert body["can_send"] is True


def test_admin_reading_others_conversation_cannot_send(world):
    body = _client("admin", "admin").get(
        f"/api/chat/conversations/{world['kept']}/messages"
    ).json()
    assert body["can_send"] is False
    assert "cán bộ khác" in body["lock_reason"]
