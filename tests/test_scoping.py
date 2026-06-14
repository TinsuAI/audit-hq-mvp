"""Phân quyền theo DN — officer chỉ thấy DN được phân công, ở MỌI lối vào.

Hai tầng:
- Helper + AI tool (`session` fixture) — gồm test TEMP VIEW scoping an-toàn-aggregate.
- Route end-to-end (TestClient) — officer vs admin qua HTTP.
"""

from __future__ import annotations

import json

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool

from app.ai.sql_tool import run_query
from app.ai.tools import run_tool
from app.auth import SessionUser
from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import Company, Finding, User
from app.scoping import (
    allowed_company_codes,
    allowed_company_ids,
    can_access_company_id,
    get_company_or_404,
)

ADMIN = SessionUser(name="admin1", role="admin")
OFFICER = SessionUser(name="off1", role="officer")


def _company(session, code: str) -> Company:
    c = Company(code=code, name=f"Cty {code}", tax_id=code)
    session.add(c)
    session.flush()
    return c


def _user(session, username: str, role: str, companies=()) -> User:
    u = User(username=username, password_hash="x", role=role)
    u.companies = list(companies)
    session.add(u)
    session.flush()
    return u


def _finding(session, company_id: int, check_code="C1.1", severity="critical") -> Finding:
    f = Finding(
        company_id=company_id, period_year=2024,
        check_code=check_code, severity=severity, title="x",
    )
    session.add(f)
    session.flush()
    return f


# ───────────────────────────── helpers ─────────────────────────────

def test_allowed_sets_officer_admin_unknown(session):
    a = _company(session, "DN_001")
    _company(session, "DN_002")
    _user(session, "off1", "officer", [a])
    _user(session, "admin1", "admin")
    session.commit()

    assert allowed_company_codes(session, OFFICER) == {"DN_001"}
    assert allowed_company_ids(session, OFFICER) == {a.id}
    # Admin = sentinel "không giới hạn".
    assert allowed_company_codes(session, ADMIN) is None
    assert allowed_company_ids(session, ADMIN) is None
    # User không tồn tại trong DB → không có quyền gì.
    ghost = SessionUser(name="ghost", role="officer")
    assert allowed_company_codes(session, ghost) == set()
    assert allowed_company_ids(session, ghost) == set()


def test_get_company_or_404_enforces_scope(session):
    a = _company(session, "DN_001")
    _company(session, "DN_002")
    _user(session, "off1", "officer", [a])
    _user(session, "admin1", "admin")
    session.commit()

    assert get_company_or_404(session, "DN_001", OFFICER).code == "DN_001"
    # DN ngoài phạm vi → 404 (không lộ tồn tại), giống hệt DN không có thật.
    with pytest.raises(HTTPException) as ei:
        get_company_or_404(session, "DN_002", OFFICER)
    assert ei.value.status_code == 404
    with pytest.raises(HTTPException) as ei2:
        get_company_or_404(session, "DN_404", OFFICER)
    assert ei2.value.status_code == 404
    # Admin xem được tất cả.
    assert get_company_or_404(session, "DN_002", ADMIN).code == "DN_002"
    assert can_access_company_id(session, ADMIN, a.id) is True


# ─────────────────────────── AI structured tools ───────────────────────────

def test_tool_list_companies_scoped(session):
    _company(session, "DN_001")
    _company(session, "DN_002")
    session.commit()

    scoped = json.loads(run_tool("list_companies", "{}", session, {"DN_001"}))
    assert {c["code"] for c in scoped["companies"]} == {"DN_001"}
    # Admin (allowed_codes=None) thấy tất cả.
    full = json.loads(run_tool("list_companies", "{}", session, None))
    assert {c["code"] for c in full["companies"]} == {"DN_001", "DN_002"}


def test_tool_search_findings_blocks_unassigned(session):
    _company(session, "DN_001")
    b = _company(session, "DN_002")
    _finding(session, b.id)
    session.commit()

    blocked = json.loads(
        run_tool("search_findings", json.dumps({"company_code": "DN_002"}), session, {"DN_001"})
    )
    assert "error" in blocked  # "không tìm thấy DN" — không lộ DN_002
    ok = json.loads(
        run_tool("search_findings", json.dumps({"company_code": "DN_001"}), session, {"DN_001"})
    )
    assert "error" not in ok and ok["count"] == 0


def test_tool_get_finding_blocks_unassigned(session):
    b = _company(session, "DN_002")
    f = _finding(session, b.id)
    session.commit()

    blocked = json.loads(
        run_tool("get_finding", json.dumps({"finding_id": f.id}), session, {"DN_001"})
    )
    assert "error" in blocked
    # Admin xem được.
    ok = json.loads(run_tool("get_finding", json.dumps({"finding_id": f.id}), session, None))
    assert ok["id"] == f.id


def test_tool_injected_allowed_codes_cannot_be_overridden(session):
    """LLM tự nhét allowed_codes vào args không được mở rộng phạm vi."""
    _company(session, "DN_001")
    _company(session, "DN_002")
    session.commit()
    out = json.loads(run_tool(
        "list_companies", json.dumps({"allowed_codes": ["DN_001", "DN_002"]}), session, {"DN_001"}
    ))
    assert {c["code"] for c in out["companies"]} == {"DN_001"}


# ─────────────── query_sql TEMP VIEW — an toàn cả với aggregate ───────────────

def test_query_sql_temp_view_aggregate_safe(session):
    a = _company(session, "DN_001")
    b = _company(session, "DN_002")
    _finding(session, a.id, "C1.1")
    _finding(session, b.id, "C1.1")
    _finding(session, b.id, "C2.3", "warning")
    session.commit()

    sql = "SELECT company_code, COUNT(*) AS n FROM v_findings GROUP BY company_code"

    # Officer DN_001: COUNT chạy trên view đã lọc tại nguồn → DN_002 vô hình.
    scoped = json.loads(run_tool("query_sql", json.dumps({"sql": sql}), session, {"DN_001"}))
    assert "error" not in scoped, scoped
    assert {r["company_code"]: r["n"] for r in scoped["rows"]} == {"DN_001": 1}

    # Admin: thấy cả hai.
    full = json.loads(run_tool("query_sql", json.dumps({"sql": sql}), session, None))
    assert {r["company_code"]: r["n"] for r in full["rows"]} == {"DN_001": 1, "DN_002": 2}

    # Officer chưa được gán DN nào → không dòng nào.
    empty = run_query(session, sql, allowed_codes=set())
    assert empty["rows"] == []

    # Scoped views đã được gỡ sau query → view thật (admin) không bị "dính" filter.
    after = run_query(session, sql, allowed_codes=None)
    assert {r["company_code"]: r["n"] for r in after["rows"]} == {"DN_001": 1, "DN_002": 2}


def test_query_sql_cannot_escape_via_schema_qualified(session):
    """Officer không lách bằng main.v_findings (schema-qualified bị guard chặn)."""
    _company(session, "DN_001")
    b = _company(session, "DN_002")
    _finding(session, b.id)
    session.commit()
    out = json.loads(run_tool(
        "query_sql", json.dumps({"sql": "SELECT * FROM main.v_findings"}), session, {"DN_001"}
    ))
    assert "error" in out  # 'main' không thuộc allowlist view


# ─────────────────────────── route end-to-end ───────────────────────────

def _setup_db():
    import app.database as dbmod
    from app.auth_users import create_user, seed_default_admin

    new_engine = dbmod.create_engine(
        "sqlite://", connect_args={"check_same_thread": False},
        poolclass=StaticPool, future=True,
    )
    new_session = dbmod.sessionmaker(bind=new_engine, autoflush=False, autocommit=False, future=True)
    dbmod.engine = new_engine
    dbmod.SessionLocal = new_session
    Base.metadata.create_all(new_engine)
    with new_session() as db:
        seed_default_admin(db, "admin", "admin")
        a = Company(code="DN_001", name="A", tax_id="1")
        b = Company(code="DN_002", name="B", tax_id="2")
        db.add_all([a, b])
        db.flush()
        off = create_user(db, "off1", "officerpw", "officer")
        off.companies = [a]  # chỉ DN_001
        db.commit()
    return new_engine, new_session


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


def test_officer_company_list_scoped_route():
    new_engine, _ = _setup_db()
    try:
        client = TestClient(app)
        _login(client, "off1", "officerpw")
        r = client.get("/companies")
        assert r.status_code == 200
        assert "DN_001" in r.text
        assert "DN_002" not in r.text  # DN ngoài phạm vi không hiện
    finally:
        _teardown(new_engine)


def test_officer_blocked_from_unassigned_detail_route():
    new_engine, _ = _setup_db()
    try:
        client = TestClient(app)
        _login(client, "off1", "officerpw")
        assert client.get("/companies/DN_001").status_code == 200
        # DN_002 tồn tại nhưng ngoài phạm vi → 404 (như không tồn tại).
        assert client.get("/companies/DN_002").status_code == 404
        assert client.get("/companies/DN_002/documents").status_code == 404
        assert client.get("/companies/DN_002/export?year=2024").status_code == 404
    finally:
        _teardown(new_engine)


def test_admin_sees_all_route():
    new_engine, _ = _setup_db()
    try:
        client = TestClient(app)
        _login(client, "admin", "admin")
        r = client.get("/companies")
        assert r.status_code == 200
        assert "DN_001" in r.text and "DN_002" in r.text
        assert client.get("/companies/DN_002").status_code == 200
    finally:
        _teardown(new_engine)


def test_admin_assign_unassign_changes_visibility():
    new_engine, new_session = _setup_db()
    try:
        client = TestClient(app)
        _login(client, "admin", "admin")
        # tìm id officer + DN_002
        with new_session() as db:
            from sqlalchemy import select
            off_id = db.scalar(select(User.id).where(User.username == "off1"))
            dn2_id = db.scalar(select(Company.id).where(Company.code == "DN_002"))

        # Gán thêm DN_002 cho officer (giữ cả DN_001).
        with new_session() as db:
            from sqlalchemy import select
            dn1_id = db.scalar(select(Company.id).where(Company.code == "DN_001"))
        r = client.post(
            f"/admin/users/{off_id}/scope",
            data={"company_ids": [dn1_id, dn2_id]}, follow_redirects=False,
        )
        assert r.status_code == 303

        off_client = TestClient(app)
        _login(off_client, "off1", "officerpw")
        assert off_client.get("/companies/DN_002").status_code == 200  # giờ thấy được

        # Gỡ hết phân công (không gửi company_ids) → officer mất quyền.
        r2 = client.post(f"/admin/users/{off_id}/scope", data={}, follow_redirects=False)
        assert r2.status_code == 303
        off_client2 = TestClient(app)
        _login(off_client2, "off1", "officerpw")
        assert off_client2.get("/companies/DN_001").status_code == 404
        assert "DN_001" not in off_client2.get("/companies").text
    finally:
        _teardown(new_engine)
