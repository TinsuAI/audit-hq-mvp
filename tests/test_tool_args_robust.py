"""Robust tool-call args: chống lỗi gộp '{...}{...}' (Gemini phát call song song)."""

from __future__ import annotations

import json

from app.ai.tools import run_tool
from app.routes.ai import _clean_tool_args


def test_clean_tool_args_takes_first_object():
    assert _clean_tool_args('{"sql":"a"}{"sql":"b"}') == '{"sql": "a"}'


def test_clean_tool_args_passthrough_valid():
    assert json.loads(_clean_tool_args('{"sql":"a"}')) == {"sql": "a"}


def test_clean_tool_args_empty():
    assert _clean_tool_args("") == "{}"
    assert _clean_tool_args("   ") == "{}"


def test_clean_tool_args_unparseable_returns_raw():
    assert _clean_tool_args("not json") == "not json"


def test_run_tool_tolerates_concatenated_args(session):
    # Gemini gộp 2 call → '{...}{...}'. run_tool phải chạy call ĐẦU, không lỗi "Extra data".
    out = run_tool("explain_check", '{"check_code":"C2.3"}{"check_code":"C9.9"}', session)
    payload = json.loads(out)
    assert "Extra data" not in out
    assert payload.get("code") == "C2.3"
