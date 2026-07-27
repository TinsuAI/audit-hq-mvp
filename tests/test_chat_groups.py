"""CHAT-2 (ADR #20) — nhóm cuộc trò chuyện theo doanh nghiệp + đổi doanh nghiệp.

Phủ API: nhóm + số đếm + thứ tự (chưa gán xếp cuối), phân trang 30/section,
tìm kiếm xuyên nhóm, công tắc "Chỉ của tôi" của quản trị, và phân quyền của
thao tác đổi doanh nghiệp (chặn ở API, không chỉ ở giao diện).
"""

from __future__ import annotations

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
        zeta = Company(code="DN_ZZZ", slug="dn-zzz", name="Zeta", tax_id="1")
        alfa = Company(code="DN_AAA", slug="dn-aaa", name="Alfa", tax_id="2")
        db.add_all([zeta, alfa])
        db.flush()
        off = create_user(db, "off", "offpw", "officer")
        off.companies = [alfa]
        other = create_user(db, "off2", "off2pw", "officer")
        other.companies = [zeta]
        db.flush()
        ids["alfa"], ids["zeta"] = alfa.id, zeta.id

        # off: 2 cuộc Alfa, 1 cuộc chưa gán. off2: 1 cuộc Zeta.
        c1 = AiConversation(user="off", title="Alfa một", company_id=alfa.id)
        c2 = AiConversation(user="off", title="Alfa hai", company_id=alfa.id)
        c3 = AiConversation(user="off", title="Chưa gán gì")
        c4 = AiConversation(user="off2", title="Zeta của off2", company_id=zeta.id)
        db.add_all([c1, c2, c3, c4])
        db.flush()
        db.add(AiMessage(conversation_id=c1.id, role="user", content="xin chào"))
        db.commit()
        ids |= {"c1": c1.id, "c2": c2.id, "c3": c3.id, "c4": c4.id}
    try:
        yield ids
    finally:
        new_engine.dispose()
        dbmod.engine, dbmod.SessionLocal = engine, SessionLocal


def _client(username: str, password: str) -> TestClient:
    c = TestClient(app)
    assert c.post("/login", data={"user": username, "password": password},
                  follow_redirects=False).status_code == 303
    return c


# ───────────────────────── nhóm + số đếm ─────────────────────────

def test_groups_count_and_unassigned_last(world):
    groups = _client("off", "offpw").get("/api/chat/conversation-groups").json()["groups"]
    assert [g["company_name"] for g in groups] == ["Alfa", "Chưa gán doanh nghiệp"]
    assert [g["count"] for g in groups] == [2, 1]
    assert groups[-1]["company_id"] is None


def test_groups_sorted_by_company_name(world):
    """Zeta tạo trước Alfa nhưng sắp theo TÊN, không theo thứ tự tạo."""
    client = _client("admin", "admin")
    groups = client.get("/api/chat/conversation-groups?mine=0").json()["groups"]
    named = [g["company_name"] for g in groups if g["company_id"] is not None]
    assert named == ["Alfa", "Zeta"]


def test_officer_groups_exclude_other_users(world):
    groups = _client("off", "offpw").get("/api/chat/conversation-groups").json()["groups"]
    assert all(g["company_name"] != "Zeta" for g in groups)


# ───────────────────────── lọc theo nhóm + phân trang ─────────────────────────

def test_list_filtered_by_company(world):
    client = _client("off", "offpw")
    r = client.get(f"/api/chat/conversations?company_id={world['alfa']}").json()
    assert {c["id"] for c in r["conversations"]} == {world["c1"], world["c2"]}
    assert r["total"] == 2
    assert r["has_more"] is False


def test_list_filtered_unassigned_group(world):
    r = _client("off", "offpw").get("/api/chat/conversations?company_id=none").json()
    assert {c["id"] for c in r["conversations"]} == {world["c3"]}


def test_list_pagination_keeps_order(world):
    client = _client("off", "offpw")
    first = client.get(
        f"/api/chat/conversations?company_id={world['alfa']}&limit=1&offset=0"
    ).json()
    assert [c["id"] for c in first["conversations"]] == [world["c2"]]  # mới nhất trước
    assert first["has_more"] is True
    second = client.get(
        f"/api/chat/conversations?company_id={world['alfa']}&limit=1&offset=1"
    ).json()
    assert [c["id"] for c in second["conversations"]] == [world["c1"]]
    assert second["has_more"] is False


def test_bad_company_id_rejected(world):
    assert _client("off", "offpw").get("/api/chat/conversations?company_id=abc").status_code == 400


# ───────────────────────── tìm kiếm xuyên nhóm ─────────────────────────

def test_search_matches_title_across_groups(world):
    client = _client("off", "offpw")
    r = client.get("/api/chat/conversations?q=hai").json()
    assert {c["id"] for c in r["conversations"]} == {world["c2"]}
    # Nhóm cũng thu hẹp theo cùng bộ lọc → FE biết section nào cần mở.
    groups = client.get("/api/chat/conversation-groups?q=hai").json()["groups"]
    assert [(g["company_name"], g["count"]) for g in groups] == [("Alfa", 1)]


def test_search_matches_company_name(world):
    r = _client("off", "offpw").get("/api/chat/conversations?q=Alfa").json()
    assert {c["id"] for c in r["conversations"]} == {world["c1"], world["c2"]}


# ───────────────────────── công tắc "Chỉ của tôi" ─────────────────────────

def test_admin_mine_toggle(world):
    client = _client("admin", "admin")
    assert client.get("/api/chat/conversations").json()["total"] == 0
    seen = {c["id"] for c in client.get("/api/chat/conversations?mine=0").json()["conversations"]}
    assert {world["c1"], world["c4"]} <= seen


def test_officer_cannot_see_others_by_flipping_mine(world):
    """`mine=0` KHÔNG phải cửa hậu — officer vẫn chỉ thấy cuộc của mình."""
    r = _client("off", "offpw").get("/api/chat/conversations?mine=0").json()
    assert world["c4"] not in {c["id"] for c in r["conversations"]}


# ───────────────────────── đổi doanh nghiệp của cuộc ─────────────────────────

def test_owner_can_change_company(world):
    client = _client("off", "offpw")
    r = client.patch(f"/api/chat/conversations/{world['c3']}", json={"company_code": "DN_AAA"})
    assert r.status_code == 200
    assert r.json()["company_code"] == "DN_AAA"
    groups = client.get("/api/chat/conversation-groups").json()["groups"]
    assert [(g["company_name"], g["count"]) for g in groups] == [("Alfa", 3)]


def test_change_company_keeps_transcript(world):
    client = _client("off", "offpw")
    client.patch(f"/api/chat/conversations/{world['c1']}", json={"company_code": None})
    msgs = client.get(f"/api/chat/conversations/{world['c1']}/messages").json()
    assert [m["content"] for m in msgs["messages"]] == ["xin chào"]
    assert msgs["company_code"] is None


def test_officer_cannot_assign_company_outside_scope(world):
    """Chặn ở API — không dựa vào việc ô chọn chỉ đổ DN hợp lệ."""
    client = _client("off", "offpw")
    r = client.patch(f"/api/chat/conversations/{world['c3']}", json={"company_code": "DN_ZZZ"})
    assert r.status_code == 404  # 404 cố ý: không lộ DN ngoài phạm vi có tồn tại
    assert client.get("/api/chat/conversations?company_id=none").json()["total"] == 1


def test_cannot_change_others_conversation(world):
    r = _client("off", "offpw").patch(
        f"/api/chat/conversations/{world['c4']}", json={"company_code": "DN_AAA"}
    )
    assert r.status_code == 404


def test_admin_can_change_any_conversation(world):
    r = _client("admin", "admin").patch(
        f"/api/chat/conversations/{world['c4']}", json={"company_code": "DN_AAA"}
    )
    assert r.status_code == 200
    assert r.json()["company_code"] == "DN_AAA"


def test_chat_page_renders_group_chrome(world):
    """Trang /chat có ô "Chỉ của tôi" + hộp thoại đổi DN để JS gắn vào."""
    html = _client("admin", "admin").get("/chat").text
    assert 'id="chat-mine"' in html
    assert 'id="chat-move-dialog"' in html
    assert 'id="chat-move-select"' in html


def test_companies_endpoint_scoped(world):
    off = _client("off", "offpw").get("/api/chat/companies").json()["companies"]
    assert [c["code"] for c in off] == ["DN_AAA"]
    admin = _client("admin", "admin").get("/api/chat/companies").json()["companies"]
    assert [c["code"] for c in admin] == ["DN_AAA", "DN_ZZZ"]  # sắp theo tên
