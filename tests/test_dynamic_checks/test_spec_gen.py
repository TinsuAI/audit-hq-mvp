"""Tests — AI spec generation cho catalog động."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool

import app.database as dbmod
from app.auth_users import seed_default_admin
from app.checks.spec_gen import generate_spec, SpecGenError
from app.database import Base, SessionLocal, engine
from app.main import app


# ---------------------------------------------------------------------------
# Unit tests — generate_spec()
# ---------------------------------------------------------------------------

VALID_THRESHOLD_SPEC = {
    "kind": "threshold_compare",
    "table": "nvl_balances",
    "subject_col": "material_code",
    "metric_col": "closing_qty",
    "thresholds": [{"lt": 0, "severity": "critical"}],
    "title_template": "Tồn cuối {subject_key} âm ({value:.2f})",
}


def _make_mock_response(content: str):
    """Build minimal OpenAI-style response mock."""
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


class TestGenerateSpec:
    def test_returns_valid_spec(self):
        """AI trả về JSON hợp lệ → generate_spec parse và validate."""
        mock_resp = _make_mock_response(json.dumps(VALID_THRESHOLD_SPEC))
        with patch("app.checks.spec_gen._call_ai", return_value=mock_resp):
            spec = generate_spec("Tồn cuối NVL âm")
        assert spec["kind"] == "threshold_compare"
        assert spec["table"] == "nvl_balances"

    def test_strips_markdown_fences(self):
        """AI hay wrap JSON trong ```json``` block."""
        content = "```json\n" + json.dumps(VALID_THRESHOLD_SPEC) + "\n```"
        mock_resp = _make_mock_response(content)
        with patch("app.checks.spec_gen._call_ai", return_value=mock_resp):
            spec = generate_spec("Tồn cuối NVL âm")
        assert spec["kind"] == "threshold_compare"

    def test_invalid_json_raises_spec_gen_error(self):
        """AI trả về text không phải JSON → SpecGenError."""
        mock_resp = _make_mock_response("Tôi xin lỗi, tôi không hiểu yêu cầu.")
        with patch("app.checks.spec_gen._call_ai", return_value=mock_resp):
            with pytest.raises(SpecGenError, match="JSON"):
                generate_spec("mô tả không rõ")

    def test_invalid_spec_kind_raises(self):
        """AI trả JSON hợp lệ nhưng kind không hợp lệ → SpecGenError."""
        bad_spec = {**VALID_THRESHOLD_SPEC, "kind": "magic_check"}
        mock_resp = _make_mock_response(json.dumps(bad_spec))
        with patch("app.checks.spec_gen._call_ai", return_value=mock_resp):
            with pytest.raises(SpecGenError, match="kind"):
                generate_spec("mô tả")

    def test_invalid_table_raises(self):
        """Table không hợp lệ → SpecGenError."""
        bad_spec = {**VALID_THRESHOLD_SPEC, "table": "DROP TABLE findings"}
        mock_resp = _make_mock_response(json.dumps(bad_spec))
        with patch("app.checks.spec_gen._call_ai", return_value=mock_resp):
            with pytest.raises(SpecGenError):
                generate_spec("mô tả")

    def test_kind_hint_included_in_prompt(self):
        """kind_hint được truyền vào và có mặt trong prompt gọi AI."""
        mock_resp = _make_mock_response(json.dumps(VALID_THRESHOLD_SPEC))
        with patch("app.checks.spec_gen._call_ai", return_value=mock_resp) as mock_call:
            generate_spec("test description", kind_hint="ratio_threshold")
        call_args = mock_call.call_args
        messages = call_args[1]["messages"] if call_args[1] else call_args[0][0]
        # Verify kind_hint appears somewhere in the messages
        all_content = " ".join(
            m.get("content", "") if isinstance(m, dict) else str(m)
            for m in messages
        )
        assert "ratio_threshold" in all_content

    def test_all_five_kinds_in_prompt(self):
        """Prompt bao gồm ví dụ cho cả 5 kind."""
        mock_resp = _make_mock_response(json.dumps(VALID_THRESHOLD_SPEC))
        with patch("app.checks.spec_gen._call_ai", return_value=mock_resp) as mock_call:
            generate_spec("test")
        call_args = mock_call.call_args
        messages = call_args[1]["messages"] if call_args[1] else call_args[0][0]
        all_content = " ".join(
            m.get("content", "") if isinstance(m, dict) else str(m)
            for m in messages
        )
        for kind in ["threshold_compare", "presence_check", "aggregate_threshold",
                     "cross_table_match", "ratio_threshold"]:
            assert kind in all_content, f"Kind {kind!r} thiếu trong prompt"


# ---------------------------------------------------------------------------
# Route tests — POST /admin/checks/generate-spec
# ---------------------------------------------------------------------------

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


class TestGenerateSpecRoute:
    def test_requires_admin(self):
        eng, sess = _setup_db()
        try:
            from app.auth import make_session_cookie, SessionUser
            from app.models.user import ROLE_OFFICER
            cookie = make_session_cookie(SessionUser(name="officer", role=ROLE_OFFICER))
            client = TestClient(app)
            r = client.post("/admin/checks/generate-spec",
                            json={"description": "test"},
                            cookies={"ahq_session": cookie})
            assert r.status_code == 403
        finally:
            _teardown(eng)

    def test_returns_spec_on_success(self):
        eng, sess = _setup_db()
        try:
            mock_resp = _make_mock_response(json.dumps(VALID_THRESHOLD_SPEC))
            with patch("app.checks.spec_gen._call_ai", return_value=mock_resp):
                from app.auth import make_session_cookie, SessionUser
                from app.models.user import ROLE_ADMIN
                cookie = make_session_cookie(SessionUser(name="admin", role=ROLE_ADMIN))
                client = TestClient(app)
                r = client.post(
                    "/admin/checks/generate-spec",
                    json={"description": "Tồn cuối NVL âm", "kind_hint": "threshold_compare"},
                    cookies={"ahq_session": cookie},
                )
            assert r.status_code == 200
            data = r.json()
            assert data["error"] is None
            assert data["spec"]["kind"] == "threshold_compare"
        finally:
            _teardown(eng)

    def test_returns_error_on_ai_failure(self):
        eng, sess = _setup_db()
        try:
            with patch("app.checks.spec_gen._call_ai", side_effect=Exception("AI timeout")):
                from app.auth import make_session_cookie, SessionUser
                from app.models.user import ROLE_ADMIN
                cookie = make_session_cookie(SessionUser(name="admin", role=ROLE_ADMIN))
                client = TestClient(app)
                r = client.post(
                    "/admin/checks/generate-spec",
                    json={"description": "test"},
                    cookies={"ahq_session": cookie},
                )
            assert r.status_code == 200
            data = r.json()
            assert data["spec"] is None
            assert data["error"] is not None
        finally:
            _teardown(eng)

    def test_empty_description_returns_error(self):
        eng, sess = _setup_db()
        try:
            from app.auth import make_session_cookie, SessionUser
            from app.models.user import ROLE_ADMIN
            cookie = make_session_cookie(SessionUser(name="admin", role=ROLE_ADMIN))
            client = TestClient(app)
            r = client.post(
                "/admin/checks/generate-spec",
                json={"description": ""},
                cookies={"ahq_session": cookie},
            )
            assert r.status_code == 200
            data = r.json()
            assert data["spec"] is None
            assert data["error"] is not None
        finally:
            _teardown(eng)
