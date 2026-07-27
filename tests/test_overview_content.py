"""TQ-4 (ADR #21 mục 3-4, 12) — nhận định JSON bốn mục + hậu kiểm số.

Hậu kiểm so khớp CHUỖI chứ không parse: parse vấp làm tròn (61,8 → 62%), năm
2025, mã kiểm tra C1.6, và mã hàng có chữ số. Đây là bộ dò hallucination rẻ nhất
hệ thống chạy được, đặt đúng trên artifact ra trước mặt khách.
"""

from __future__ import annotations

import json

from app.ai.overview_content import (
    build_prompt_payload,
    finalize_sections,
    parse_sections,
    unsupported_numbers,
)


def _stats(**over):
    base = {
        "check_code": "C1.6",
        "title": "Chuyển mục đích sử dụng",
        "year": 2025,
        "total_findings": 42,
        "severity_totals": {"critical": 30, "warning": 10, "info": 2},
        "concentration": {
            "distinct_subjects": 8,
            "top5_share_pct": 61.8,
            "subjects_covering_80pct": 6,
            "top_subjects": [
                {"subject_key": "NPL-X12", "count": 9},
                {"subject_key": "MC50", "count": 7},
            ],
        },
        "numeric_fields": [{
            "key": "m15_repurpose", "is_pct": False, "n": 42,
            "min": 1.0, "p50": 25.0, "p90": 300.0, "max": 900.0,
            "higher": 40, "lower": 2, "zero": 0,
        }],
        "previous_year": {
            "available": True, "year": 2024, "total": 30, "delta": 12,
            "new_subjects_count": 3, "new_subjects": ["NPL-X12"],
        },
    }
    base.update(over)
    return base


# ───────────────────────── prompt ─────────────────────────

def test_prompt_supplies_preformatted_numbers(_=None):
    block, allowed = build_prompt_payload(_stats(), "Công ty A")
    assert "Công ty A" in block
    assert "61,8" in block          # định dạng Việt Nam, model chỉ việc copy
    assert "61,8" in allowed
    assert "+12" in allowed         # chênh lệch có dấu
    assert "NPL-X12" in allowed


def test_prompt_tells_model_to_skip_distribution_when_small(_=None):
    block, _a = build_prompt_payload(_stats(total_findings=7), "Công ty A")
    assert "BỎ TRỐNG trường `phan_bo`" in block


def test_prompt_forbids_writing_zero_when_no_previous_period(_=None):
    block, _a = build_prompt_payload(
        _stats(previous_year={"available": False, "year": 2024}), "Công ty A"
    )
    assert "KHÔNG được viết là 0" in block
    assert "Chênh lệch" not in block


# ───────────────────────── parse ─────────────────────────

def _raw(**over):
    payload = {
        "nhan_dinh": "Kiểm tra ghi nhận 42 phát hiện.",
        "phan_bo": "5 mã lớn nhất chiếm 61,8% số phát hiện.",
        "diem_nong": [{"subject_key": "NPL-X12", "nhan_xet": "Lượng chuyển mục đích lớn."}],
        "de_xuat": ["Đối chiếu chứng từ chuyển mục đích."],
    }
    payload.update(over)
    return json.dumps(payload, ensure_ascii=False)


def test_parses_four_sections(_=None):
    sec = parse_sections(_raw())
    assert set(sec) == {"nhan_dinh", "phan_bo", "diem_nong", "de_xuat"}
    assert sec["diem_nong"][0]["subject_key"] == "NPL-X12"


def test_parses_json_wrapped_in_code_fence(_=None):
    sec = parse_sections("```json\n" + _raw() + "\n```")
    assert sec is not None
    assert sec["nhan_dinh"].startswith("Kiểm tra")


def test_broken_json_degrades_to_none(_=None):
    assert parse_sections("Đây là một đoạn văn xuôi, không phải JSON.") is None
    assert parse_sections("") is None
    assert parse_sections("[1, 2, 3]") is None


def test_caps_hotspots_and_suggestions(_=None):
    sec = parse_sections(_raw(
        diem_nong=[{"subject_key": f"M{i}", "nhan_xet": "x"} for i in range(9)],
        de_xuat=[f"đề xuất {i}" for i in range(9)],
    ))
    assert len(sec["diem_nong"]) == 5
    assert len(sec["de_xuat"]) == 3


# ───────────────────────── hậu kiểm số ─────────────────────────

def test_numbers_copied_verbatim_pass(_=None):
    stats = _stats()
    _block, allowed = build_prompt_payload(stats, "Công ty A")
    sec, bad = finalize_sections(parse_sections(_raw()), stats, allowed)
    assert bad == []
    assert sec["phan_bo"]


def test_invented_number_is_flagged(_=None):
    stats = _stats()
    _block, allowed = build_prompt_payload(stats, "Công ty A")
    raw = _raw(nhan_dinh="Kiểm tra ghi nhận 137 phát hiện trên 8 mã.")
    _sec, bad = finalize_sections(parse_sections(raw), stats, allowed)
    assert bad == ["137"]


def test_rounded_number_is_flagged_not_silently_accepted(_=None):
    """61,8% làm tròn thành 62% là đúng lệch — phải gắn cờ, không publish âm thầm."""
    stats = _stats()
    _block, allowed = build_prompt_payload(stats, "Công ty A")
    raw = _raw(phan_bo="5 mã lớn nhất chiếm khoảng 62% số phát hiện.")
    _sec, bad = finalize_sections(parse_sections(raw), stats, allowed)
    assert bad == ["62"]


def test_check_code_and_year_are_not_flagged(_=None):
    """Mã kiểm tra C1.6, năm 2025, mã hàng NPL-X12 đều có chữ số — không phải bịa."""
    stats = _stats()
    _block, allowed = build_prompt_payload(stats, "Công ty A")
    raw = _raw(nhan_dinh="Kiểm tra C1.6 năm 2025 tập trung ở mã NPL-X12.")
    _sec, bad = finalize_sections(parse_sections(raw), stats, allowed)
    assert bad == []


def test_unsupported_numbers_scans_every_section(_=None):
    allowed = {"42"}
    sections = {
        "nhan_dinh": "42 phát hiện",
        "phan_bo": "chiếm 99%",
        "diem_nong": [{"subject_key": "M7", "nhan_xet": "lệch 55 đơn vị"}],
        "de_xuat": ["rà soát 3 mã"],
    }
    assert unsupported_numbers(sections, allowed) == ["3", "55", "7", "99"]


# ───────────────────────── quy tắc trình bày ─────────────────────────

def test_distribution_dropped_below_ten_findings(_=None):
    stats = _stats(total_findings=7)
    _block, allowed = build_prompt_payload(stats, "Công ty A")
    # Model vẫn viết phan_bo → vẫn phải bỏ.
    sec, _bad = finalize_sections(parse_sections(_raw(phan_bo="vài câu")), stats, allowed)
    assert sec["phan_bo"] == ""


def test_hotspot_with_unknown_code_is_dropped(_=None):
    """Mã model bịa ra không được render thành link tới trang không tồn tại."""
    stats = _stats()
    _block, allowed = build_prompt_payload(stats, "Công ty A")
    raw = _raw(diem_nong=[
        {"subject_key": "NPL-X12", "nhan_xet": "thật"},
        {"subject_key": "KHONG-CO", "nhan_xet": "bịa"},
    ])
    sec, _bad = finalize_sections(parse_sections(raw), stats, allowed)
    assert [h["subject_key"] for h in sec["diem_nong"]] == ["NPL-X12"]


def test_finalize_passes_none_through(_=None):
    stats = _stats()
    _block, allowed = build_prompt_payload(stats, "Công ty A")
    sec, bad = finalize_sections(None, stats, allowed)
    assert sec is None and bad == []
