"""CHAT-1 (ADR #20) — cuộc trò chuyện gắn MỘT doanh nghiệp.

Phủ: chuỗi ưu tiên nhận diện lúc tạo, gán muộn từ mention, ranh giới phân quyền,
nhãn trả về ở API danh sách, và backfill của migration.

Nhận diện chạy trong `_resume_or_create_conversation`, gọi từ cả `/api/chat` lẫn
`/api/chat/stream`. Test gọi thẳng helper thay vì đi qua endpoint để khỏi phải
dựng LLM giả — endpoint chỉ là hai lời gọi tới đúng hàm này.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.pool import StaticPool

from app.ai.conversation_scope import (
    late_assign_company,
    resolve_company_for_new_conversation,
)
from app.auth import SessionUser
from app.database import Base
from app.models import AiConversation, Company, Finding


@pytest.fixture
def db():
    import app.database as dbmod

    engine = dbmod.create_engine(
        "sqlite://", connect_args={"check_same_thread": False},
        poolclass=StaticPool, future=True,
    )
    Base.metadata.create_all(engine)
    session_factory = dbmod.sessionmaker(
        bind=engine, autoflush=False, autocommit=False, future=True
    )
    with session_factory() as s:
        yield s
    engine.dispose()


@pytest.fixture
def world(db):
    """2 DN, 1 admin, 1 officer chỉ có quyền DN A, 1 finding thuộc DN B."""
    from app.auth_users import create_user, seed_default_admin

    seed_default_admin(db, "admin", "admin")
    a = Company(code="DN_AAA", slug="dn-aaa", name="Công ty A", tax_id="1")
    b = Company(code="DN_BBB", slug="dn-bbb", name="Công ty B", tax_id="2")
    db.add_all([a, b])
    db.flush()
    off = create_user(db, "off", "offpw", "officer")
    off.companies = [a]
    f_a = Finding(company_id=a.id, period_year=2025, check_code="C1.1", severity="critical",
                  title="Phát hiện A")
    f_b = Finding(company_id=b.id, period_year=2025, check_code="C1.1", severity="critical",
                  title="Phát hiện B")
    db.add_all([f_a, f_b])
    db.commit()
    return {
        "a": a, "b": b,
        "f_a": f_a.id, "f_b": f_b.id,
        "admin": SessionUser(name="admin", role="admin"),
        "officer": SessionUser(name="off", role="officer"),
    }


# ───────────────────────── chuỗi ưu tiên ─────────────────────────

def test_page_company_wins_when_no_ui_choice(db, world):
    got = resolve_company_for_new_conversation(
        db, world["admin"], {"dn_code": "dn-aaa", "url": "/companies/dn-aaa"}
    )
    assert got == world["a"].id


def test_company_resolves_by_code_not_only_slug(db, world):
    # Link nội bộ / AI cũ dùng `code`; URL người dùng dùng `slug` — nhận cả hai.
    got = resolve_company_for_new_conversation(db, world["admin"], {"dn_code": "DN_AAA"})
    assert got == world["a"].id


def test_ui_choice_beats_page_company(db, world):
    got = resolve_company_for_new_conversation(
        db, world["admin"], {"scope_company_code": "dn-bbb", "dn_code": "dn-aaa"}
    )
    assert got == world["b"].id


def test_finding_page_assigns_finding_company(db, world):
    # Trang /findings/{id} không có dn_code — đây chính là ca cuộc cũ mất nhãn.
    got = resolve_company_for_new_conversation(
        db, world["admin"], {"finding_id": world["f_b"], "url": f"/findings/{world['f_b']}"}
    )
    assert got == world["b"].id


def test_page_company_beats_finding(db, world):
    got = resolve_company_for_new_conversation(
        db, world["admin"], {"dn_code": "dn-aaa", "finding_id": world["f_b"]}
    )
    assert got == world["a"].id


def test_no_signal_leaves_unassigned(db, world):
    assert resolve_company_for_new_conversation(db, world["admin"], {"url": "/jobs"}) is None
    assert resolve_company_for_new_conversation(db, world["admin"], None) is None


def test_unknown_or_dead_signal_leaves_unassigned(db, world):
    assert resolve_company_for_new_conversation(db, world["admin"], {"dn_code": "khong-co"}) is None
    # finding id không sống qua một lần chạy lại kiểm tra.
    assert resolve_company_for_new_conversation(db, world["admin"], {"finding_id": 999999}) is None
    assert resolve_company_for_new_conversation(db, world["admin"], {"finding_id": "abc"}) is None


# ───────────────────────── ranh giới phân quyền ─────────────────────────

def test_officer_cannot_be_scoped_to_company_outside_assignment(db, world):
    off = world["officer"]
    assert resolve_company_for_new_conversation(db, off, {"dn_code": "dn-bbb"}) is None
    assert resolve_company_for_new_conversation(db, off, {"scope_company_code": "DN_BBB"}) is None
    assert resolve_company_for_new_conversation(db, off, {"finding_id": world["f_b"]}) is None
    # DN được phân công thì vẫn gắn bình thường.
    assert resolve_company_for_new_conversation(db, off, {"dn_code": "dn-aaa"}) == world["a"].id


def test_out_of_scope_page_does_not_fall_through_to_finding(db, world):
    """Trang DN ngoài quyền + phát hiện trong quyền → KHÔNG gắn.

    Chuỗi ưu tiên dừng ở khớp ĐẦU, và "khớp" nghĩa là trang trỏ tới DN có thật.
    Nếu tín hiệu trang bị chặn vì quyền mà vẫn rơi xuống nhánh sau thì nhãn sẽ
    nói về DN khác hẳn với DN cán bộ đang xem.
    """
    got = resolve_company_for_new_conversation(
        db, world["officer"], {"dn_code": "dn-bbb", "finding_id": world["f_a"]}
    )
    assert got is None


# ───────────────────────── gán muộn từ mention ─────────────────────────

def test_late_assign_on_single_company_mention(db, world):
    conv = AiConversation(user="admin", title="t")
    db.add(conv)
    db.flush()
    assigned = late_assign_company(
        db, conv, [{"type": "company", "code": "DN_AAA", "name": "Công ty A"}], world["admin"]
    )
    assert assigned is True
    assert conv.company_id == world["a"].id


def test_late_assign_skipped_for_two_companies(db, world):
    conv = AiConversation(user="admin", title="t")
    db.add(conv)
    db.flush()
    assigned = late_assign_company(db, conv, [
        {"type": "company", "code": "DN_AAA"},
        {"type": "company", "code": "DN_BBB"},
    ], world["admin"])
    assert assigned is False
    assert conv.company_id is None


def test_late_assign_does_not_overwrite_existing_label(db, world):
    conv = AiConversation(user="admin", title="t", company_id=world["a"].id)
    db.add(conv)
    db.flush()
    assigned = late_assign_company(
        db, conv, [{"type": "company", "code": "DN_BBB"}], world["admin"]
    )
    assert assigned is False
    assert conv.company_id == world["a"].id


def test_late_assign_ignores_finding_mentions(db, world):
    """`@finding` KHÔNG phải `@DN` — gán muộn chỉ nhận tín hiệu tường minh về DN."""
    conv = AiConversation(user="admin", title="t")
    db.add(conv)
    db.flush()
    assigned = late_assign_company(
        db, conv,
        [{"type": "finding", "id": world["f_b"], "company_code": "DN_BBB"}],
        world["admin"],
    )
    assert assigned is False
    assert conv.company_id is None


def test_late_assign_blocked_by_scope(db, world):
    conv = AiConversation(user="off", title="t")
    db.add(conv)
    db.flush()
    assigned = late_assign_company(
        db, conv, [{"type": "company", "code": "DN_BBB"}], world["officer"]
    )
    assert assigned is False
    assert conv.company_id is None


def test_same_company_mentioned_twice_counts_as_one(db, world):
    conv = AiConversation(user="admin", title="t")
    db.add(conv)
    db.flush()
    assigned = late_assign_company(db, conv, [
        {"type": "company", "code": "DN_AAA"},
        {"type": "company", "code": "DN_AAA"},
    ], world["admin"])
    assert assigned is True
    assert conv.company_id == world["a"].id


# ───────────── helper dùng chung của /api/chat và /api/chat/stream ─────────────

def test_resume_or_create_labels_new_conversation(db, world):
    from app.routes.ai import _resume_or_create_conversation

    conv = _resume_or_create_conversation(
        db, world["admin"], None,
        page_context={"dn_code": "dn-aaa", "url": "/companies/dn-aaa"},
        mentions=[], user_message="năm 2025 có gì đáng chú ý?",
    )
    assert conv.company_id == world["a"].id
    assert conv.page_url_seed == "/companies/dn-aaa"


def test_resume_or_create_late_assigns_on_resume(db, world):
    from app.routes.ai import _resume_or_create_conversation

    conv = AiConversation(user="admin", title="t")
    db.add(conv)
    db.flush()
    resumed = _resume_or_create_conversation(
        db, world["admin"], conv.id,
        page_context={}, mentions=[{"type": "company", "code": "DN_BBB"}],
        user_message="@Công ty B thế nào?",
    )
    assert resumed.id == conv.id
    assert resumed.company_id == world["b"].id


def test_resume_keeps_label_when_page_context_points_elsewhere(db, world):
    """Nhãn đã gắn KHÔNG đổi theo trang cán bộ tình cờ đang mở."""
    from app.routes.ai import _resume_or_create_conversation

    conv = AiConversation(user="admin", title="t", company_id=world["a"].id)
    db.add(conv)
    db.flush()
    resumed = _resume_or_create_conversation(
        db, world["admin"], conv.id,
        page_context={"dn_code": "dn-bbb"}, mentions=[], user_message="hỏi tiếp",
    )
    assert resumed.company_id == world["a"].id


# ───────────────────────── API danh sách trả nhãn ─────────────────────────

def test_list_api_returns_company_label():
    """Chip trên mỗi dòng đọc từ dữ liệu — cuộc mở từ trang phát hiện có nhãn."""
    from fastapi.testclient import TestClient

    import app.database as dbmod
    from app.auth_users import seed_default_admin
    from app.database import SessionLocal as orig_session
    from app.database import engine as orig_engine
    from app.main import app

    new_engine = dbmod.create_engine(
        "sqlite://", connect_args={"check_same_thread": False},
        poolclass=StaticPool, future=True,
    )
    new_session = dbmod.sessionmaker(
        bind=new_engine, autoflush=False, autocommit=False, future=True
    )
    dbmod.engine, dbmod.SessionLocal = new_engine, new_session
    Base.metadata.create_all(new_engine)
    try:
        with new_session() as s:
            seed_default_admin(s, "admin", "admin")
            c = Company(code="DN_AAA", slug="dn-aaa", name="Công ty A", tax_id="1")
            s.add(c)
            s.flush()
            # Cuộc mở từ trang phát hiện: seed KHÔNG chứa /companies/... nhưng
            # nhãn vẫn đúng vì nó nằm trên dòng cuộc.
            s.add_all([
                AiConversation(user="admin", title="có nhãn", company_id=c.id,
                               page_url_seed="/findings/36330"),
                AiConversation(user="admin", title="chưa gắn", page_url_seed="/jobs"),
            ])
            s.commit()

        client = TestClient(app)
        assert client.post("/login", data={"user": "admin", "password": "admin"},
                           follow_redirects=False).status_code == 303
        convs = {c["title"]: c for c in client.get("/api/chat/conversations").json()["conversations"]}
        assert convs["có nhãn"]["company_code"] == "DN_AAA"
        assert convs["có nhãn"]["company_name"] == "Công ty A"
        assert convs["có nhãn"]["company_slug"] == "dn-aaa"
        assert convs["chưa gắn"]["company_code"] is None
    finally:
        new_engine.dispose()
        dbmod.engine, dbmod.SessionLocal = orig_engine, orig_session


# ───────────────────────── backfill của migration ─────────────────────────

def _run_backfill(db):
    """Chạy đúng 2 câu UPDATE của migration e1f2a3b4c5d6 trên schema hiện tại."""
    import re
    from pathlib import Path

    src = Path("migrations/versions/e1f2a3b4c5d6_ai_conversation_company.py").read_text()
    stmts = re.findall(r'sa\.text\("""(.*?)"""\)', src, re.S)
    assert len(stmts) == 2, "migration phải còn đúng 2 câu backfill"
    for s in stmts:
        db.execute(text(s))
    db.commit()


def test_migration_backfill_three_branches(db, world):
    rows = {
        "slug": AiConversation(user="admin", title="t", page_url_seed="/companies/dn-aaa"),
        "slug_sub": AiConversation(user="admin", title="t",
                                   page_url_seed="/companies/dn-aaa/data?year=2025"),
        "code": AiConversation(user="admin", title="t", page_url_seed="/companies/DN_BBB"),
        "qs": AiConversation(user="admin", title="t", page_url_seed="/companies/dn-bbb?year=2025"),
        "finding": AiConversation(user="admin", title="t",
                                  page_url_seed=f"/findings/{world['f_b']}"),
        "dead_finding": AiConversation(user="admin", title="t", page_url_seed="/findings/999999"),
        "other": AiConversation(user="admin", title="t", page_url_seed="/jobs/12"),
        "none": AiConversation(user="admin", title="t", page_url_seed=None),
    }
    db.add_all(rows.values())
    db.commit()
    ids = {k: v.id for k, v in rows.items()}

    _run_backfill(db)

    def company_of(key):
        return db.get(AiConversation, ids[key]).company_id

    assert company_of("slug") == world["a"].id
    assert company_of("slug_sub") == world["a"].id
    assert company_of("code") == world["b"].id
    assert company_of("qs") == world["b"].id
    assert company_of("finding") == world["b"].id
    assert company_of("dead_finding") is None
    assert company_of("other") is None
    assert company_of("none") is None
