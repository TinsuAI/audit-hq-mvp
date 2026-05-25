"""Tests cho AI guardrails — forbidden phrase + missing citation detection."""

from __future__ import annotations

from app.ai.guardrails import (
    apply_guardrails,
    check_forbidden_phrases,
    check_missing_citations,
    redact_forbidden_phrases,
)


def test_forbidden_phrase_detected():
    violations = check_forbidden_phrases("Tôi sẽ confirm finding này.")
    assert len(violations) == 1


def test_forbidden_phrase_reject():
    violations = check_forbidden_phrases("Tôi đã reject trường hợp này.")
    assert len(violations) == 1


def test_forbidden_phrase_duyet():
    violations = check_forbidden_phrases("Tôi sẽ duyệt hồ sơ.")
    assert len(violations) == 1


def test_no_forbidden_phrase_in_clean_text():
    text = "Theo dữ liệu M15, số liệu nguyên liệu tồn kho cần kiểm tra thêm."
    assert check_forbidden_phrases(text) == []


def test_redact_replaces_violation():
    text = "Theo tôi, tôi sẽ confirm finding C3.2."
    clean, violations = redact_forbidden_phrases(text)
    assert violations
    assert "[redacted" in clean
    assert "confirm" not in clean.lower()


def test_missing_citation_detected():
    text = "Theo bảng M15, số dư tồn kho là 1000 kg."
    assert check_missing_citations(text) is True


def test_no_missing_citation_when_tag_present():
    text = "Theo bảng M15, số dư tồn kho là 1000 kg [m15:row_no=42]."
    assert check_missing_citations(text) is False


def test_apply_guardrails_returns_clean_text():
    text = "Dữ liệu bình thường, không vi phạm gì."
    result = apply_guardrails(text, conv_id=None)
    assert result == text


def test_apply_guardrails_redacts_forbidden():
    text = "Tôi đã xác nhận là không vi phạm."
    result = apply_guardrails(text, conv_id=1)
    assert "[redacted" in result
