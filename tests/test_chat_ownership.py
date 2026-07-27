"""Phân quyền chat (yêu cầu pilot):
1. AI chỉ truy cập DN của user — đã phủ ở test_scoping.py (run_tool/allowed_codes).
2. User CHỈ xem/sửa/xoá được cuộc trò chuyện của CHÍNH MÌNH — file này.

Cưỡng chế ở: /api/chat/conversations (list lọc theo user), .../{id}/messages (404
nếu khác chủ), DELETE .../{id} (404), và trang /chat/{id} (404). 404 cố ý để không
lộ sự tồn tại cuộc của người khác.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import AiConversation, AiMessage, Company


def _setup_db():
    import app.database as dbmod
    from app.auth_users import create_user, seed_default_admin

    new_engine = dbmod.create_engine(
        "sqlite://", connect_args={"check_same_thread": False},
        poolclass=StaticPool, future=True,
    )
    new_session = dbmod.sessionmaker(
        bind=new_engine, autoflush=False, autocommit=False, future=True
    )
    dbmod.engine = new_engine
    dbmod.SessionLocal = new_session
    Base.metadata.create_all(new_engine)
    ids = {}
    with new_session() as db:
        seed_default_admin(db, "admin", "admin")
        a = Company(code="DN_001", name="A", tax_id="1")
        b = Company(code="DN_002", name="B", tax_id="2")
        db.add_all([a, b])
        db.flush()
        off1 = create_user(db, "off1", "off1pw", "officer")
        off1.companies = [a]
        off2 = create_user(db, "off2", "off2pw", "officer")
        off2.companies = [b]
        db.flush()

        c1 = AiConversation(user="off1", title="Cuộc của off1", page_url_seed="/companies/DN_001")
        c2 = AiConversation(user="off2", title="Cuộc của off2", page_url_seed="/companies/DN_002")
        db.add_all([c1, c2])
        db.flush()
        db.add_all([
            AiMessage(conversation_id=c1.id, role="user", content="hỏi off1"),
            AiMessage(conversation_id=c2.id, role="user", content="hỏi off2"),
        ])
        db.commit()
        ids["c_off1"] = c1.id
        ids["c_off2"] = c2.id
    return new_engine, new_session, ids


def _teardown(new_engine):
    new_engine.dispose()
    import app.database as dbmod
    dbmod.engine = engine
    dbmod.SessionLocal = SessionLocal


def _login(client: TestClient, username: str, password: str) -> None:
    r = client.post(
        "/login", data={"user": username, "password": password}, follow_redirects=False
    )
    assert r.status_code == 303


def test_conversation_list_only_own():
    new_engine, _, ids = _setup_db()
    try:
        client = TestClient(app)
        _login(client, "off2", "off2pw")
        r = client.get("/api/chat/conversations")
        assert r.status_code == 200
        returned = {c["id"] for c in r.json()["conversations"]}
        assert returned == {ids["c_off2"]}  # KHÔNG thấy cuộc của off1
    finally:
        _teardown(new_engine)


def test_cannot_read_others_conversation_messages():
    new_engine, _, ids = _setup_db()
    try:
        client = TestClient(app)
        _login(client, "off2", "off2pw")
        # Cuộc của off1 → 404 (như không tồn tại).
        assert client.get(f"/api/chat/conversations/{ids['c_off1']}/messages").status_code == 404
        # Cuộc của chính mình → 200.
        assert client.get(f"/api/chat/conversations/{ids['c_off2']}/messages").status_code == 200
    finally:
        _teardown(new_engine)


def test_cannot_delete_others_conversation():
    new_engine, new_session, ids = _setup_db()
    try:
        client = TestClient(app)
        _login(client, "off2", "off2pw")
        assert client.delete(f"/api/chat/conversations/{ids['c_off1']}").status_code == 404
        # Cuộc của off1 vẫn còn nguyên sau khi off2 thử xoá.
        with new_session() as db:
            assert db.get(AiConversation, ids["c_off1"]) is not None
    finally:
        _teardown(new_engine)


def test_chat_page_route_enforces_ownership():
    new_engine, _, ids = _setup_db()
    try:
        client = TestClient(app)
        _login(client, "off2", "off2pw")
        assert client.get("/chat").status_code == 200          # trang gốc
        assert client.get(f"/chat/{ids['c_off2']}").status_code == 200   # cuộc của mình
        assert client.get(f"/chat/{ids['c_off1']}").status_code == 404   # cuộc người khác
        assert client.get("/chat/999999").status_code == 404            # không tồn tại
    finally:
        _teardown(new_engine)


def test_admin_can_read_any_conversation():
    # Admin giám sát: đọc được cuộc của mọi user (API + trang) + list thấy hết
    # khi TẮT "Chỉ của tôi" (mine=0). Mặc định mine=1 — xem test dưới.
    new_engine, _, ids = _setup_db()
    try:
        client = TestClient(app)
        _login(client, "admin", "admin")
        assert client.get(f"/api/chat/conversations/{ids['c_off1']}/messages").status_code == 200
        assert client.get(f"/api/chat/conversations/{ids['c_off2']}/messages").status_code == 200
        assert client.get(f"/chat/{ids['c_off1']}").status_code == 200
        r = client.get("/api/chat/conversations?mine=0")
        seen = {c["id"] for c in r.json()["conversations"]}
        assert {ids["c_off1"], ids["c_off2"]} <= seen
        # owner đính kèm để FE phân biệt + ẩn nút xoá cuộc người khác.
        owners = {c["id"]: c["owner"] for c in r.json()["conversations"]}
        assert owners[ids["c_off1"]] == "off1"
    finally:
        _teardown(new_engine)


def test_admin_list_defaults_to_own_conversations_only():
    """"Chỉ của tôi" BẬT mặc định — giám sát cuộc người khác phải bấm tắt."""
    new_engine, _, ids = _setup_db()
    try:
        client = TestClient(app)
        _login(client, "admin", "admin")
        seen = {c["id"] for c in client.get("/api/chat/conversations").json()["conversations"]}
        assert ids["c_off1"] not in seen
        assert ids["c_off2"] not in seen
    finally:
        _teardown(new_engine)


def test_admin_cannot_delete_others_conversation():
    # "View được hết" KHÔNG kèm xoá: xoá vẫn owner-only (tránh mất lịch sử người khác).
    new_engine, new_session, ids = _setup_db()
    try:
        client = TestClient(app)
        _login(client, "admin", "admin")
        assert client.delete(f"/api/chat/conversations/{ids['c_off1']}").status_code == 404
        with new_session() as db:
            assert db.get(AiConversation, ids["c_off1"]) is not None
    finally:
        _teardown(new_engine)
