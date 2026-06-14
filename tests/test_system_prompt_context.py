"""P3 — ngữ cảnh trang phân giải cao trong system prompt."""

from __future__ import annotations

from app.ai.system_prompt import build_messages_system, build_page_context


def _flatten(msgs) -> str:
    content = msgs[0]["content"]
    if isinstance(content, list):
        return " ".join(b.get("text", "") for b in content)
    return content


def test_page_context_empty():
    assert build_page_context(None, None, None, None) == ""


def test_page_context_dn_and_year_combined():
    out = build_page_context("/companies/DN_001?year=2024", "DN_001", 2024, None)
    assert "DN `DN_001`" in out and "năm `2024`" in out


def test_page_context_item_code():
    out = build_page_context(
        "/companies/DN_001/items/X-DL", "DN_001", 2024, None, item_code="X-DL"
    )
    assert "mã hàng `X-DL`" in out


def test_page_context_table_with_filter():
    out = build_page_context("/x", "DN_001", 2024, None, table="m15", table_q="ABC")
    assert "M15" in out and "lọc theo `ABC`" in out


def test_page_context_finding_and_label():
    out = build_page_context("/findings/5", None, None, 5, view_label="Chi tiết phát hiện")
    assert "Trang: Chi tiết phát hiện" in out and "#5" in out


def test_build_messages_system_threads_new_keys():
    msgs = build_messages_system(page_context={
        "url": "/companies/DN_002/items/Y",
        "dn_code": "DN_002",
        "item_code": "Y",
        "view_label": "Chi tiết mã hàng",
    })
    text = _flatten(msgs)
    assert "DN_002" in text and "mã hàng `Y`" in text and "Chi tiết mã hàng" in text
