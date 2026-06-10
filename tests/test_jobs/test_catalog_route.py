"""Test /danh-muc-kiem-tra — trang danh mục 49 kiểm tra theo §4 đề án."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool

import app.database as dbmod
from app.auth_users import seed_default_admin
from app.catalog_full import CATALOG, grouped_by_phase, summary_counts
from app.database import Base, SessionLocal, engine
from app.main import app


def _setup_db():
    new_engine = dbmod.create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    new_session = dbmod.sessionmaker(
        bind=new_engine, autoflush=False, autocommit=False, future=True,
    )
    dbmod.engine = new_engine
    dbmod.SessionLocal = new_session
    Base.metadata.create_all(new_engine)
    with new_session() as db:
        seed_default_admin(db, "admin", "admin")
    return new_engine


def _teardown(new_engine):
    new_engine.dispose()
    dbmod.engine = engine
    dbmod.SessionLocal = SessionLocal


def _login(client: TestClient) -> None:
    r = client.post(
        "/login", data={"user": "admin", "password": "admin"}, follow_redirects=False,
    )
    assert r.status_code == 303


def test_catalog_has_49_entries():
    assert len(CATALOG) == 49
    counts = summary_counts()
    assert counts == {"total": 49, "mvp": 17, "wip": 13, "conditional": 19}


def test_catalog_phase_breakdown_matches_proposal():
    """Phase I = 33 kiểm tra (Nhóm 1-7), Phase II = 16 (Nhóm 8-12)."""
    phases = grouped_by_phase()
    p1 = next(p for p in phases if p["phase"] == 1)
    p2 = next(p for p in phases if p["phase"] == 2)
    assert sum(len(g["entries"]) for g in p1["groups"]) == 33
    assert sum(len(g["entries"]) for g in p2["groups"]) == 16
    assert [g["group"] for g in p1["groups"]] == [1, 2, 3, 4, 5, 6, 7]
    assert [g["group"] for g in p2["groups"]] == [8, 9, 10, 11, 12]


def test_catalog_requires_auth():
    new_engine = _setup_db()
    try:
        client = TestClient(app)
        r = client.get("/danh-muc-kiem-tra", follow_redirects=False)
        assert r.status_code == 303
        assert "/login" in r.headers.get("location", "")
    finally:
        _teardown(new_engine)


def test_catalog_page_renders_all_codes():
    new_engine = _setup_db()
    try:
        client = TestClient(app)
        _login(client)
        r = client.get("/danh-muc-kiem-tra")
        assert r.status_code == 200
        text = r.text
        assert "Danh mục kiểm tra" in text
        # Spot-check: vài mã từ mỗi giai đoạn phải xuất hiện.
        for code in ["C1.1", "C4.3", "C6.1", "C7.2", "C8.2", "C10.1", "C12.3"]:
            assert code in text, f"missing {code}"
        # Summary numbers.
        assert "49" in text
        assert "16" in text
    finally:
        _teardown(new_engine)


def test_navbar_has_catalog_link():
    new_engine = _setup_db()
    try:
        client = TestClient(app)
        _login(client)
        r = client.get("/companies")
        assert r.status_code == 200
        assert 'href="/danh-muc-kiem-tra"' in r.text
    finally:
        _teardown(new_engine)
