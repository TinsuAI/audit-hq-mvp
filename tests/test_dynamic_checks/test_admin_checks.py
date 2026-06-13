"""Tests — admin routes soạn/quản lý kiểm tra mở rộng (/admin/checks/*)."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool

import app.database as dbmod
from app.auth_users import seed_default_admin
from app.checks.spec_gen import DraftResult, SpecGenError
from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import CheckDefinition, CheckStatus, Company, NvlBalance


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


def _login_admin(client):
    r = client.post("/login", data={"user": "admin", "password": "admin"}, follow_redirects=False)
    assert r.status_code == 303


_SQL = (
    "SELECT 'critical' AS severity, material_code AS subject_key, "
    "'x' AS title, '' AS detail FROM nvl_balances "
    "WHERE company_id=:company_id AND period_year=:period_year AND closing_qty < -0.01"
)


def _sql_check(**kw):
    base = dict(code="X.1", kind="sql", title="Tồn cuối âm demo", description="",
                spec={}, sql_snippet=_SQL, subject_table="nvl_balances",
                subject_col="material_code", scope="nvl", default_severity="critical")
    base.update(kw)
    return CheckDefinition(**base)


class TestListAndAuth:
    def test_list_requires_auth(self):
        eng, _ = _setup_db()
        try:
            r = TestClient(app).get("/admin/checks", follow_redirects=False)
            assert r.status_code in (302, 303)
        finally:
            _teardown(eng)

    def test_list_requires_admin(self):
        eng, _ = _setup_db()
        try:
            from app.auth import SessionUser, make_session_cookie
            from app.models.user import ROLE_OFFICER
            cookie = make_session_cookie(SessionUser(name="officer", role=ROLE_OFFICER))
            r = TestClient(app).get("/admin/checks", cookies={"ahq_session": cookie})
            assert r.status_code == 403
        finally:
            _teardown(eng)

    def test_list_shows_checks(self):
        eng, sess = _setup_db()
        try:
            with sess() as db:
                db.add(_sql_check(status=CheckStatus.PUBLISHED))
                db.commit()
            client = TestClient(app)
            _login_admin(client)
            r = client.get("/admin/checks")
            assert r.status_code == 200
            assert "Tồn cuối âm demo" in r.text
        finally:
            _teardown(eng)

    def test_new_form_renders(self):
        eng, _ = _setup_db()
        try:
            client = TestClient(app)
            _login_admin(client)
            r = client.get("/admin/checks/new")
            assert r.status_code == 200
            assert "ngôn ngữ tự nhiên" in r.text
        finally:
            _teardown(eng)


class TestDraft:
    def test_draft_renders_preview(self):
        eng, sess = _setup_db()
        try:
            with sess() as db:
                db.add(Company(code="DN_X", name="DN X"))
                db.commit()
            client = TestClient(app)
            _login_admin(client)
            fake = DraftResult(
                nl_prompt="tồn âm", kind="sql", title="Tồn cuối NVL âm",
                description="desc", slug="ton-am", base_severity="critical", scope="nvl",
                subject_table="nvl_balances", subject_col="material_code",
                sql_snippet=_SQL, detail_query="", code_snippet="", analysis="a",
                plan=["b1"], self_review={"confidence": "medium",
                                          "alternative_interpretation": "cách khác"},
                sample_rows=[{"severity": "critical", "subject_key": "M1",
                             "title": "t", "detail": "d"}],
                matched_rows=[], matched_columns=[], finding_count=1,
                ref_company_code="DN_X", ref_year=2024,
            )
            with patch("app.routes.admin_checks.draft_and_validate", return_value=fake), \
                 patch("app.ai.config.get_setting", return_value="x"):
                r = client.post("/admin/checks/draft", data={
                    "nl_prompt": "tồn âm", "ref_company": "DN_X", "ref_year": 2024,
                })
            assert r.status_code == 200
            assert "Hệ thống hiểu" in r.text
            assert "Tồn cuối NVL âm" in r.text
            assert "cách khác" in r.text  # alternative interpretation shown (medium conf)

        finally:
            _teardown(eng)

    def test_draft_shows_error_on_specgen_failure(self):
        eng, sess = _setup_db()
        try:
            with sess() as db:
                db.add(Company(code="DN_X", name="DN X"))
                db.commit()
            client = TestClient(app)
            _login_admin(client)
            with patch("app.routes.admin_checks.draft_and_validate",
                       side_effect=SpecGenError("AI lỗi")), \
                 patch("app.ai.config.get_setting", return_value="x"):
                r = client.post("/admin/checks/draft", data={
                    "nl_prompt": "x", "ref_company": "DN_X", "ref_year": 2024,
                })
            assert r.status_code == 400
            assert "AI lỗi" in r.text
        finally:
            _teardown(eng)


class TestSave:
    def _post_save(self, client, **over):
        data = {
            "nl_prompt": "tồn âm", "kind": "sql", "title": "Tồn cuối NVL âm",
            "description": "desc", "base_severity": "critical", "scope": "nvl",
            "subject_table": "nvl_balances", "subject_col": "material_code",
            "sql_snippet": _SQL, "detail_query": "", "code_snippet": "",
            "analysis": "a", "plan_json": '["b1"]', "self_review_json": '{"confidence":"high"}',
        }
        data.update(over)
        return client.post("/admin/checks", data=data, follow_redirects=False)

    def test_save_creates_draft(self):
        eng, sess = _setup_db()
        try:
            client = TestClient(app)
            _login_admin(client)
            r = self._post_save(client)
            assert r.status_code == 303
            with sess() as db:
                cd = db.query(CheckDefinition).first()
                assert cd.code == "X.1"
                assert cd.kind == "sql"
                assert cd.scope == "nvl"
                assert cd.subject_table == "nvl_balances"
                assert cd.status == CheckStatus.DRAFT
                assert cd.plan == ["b1"]
                assert cd.self_review == {"confidence": "high"}
        finally:
            _teardown(eng)

    def test_save_rejects_invalid_sql(self):
        eng, _ = _setup_db()
        try:
            client = TestClient(app)
            _login_admin(client)
            # SQL thiếu :company_id → validate fail → 400
            r = self._post_save(client, sql_snippet="SELECT 1 AS severity")
            assert r.status_code == 400
        finally:
            _teardown(eng)

    def test_save_sequential_codes(self):
        eng, _ = _setup_db()
        try:
            client = TestClient(app)
            _login_admin(client)
            self._post_save(client)
            self._post_save(client, title="Hai")
            r = client.get("/admin/checks")
            assert "X.1" in r.text and "X.2" in r.text
        finally:
            _teardown(eng)


class TestPreviewAndStatus:
    def test_preview_runs_check(self):
        eng, sess = _setup_db()
        try:
            with sess() as db:
                c = Company(code="DN_P", name="P")
                db.add(c)
                db.flush()
                db.add(NvlBalance(company_id=c.id, period_year=2024,
                                  material_code="BAD", unit="PCE", closing_qty=-5))
                db.add(_sql_check(status=CheckStatus.DRAFT))
                db.commit()
                cid = db.query(CheckDefinition).first().id
            client = TestClient(app)
            _login_admin(client)
            r = client.post(f"/admin/checks/{cid}/preview",
                            json={"company_code": "DN_P", "year": 2024})
            assert r.status_code == 200
            data = r.json()
            assert data["count"] == 1
            assert data["findings"][0]["subject_key"] == "BAD"
        finally:
            _teardown(eng)

    def test_publish_then_disable(self):
        eng, sess = _setup_db()
        try:
            with sess() as db:
                db.add(_sql_check(status=CheckStatus.DRAFT))
                db.commit()
                cid = db.query(CheckDefinition).first().id
            client = TestClient(app)
            _login_admin(client)
            client.post(f"/admin/checks/{cid}/publish", follow_redirects=False)
            with sess() as db:
                assert db.get(CheckDefinition, cid).status == CheckStatus.PUBLISHED
            client.post(f"/admin/checks/{cid}/disable", follow_redirects=False)
            with sess() as db:
                assert db.get(CheckDefinition, cid).status == CheckStatus.DISABLED
        finally:
            _teardown(eng)

    def test_publish_requires_admin(self):
        eng, sess = _setup_db()
        try:
            with sess() as db:
                db.add(_sql_check(status=CheckStatus.DRAFT))
                db.commit()
                cid = db.query(CheckDefinition).first().id
            from app.auth import SessionUser, make_session_cookie
            from app.models.user import ROLE_OFFICER
            cookie = make_session_cookie(SessionUser(name="o", role=ROLE_OFFICER))
            r = TestClient(app).post(f"/admin/checks/{cid}/publish",
                                     cookies={"ahq_session": cookie}, follow_redirects=False)
            assert r.status_code == 403
        finally:
            _teardown(eng)
