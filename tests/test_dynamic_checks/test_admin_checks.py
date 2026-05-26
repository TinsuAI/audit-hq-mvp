"""Tests — admin routes cho catalog động (/admin/checks/*)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool

import app.database as dbmod
from app.auth_users import seed_default_admin
from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import CheckDefinition, CheckStatus


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


VALID_SPEC = {
    "kind": "threshold_compare",
    "table": "nvl_balances",
    "subject_col": "material_code",
    "metric_col": "closing_qty",
    "thresholds": [{"lt": 0, "severity": "critical"}],
    "title_template": "Tồn cuối {subject_key} âm",
}


class TestListChecks:
    def test_list_requires_auth(self):
        eng, sess = _setup_db()
        try:
            client = TestClient(app, raise_server_exceptions=True)
            r = client.get("/admin/checks", follow_redirects=False)
            assert r.status_code in (302, 303)
        finally:
            _teardown(eng)

    def test_list_requires_admin(self):
        eng, sess = _setup_db()
        try:
            client = TestClient(app)
            # Dùng cookie officer trực tiếp (không cần đăng nhập thật).
            from app.auth import make_session_cookie, SessionUser
            from app.models.user import ROLE_OFFICER
            cookie = make_session_cookie(SessionUser(name="officer", role=ROLE_OFFICER))
            r = client.get("/admin/checks", cookies={"ahq_session": cookie})
            assert r.status_code == 403
        finally:
            _teardown(eng)

    def test_list_empty(self):
        eng, sess = _setup_db()
        try:
            client = TestClient(app)
            _login_admin(client)
            r = client.get("/admin/checks")
            assert r.status_code == 200
            assert "Kiểm tra mở rộng" in r.text
        finally:
            _teardown(eng)

    def test_list_shows_checks(self):
        eng, sess = _setup_db()
        try:
            with sess() as db:
                db.add(CheckDefinition(
                    code="X.1", kind="threshold_compare",
                    title="Tồn cuối âm demo", description="",
                    spec={}, status=CheckStatus.PUBLISHED,
                ))
                db.commit()
            client = TestClient(app)
            _login_admin(client)
            r = client.get("/admin/checks")
            assert r.status_code == 200
            assert "Tồn cuối âm demo" in r.text
        finally:
            _teardown(eng)


class TestCreateCheck:
    def test_new_form_renders(self):
        eng, sess = _setup_db()
        try:
            client = TestClient(app)
            _login_admin(client)
            r = client.get("/admin/checks/new")
            assert r.status_code == 200
        finally:
            _teardown(eng)

    def test_create_saves_draft(self):
        eng, sess = _setup_db()
        try:
            client = TestClient(app)
            _login_admin(client)
            r = client.post("/admin/checks", data={
                "title": "My check",
                "description": "Mô tả",
                "kind": "threshold_compare",
                "spec_json": json.dumps(VALID_SPEC),
            }, follow_redirects=False)
            assert r.status_code in (302, 303)
            from sqlalchemy import select
            with sess() as db:
                cd = db.scalar(select(CheckDefinition).where(CheckDefinition.title == "My check"))
            assert cd is not None
            assert cd.status == CheckStatus.DRAFT
            assert cd.code.startswith("X.")
        finally:
            _teardown(eng)

    def test_create_invalid_spec_returns_error(self):
        eng, sess = _setup_db()
        try:
            client = TestClient(app)
            _login_admin(client)
            r = client.post("/admin/checks", data={
                "title": "Bad check",
                "description": "",
                "kind": "threshold_compare",
                "spec_json": json.dumps({"kind": "threshold_compare", "table": "rm_rf"}),
            })
            assert r.status_code in (200, 400)
            from sqlalchemy import select
            with sess() as db:
                cd = db.scalar(select(CheckDefinition).where(CheckDefinition.title == "Bad check"))
            assert cd is None
        finally:
            _teardown(eng)

    def test_create_assigns_sequential_codes(self):
        eng, sess = _setup_db()
        try:
            client = TestClient(app)
            _login_admin(client)
            for title in ["Check A", "Check B"]:
                client.post("/admin/checks", data={
                    "title": title,
                    "description": "",
                    "kind": "threshold_compare",
                    "spec_json": json.dumps(VALID_SPEC),
                }, follow_redirects=False)
            from sqlalchemy import select
            with sess() as db:
                codes = [
                    r.code for r in db.scalars(
                        select(CheckDefinition).order_by(CheckDefinition.id)
                    ).all()
                ]
            assert codes == ["X.1", "X.2"]
        finally:
            _teardown(eng)


class TestPublishCheck:
    def test_publish_changes_status(self):
        eng, sess = _setup_db()
        try:
            with sess() as db:
                cd = CheckDefinition(
                    code="X.1", kind="threshold_compare",
                    title="T", description="",
                    spec=VALID_SPEC,
                )
                db.add(cd)
                db.commit()
                cd_id = cd.id
            client = TestClient(app)
            _login_admin(client)
            r = client.post(f"/admin/checks/{cd_id}/publish", follow_redirects=False)
            assert r.status_code in (302, 303)
            with sess() as db:
                cd = db.get(CheckDefinition, cd_id)
            assert cd.status == CheckStatus.PUBLISHED
        finally:
            _teardown(eng)

    def test_publish_requires_admin(self):
        eng, sess = _setup_db()
        try:
            from app.auth import make_session_cookie, SessionUser
            from app.models.user import ROLE_OFFICER
            cookie = make_session_cookie(SessionUser(name="officer", role=ROLE_OFFICER))
            client = TestClient(app)
            r = client.post("/admin/checks/1/publish", cookies={"ahq_session": cookie})
            assert r.status_code == 403
        finally:
            _teardown(eng)


class TestDisableCheck:
    def test_disable_changes_status(self):
        eng, sess = _setup_db()
        try:
            with sess() as db:
                cd = CheckDefinition(
                    code="X.1", kind="threshold_compare",
                    title="T", description="",
                    spec={}, status=CheckStatus.PUBLISHED,
                )
                db.add(cd)
                db.commit()
                cd_id = cd.id
            client = TestClient(app)
            _login_admin(client)
            r = client.post(f"/admin/checks/{cd_id}/disable", follow_redirects=False)
            assert r.status_code in (302, 303)
            with sess() as db:
                cd = db.get(CheckDefinition, cd_id)
            assert cd.status == CheckStatus.DISABLED
        finally:
            _teardown(eng)


class TestPreviewCheck:
    def _seed_check_and_company(self, sess):
        from app.models import Company
        from app.models.finding import Finding
        with sess() as db:
            cd = CheckDefinition(
                code="X.1", kind="threshold_compare",
                title="Test check", description="",
                spec=VALID_SPEC, status=CheckStatus.PUBLISHED,
            )
            db.add(cd)
            company = Company(
                code="DN_TEST", name="Công ty Test",
            )
            db.add(company)
            db.commit()
            return cd.id, company.id

    def test_preview_returns_findings(self):
        eng, sess = _setup_db()
        try:
            cd_id, company_id = self._seed_check_and_company(sess)
            from app.models.finding import Finding
            mock_findings = [
                Finding(
                    company_id=company_id, period_year=2023,
                    check_code="X.1", severity="critical",
                    title="Tồn cuối NVL001 âm",
                    details={"closing_qty": -5},
                ),
            ]
            from unittest.mock import patch
            with patch("app.checks.dynamic_runner.DynamicCheckRunner.run", return_value=mock_findings):
                client = TestClient(app)
                _login_admin(client)
                r = client.post(
                    f"/admin/checks/{cd_id}/preview",
                    json={"company_code": "DN_TEST", "year": 2023},
                )
            assert r.status_code == 200
            data = r.json()
            assert data["error"] is None
            assert data["count"] == 1
            assert data["findings"][0]["title"] == "Tồn cuối NVL001 âm"
            assert data["findings"][0]["severity"] == "critical"
        finally:
            _teardown(eng)

    def test_preview_no_findings(self):
        eng, sess = _setup_db()
        try:
            cd_id, _ = self._seed_check_and_company(sess)
            from unittest.mock import patch
            with patch("app.checks.dynamic_runner.DynamicCheckRunner.run", return_value=[]):
                client = TestClient(app)
                _login_admin(client)
                r = client.post(
                    f"/admin/checks/{cd_id}/preview",
                    json={"company_code": "DN_TEST", "year": 2023},
                )
            assert r.status_code == 200
            data = r.json()
            assert data["error"] is None
            assert data["count"] == 0
            assert data["findings"] == []
        finally:
            _teardown(eng)

    def test_preview_unknown_company_returns_error(self):
        eng, sess = _setup_db()
        try:
            cd_id, _ = self._seed_check_and_company(sess)
            client = TestClient(app)
            _login_admin(client)
            r = client.post(
                f"/admin/checks/{cd_id}/preview",
                json={"company_code": "GHOST", "year": 2023},
            )
            assert r.status_code == 200
            data = r.json()
            assert data["error"] is not None
            assert data["findings"] is None
        finally:
            _teardown(eng)

    def test_preview_check_not_found_returns_404(self):
        eng, sess = _setup_db()
        try:
            client = TestClient(app)
            _login_admin(client)
            r = client.post(
                "/admin/checks/9999/preview",
                json={"company_code": "DN_TEST", "year": 2023},
            )
            assert r.status_code == 404
        finally:
            _teardown(eng)

    def test_preview_requires_admin(self):
        eng, sess = _setup_db()
        try:
            from app.auth import make_session_cookie, SessionUser
            from app.models.user import ROLE_OFFICER
            cookie = make_session_cookie(SessionUser(name="officer", role=ROLE_OFFICER))
            client = TestClient(app)
            r = client.post(
                "/admin/checks/1/preview",
                json={"company_code": "DN_TEST", "year": 2023},
                cookies={"ahq_session": cookie},
            )
            assert r.status_code == 403
        finally:
            _teardown(eng)
