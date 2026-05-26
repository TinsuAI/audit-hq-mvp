"""Test /tai-lieu/scoring-methodology — render .md → HTML."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool

import app.database as dbmod
from app.auth_users import seed_default_admin
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
    return new_engine, new_session


def _teardown(new_engine):
    new_engine.dispose()
    dbmod.engine = engine
    dbmod.SessionLocal = SessionLocal


def _login(client: TestClient) -> None:
    r = client.post(
        "/login", data={"user": "admin", "password": "admin"}, follow_redirects=False,
    )
    assert r.status_code == 303


def test_scoring_methodology_requires_auth():
    new_engine, _ = _setup_db()
    try:
        client = TestClient(app)
        r = client.get("/tai-lieu/scoring-methodology", follow_redirects=False)
        assert r.status_code == 303
        assert "/login" in r.headers.get("location", "")
    finally:
        _teardown(new_engine)


def test_docs_index_lists_all_public_docs():
    new_engine, _ = _setup_db()
    try:
        client = TestClient(app)
        _login(client)
        r = client.get("/tai-lieu")
        assert r.status_code == 200
        text = r.text
        # Index phải có title + link tới scoring-methodology.
        assert "Thư viện tài liệu" in text or "Tài liệu" in text
        assert "/tai-lieu/scoring-methodology" in text
        assert "Phương pháp tính điểm" in text
    finally:
        _teardown(new_engine)


def test_docs_index_requires_auth():
    new_engine, _ = _setup_db()
    try:
        client = TestClient(app)
        r = client.get("/tai-lieu", follow_redirects=False)
        assert r.status_code == 303
        assert "/login" in r.headers.get("location", "")
    finally:
        _teardown(new_engine)


def test_docs_index_groups_methodology_and_legal():
    new_engine, _ = _setup_db()
    try:
        client = TestClient(app)
        _login(client)
        r = client.get("/tai-lieu")
        text = r.text
        # Hai section: Phương pháp luận + Văn bản pháp lý.
        assert "Phương pháp luận" in text
        assert "Văn bản pháp lý" in text
        # Section pháp lý phải có 3 thông tư.
        assert "tt-38-2015-tt-btc" in text
        assert "tt-39-2018-tt-btc" in text
        assert "tt-81-2019-tt-btc" in text
    finally:
        _teardown(new_engine)


def test_legal_doc_renders():
    new_engine, _ = _setup_db()
    try:
        client = TestClient(app)
        _login(client)
        for slug, expected_substr in [
            ("tt-38-2015-tt-btc", "Mẫu 15/BCQT-NVLTP"),
            ("tt-39-2018-tt-btc", "thông báo định mức trước"),
            ("tt-81-2019-tt-btc", "5 Mức tuân thủ"),
        ]:
            r = client.get(f"/tai-lieu/{slug}")
            assert r.status_code == 200, f"{slug} status {r.status_code}"
            assert expected_substr in r.text, f"{slug} missing {expected_substr!r}"
    finally:
        _teardown(new_engine)


def test_navbar_has_docs_link():
    new_engine, _ = _setup_db()
    try:
        client = TestClient(app)
        _login(client)
        r = client.get("/companies")
        assert r.status_code == 200
        # Navbar phải có link tới /tai-lieu.
        assert 'href="/tai-lieu"' in r.text
    finally:
        _teardown(new_engine)


def test_scoring_methodology_renders_md_content():
    new_engine, _ = _setup_db()
    try:
        client = TestClient(app)
        _login(client)
        r = client.get("/tai-lieu/scoring-methodology")
        assert r.status_code == 200
        text = r.text
        # Section headings from the .md file should appear (rendered as <h2>).
        assert "Phương pháp tính điểm rủi ro" in text
        assert "Mức độ nghiêm trọng" in text
        assert "Phân loại 5 mức cảnh báo" in text
        # Markdown table rendered to <table>.
        assert "<table" in text
        # Disclaimer about TT 81/2019 should be present.
        assert "81/2019" in text
    finally:
        _teardown(new_engine)


def test_company_detail_links_to_methodology_doc():
    new_engine, new_session = _setup_db()
    try:
        from app.models import Company
        with new_session() as s:
            s.add(Company(code="DN_X", tax_id="1", name="X"))
            s.commit()

        client = TestClient(app)
        _login(client)
        r = client.get("/companies/DN_X")
        assert r.status_code == 200
        # Disclaimer footer phải link tới trang giải thích.
        assert "/tai-lieu/scoring-methodology" in r.text
    finally:
        _teardown(new_engine)
