"""Tổng quan AI: JSON model trả về phải đọc được, và JSON thô KHÔNG được đưa ra cán bộ.

Ca thật (ảnh chụp 06/08): panel "Tổng quan AI" in nguyên khối JSON — dấu ngoặc, tên
khoá `nhan_dinh`/`diem_nong`, thụt đầu dòng. `parse_sections` trả None nên template
rơi xuống nhánh in `ov.content` thô.

Hai lớp, sửa cả hai:

1. **Vì sao parse trượt.** `json.loads` mặc định `strict=True` từ chối ký tự điều
   khiển thô bên trong chuỗi. Model xuống dòng thật giữa một câu dài là JSON hỏng —
   nhưng `white-space: pre-wrap` render ra y hệt JSON hợp lệ, nên nhìn ảnh không thấy
   được. Cùng lớp đó: model viết thêm câu dẫn trước `{` hoặc ghi chú sau `}`.
2. **Trượt thì hiện gì.** Dù lý do là gì, khối JSON thô là thứ cán bộ không đọc được
   và không nên thấy. Nhánh xuống cấp phải nói rõ là chưa viết được nhận định.
"""

from __future__ import annotations

import json

from app.ai.overview_content import parse_sections
from app.models import CheckOverview

_MINIMAL = {"nhan_dinh": "Một câu.", "phan_bo": "", "diem_nong": [], "de_xuat": []}


def test_parse_accepts_a_literal_newline_inside_a_string():
    """Model xuống dòng thật giữa câu — mắt nhìn vẫn là JSON đẹp."""
    raw = (
        '{\n "nhan_dinh": "Kiểm tra C1.1 ghi nhận 97 phát hiện,\n'
        'trong đó 49 nghiêm trọng.",\n'
        ' "phan_bo": "", "diem_nong": [], "de_xuat": []\n}'
    )
    out = parse_sections(raw)
    assert out is not None
    assert "97 phát hiện" in out["nhan_dinh"]


def test_parse_accepts_a_literal_tab_inside_a_string():
    raw = '{"nhan_dinh": "Cột\tĐơn giá lệch.", "phan_bo": "", "diem_nong": [], "de_xuat": []}'
    out = parse_sections(raw)
    assert out is not None


def test_parse_finds_the_object_after_a_preamble():
    raw = "Dưới đây là nhận định theo cấu trúc yêu cầu:\n\n" + json.dumps(_MINIMAL, ensure_ascii=False)
    out = parse_sections(raw)
    assert out is not None
    assert out["nhan_dinh"] == "Một câu."


def test_parse_finds_the_object_before_a_trailing_note():
    raw = json.dumps(_MINIMAL, ensure_ascii=False) + "\n\nGhi chú: số liệu lấy nguyên từ bảng."
    out = parse_sections(raw)
    assert out is not None
    assert out["nhan_dinh"] == "Một câu."


def test_parse_handles_a_fence_that_is_not_the_whole_string():
    raw = "Kết quả:\n```json\n" + json.dumps(_MINIMAL, ensure_ascii=False) + "\n```\nHết."
    out = parse_sections(raw)
    assert out is not None


def test_parse_still_gives_up_on_text_with_no_object():
    assert parse_sections("Xin lỗi, tôi không thể tạo nhận định cho dữ liệu này.") is None
    assert parse_sections("") is None
    assert parse_sections("[1, 2, 3]") is None


def test_parse_gives_up_on_a_truncated_object():
    """Cụt vì chạm max_tokens — đừng đoán phần thiếu."""
    raw = '{"nhan_dinh": "Câu bị cắt giữa chừng'
    assert parse_sections(raw) is None


# ── Lớp 2: trượt rồi thì cán bộ thấy gì ────────────────────────────────────────


def test_a_json_blob_is_marked_unreadable():
    """Đây chính là thứ đang hiện trên màn: `{`, tên khoá, thụt đầu dòng."""
    ov = CheckOverview(content='{\n  "nhan_dinh": "…",\n  "diem_nong": []\n}', sections_json=None)
    assert ov.fallback_is_unreadable is True


def test_a_truncated_json_blob_is_marked_unreadable():
    ov = CheckOverview(content='{"nhan_dinh": "Câu bị cắt', sections_json=None)
    assert ov.fallback_is_unreadable is True


def test_a_fenced_json_blob_is_marked_unreadable():
    ov = CheckOverview(content='```json\n{"nhan_dinh": "…"}\n```', sections_json=None)
    assert ov.fallback_is_unreadable is True


def test_plain_prose_is_still_shown_to_the_officer():
    """Model viết văn xuôi thay vì JSON — đọc được, cứ hiện."""
    ov = CheckOverview(
        content="Kiểm tra C1.1 ghi nhận 97 phát hiện, trong đó 49 nghiêm trọng.",
        sections_json=None,
    )
    assert ov.fallback_is_unreadable is False


def test_a_parsed_overview_never_uses_the_fallback():
    ov = CheckOverview(content='{"nhan_dinh": "…"}', sections_json={"nhan_dinh": "…"})
    assert ov.fallback_is_unreadable is False


def test_empty_content_is_not_shown_as_prose():
    assert CheckOverview(content="", sections_json=None).fallback_is_unreadable is False
    assert CheckOverview(content=None, sections_json=None).fallback_is_unreadable is False
