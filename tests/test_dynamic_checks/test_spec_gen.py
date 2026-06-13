"""Tests — spec_gen: agentic tool-loop soạn check từ NL (mock LLM client)."""

from __future__ import annotations

import json
from types import SimpleNamespace as NS

import pytest

import app.checks.spec_gen as sg
from app.checks.spec_gen import SpecGenError, draft_and_validate
from tests.conftest import add_nvl

_SQL_OK = (
    "SELECT 'critical' AS severity, material_code AS subject_key, "
    "'Tồn âm ' || material_code AS title, 'c=' || closing_qty AS detail "
    "FROM nvl_balances WHERE company_id = :company_id AND period_year = :period_year "
    "AND closing_qty < -0.01"
)


def _good_payload(**over):
    p = {
        "plan": ["Bảng nvl_balances", "Lọc closing_qty < -0.01", "subject material_code"],
        "analysis": "Tìm mã NVL tồn cuối âm.",
        "slug_hint": "ton-am", "title": "Tồn cuối NVL âm",
        "description": "Mã NVL có tồn cuối kỳ âm.", "base_severity": "critical",
        "scope": "nvl", "subject_table": "nvl_balances", "subject_col": "material_code",
        "kind": "sql", "sql_snippet": _SQL_OK,
        "self_review": {"confidence": "high", "alternative_interpretation": "không có",
                        "edge_cases_handled": ["sai số -0.01"]},
    }
    p.update(over)
    return p


def _tc(name, args, tid="t1"):
    return NS(id=tid, type="function", function=NS(name=name, arguments=json.dumps(args)))


class _FakeCompletions:
    def __init__(self, script):
        self.script = script
        self.i = 0

    def create(self, **kw):
        turn = self.script[min(self.i, len(self.script) - 1)]
        self.i += 1
        return NS(choices=[NS(message=NS(
            content=turn.get("content", ""), tool_calls=turn.get("tool_calls"),
        ))])


def _fake_client(script):
    return NS(chat=NS(completions=_FakeCompletions(script)))


@pytest.fixture
def _seed(session, company):
    add_nvl(session, company.id, material_code="NVL_BAD", closing=-5)
    add_nvl(session, company.id, material_code="NVL_OK", closing=10)
    session.commit()
    return company


def test_full_loop_success(session, _seed, monkeypatch):
    script = [
        {"tool_calls": [_tc("get_table_schema", {"table": "nvl_balances"})]},
        {"tool_calls": [_tc("submit_final_answer", {"payload": _good_payload()})]},
    ]
    client = _fake_client(script)
    monkeypatch.setattr(sg, "make_client", lambda: client)
    r = draft_and_validate(session, _seed.id, 2024, "Tìm mã NVL tồn cuối âm")
    assert r.kind == "sql"
    assert r.scope == "nvl"
    assert r.subject_table == "nvl_balances"
    assert r.self_review.get("confidence") == "high"
    assert r.plan and len(r.plan) == 3
    assert r.finding_count == 1  # NVL_BAD matched in dry-run
    assert r.sample_rows[0]["subject_key"] == "NVL_BAD"


def test_retry_on_oracle_failure(session, _seed, monkeypatch):
    """Lần đầu SQL thiếu :company_id → oracle reject → lần 2 hợp lệ."""
    bad = _good_payload(sql_snippet="SELECT 'info' AS severity, material_code AS subject_key, "
                        "'x' AS title, '' AS detail FROM nvl_balances WHERE period_year = :period_year")
    script = [
        {"tool_calls": [_tc("submit_final_answer", {"payload": bad})]},
        {"tool_calls": [_tc("submit_final_answer", {"payload": _good_payload()})]},
    ]
    client = _fake_client(script)
    monkeypatch.setattr(sg, "make_client", lambda: client)
    r = draft_and_validate(session, _seed.id, 2024, "Tìm mã NVL tồn cuối âm", max_retries=2)
    assert r.title == "Tồn cuối NVL âm"


def test_no_tool_call_raises(session, _seed, monkeypatch):
    script = [{"content": "Xin chào, đây là check của bạn.", "tool_calls": None}]
    client = _fake_client(script)
    monkeypatch.setattr(sg, "make_client", lambda: client)
    with pytest.raises(SpecGenError):
        draft_and_validate(session, _seed.id, 2024, "mô tả")


def test_dry_run_failure_then_retry(session, _seed, monkeypatch):
    """SQL tham chiếu cột không tồn tại → dry-run lỗi → retry."""
    bad = _good_payload(sql_snippet="SELECT 'info' AS severity, nope AS subject_key, 'x' AS title, "
                        "'' AS detail FROM nvl_balances WHERE company_id=:company_id AND period_year=:period_year")  # noqa: E501
    script = [
        {"tool_calls": [_tc("submit_final_answer", {"payload": bad})]},
        {"tool_calls": [_tc("submit_final_answer", {"payload": _good_payload()})]},
    ]
    client = _fake_client(script)
    monkeypatch.setattr(sg, "make_client", lambda: client)
    r = draft_and_validate(session, _seed.id, 2024, "Tìm mã NVL tồn cuối âm", max_retries=2)
    assert r.finding_count == 1


def test_empty_prompt_raises(session, company):
    with pytest.raises(SpecGenError):
        draft_and_validate(session, company.id, 2024, "   ")
