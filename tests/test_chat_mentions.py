"""Mention @DN/@finding cũng phải theo phân quyền DN.

Hai tầng chặn:
- Endpoint /api/chat/mentions: officer chỉ thấy DN của mình + finding thuộc DN đó.
- _resolve_mentions (server-side): KHÔNG tin code/id client gửi — DN ngoài phạm vi
  bị bỏ, nên mention không phải lối lách để truy cập DN người khác.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import Company, Finding


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
        a = Company(code="DN_001", name="Alpha Foods", tax_id="1")
        b = Company(code="DN_002", name="Beta Steel", tax_id="2")
        db.add_all([a, b])
        db.flush()
        fa = Finding(company_id=a.id, period_year=2024, check_code="C1.1",
                     severity="critical", title="Lệch NVL Alpha")
        fb = Finding(company_id=b.id, period_year=2024, check_code="C1.1",
                     severity="critical", title="Lệch NVL Beta")
        db.add_all([fa, fb])
        off1 = create_user(db, "off1", "off1pw", "officer")
        off1.companies = [a]
        db.flush()
        ids.update(dn1=a.id, dn2=b.id, f1=fa.id, f2=fb.id)
        db.commit()
    return new_engine, new_session, ids


def _teardown(new_engine):
    new_engine.dispose()
    import app.database as dbmod
    dbmod.engine = engine
    dbmod.SessionLocal = SessionLocal


def _login(client: TestClient, username: str, password: str) -> None:
    r = client.post("/login", data={"user": username, "password": password}, follow_redirects=False)
    assert r.status_code == 303


def test_mentions_endpoint_scoped_to_officer():
    new_engine, _, _ = _setup_db()
    try:
        client = TestClient(app)
        _login(client, "off1", "off1pw")
        items = client.get("/api/chat/mentions?q=").json()["items"]
        codes = {i["code"] for i in items if i["type"] == "company"}
        f_companies = {i["company_code"] for i in items if i["type"] == "finding"}
        assert codes == {"DN_001"}                 # KHÔNG thấy DN_002
        assert f_companies <= {"DN_001"}           # finding cũng chỉ của DN mình
        # Gõ đúng tên DN ngoài phạm vi vẫn không ra.
        assert client.get("/api/chat/mentions?q=Beta").json()["items"] == []
    finally:
        _teardown(new_engine)


def test_mentions_endpoint_admin_sees_all():
    new_engine, _, _ = _setup_db()
    try:
        client = TestClient(app)
        _login(client, "admin", "admin")
        items = client.get("/api/chat/mentions?q=").json()["items"]
        codes = {i["code"] for i in items if i["type"] == "company"}
        assert {"DN_001", "DN_002"} <= codes
    finally:
        _teardown(new_engine)


def test_resolve_mentions_drops_out_of_scope():
    from app.routes.ai import _resolve_mentions

    new_engine, new_session, ids = _setup_db()
    try:
        with new_session() as db:
            allowed = {"DN_001"}  # officer off1
            raw = [
                {"type": "company", "code": "DN_001"},
                {"type": "company", "code": "DN_002"},   # ngoài phạm vi → bỏ
                {"type": "finding", "id": ids["f1"]},
                {"type": "finding", "id": ids["f2"]},     # finding DN_002 → bỏ
            ]
            out = _resolve_mentions(db, raw, allowed)
            kinds = {(m["type"], m.get("code") or m.get("company_code")) for m in out}
            assert ("company", "DN_001") in kinds
            assert ("finding", "DN_001") in kinds
            assert all(k[1] == "DN_001" for k in kinds)   # tuyệt đối không lọt DN_002
    finally:
        _teardown(new_engine)


def test_resolve_mentions_admin_unrestricted():
    from app.routes.ai import _resolve_mentions

    new_engine, new_session, ids = _setup_db()
    try:
        with new_session() as db:
            raw = [
                {"type": "company", "code": "DN_002"},
                {"type": "finding", "id": ids["f2"]},
            ]
            out = _resolve_mentions(db, raw, None)  # admin: không giới hạn
            assert len(out) == 2
    finally:
        _teardown(new_engine)
