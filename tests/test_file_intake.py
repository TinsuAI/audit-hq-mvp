"""Gợi ý loại tài liệu cho một file vừa thả (#88) — tên trước, nội dung sau, có ngưỡng.

Thứ tự phân giải đo được: khớp tên là tức thì; mở nội dung mất 0,14–0,20 giây với
biểu quyết toán nhỏ nhưng **96,93 giây** với file 71,3MB, và dò nội dung KHÔNG nhận
ra BCCT trong mọi trường hợp (chỉ thử ba biểu quyết toán). Nên: tên không phân giải
được + file lớn ⇒ đi thẳng vào danh sách cán bộ tự chọn, KHÔNG mở file.

Từ ngữ: "nhận ra" chỉ dành cho file ĐÃ MỞ và khớp bố cục. Khớp tên là **gợi ý**.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.pipeline import file_intake
from app.pipeline.file_intake import (
    BASIS_CONTENT,
    BASIS_NAME,
    BASIS_OFFICER,
    CONTENT_PROBE_MAX_BYTES,
    propose,
    slot_from_name,
)
from tests.helpers import m15_xlsx_bytes


@pytest.mark.parametrize(
    ("filename", "slot"),
    [
        ("NhapXuatTon_NVL_2024.xlsx", "m15"),
        ("Bao cao NPL 2024.xls", "m15"),
        ("M15_2024.xlsx", "m15"),
        ("M15a_SP_2024.xlsx", "m15a"),
        ("Mau 15a - thanh pham.xlsx", "m15a"),
        ("BCDM_TT39_2024.xlsx", "m16"),
        ("Bao cao dinh muc 2024.xlsx", "m16"),
        ("BaoCaoHangChiTiet_2024.xlsx", "bcct"),
        ("BCCT_F1.xlsx", "bcct"),
    ],
)
def test_name_alone_resolves_the_four_families(filename: str, slot: str):
    assert slot_from_name(filename) == slot


@pytest.mark.parametrize("filename", ["BaoCao.xlsx", "Book1.xlsx", "2024.xls"])
def test_a_name_with_no_marker_does_not_resolve(filename: str):
    assert slot_from_name(filename) is None


def test_a_name_match_never_opens_the_file(tmp_path: Path, monkeypatch):
    """Khớp tên là tức thì — mở file ở đây là trả 96,93 giây cho thứ đã biết."""
    opened: list[Path] = []
    monkeypatch.setattr(
        file_intake, "content_slots", lambda p, y=None: opened.append(p) or ()
    )
    p = tmp_path / "NhapXuatTon_NVL_2024.xlsx"
    p.write_bytes(m15_xlsx_bytes())

    result = propose(p, year=2024)

    assert (result.slot, result.basis) == ("m15", BASIS_NAME)
    assert opened == []


def test_a_name_that_does_not_resolve_falls_back_to_opening_a_small_file(tmp_path: Path):
    p = tmp_path / "BaoCao.xlsx"
    p.write_bytes(m15_xlsx_bytes())

    result = propose(p, year=2024)

    assert (result.slot, result.basis) == ("m15", BASIS_CONTENT)


def test_a_large_file_that_the_name_does_not_resolve_is_never_opened(
    tmp_path: Path, monkeypatch
):
    """File 71,3MB mất 96,93 giây để dò — cán bộ chờ ngần ấy là hỏng luồng."""
    calls: list[Path] = []
    monkeypatch.setattr(
        file_intake, "content_slots", lambda p, y=None: calls.append(p) or ("m15",)
    )
    p = tmp_path / "BaoCao.xlsx"
    p.write_bytes(m15_xlsx_bytes())

    result = propose(p, year=2024, size_bytes=CONTENT_PROBE_MAX_BYTES + 1)

    assert (result.slot, result.basis) == (None, None)
    assert calls == []
    assert not result.resolved


def test_a_file_exactly_at_the_threshold_is_still_opened(tmp_path: Path, monkeypatch):
    calls: list[Path] = []
    monkeypatch.setattr(
        file_intake, "content_slots", lambda p, y=None: calls.append(p) or ("m16",)
    )
    p = tmp_path / "BaoCao.xlsx"
    p.write_bytes(m15_xlsx_bytes())

    result = propose(p, year=2024, size_bytes=CONTENT_PROBE_MAX_BYTES)

    assert (result.slot, result.basis) == ("m16", BASIS_CONTENT)
    assert calls == [p]


def test_content_that_matches_nothing_leaves_the_choice_to_the_officer(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setattr(file_intake, "content_slots", lambda p, y=None: ())
    p = tmp_path / "BaoCao.xlsx"
    p.write_bytes(m15_xlsx_bytes())

    result = propose(p, year=2024)

    assert (result.slot, result.basis) == (None, None)


def test_content_matching_several_slots_proposes_one_in_display_order(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setattr(file_intake, "content_slots", lambda p, y=None: ("m15a", "m15"))
    p = tmp_path / "BaoCao.xlsx"
    p.write_bytes(m15_xlsx_bytes())

    assert propose(p, year=2024).slot == "m15"


def test_the_basis_wording_separates_a_guess_from_an_opened_file():
    """`nhận ra` chỉ dành cho file đã mở. Khớp tên phải nói rõ là chưa mở file."""
    from app.pipeline.file_intake import BASIS_LABEL_VI

    assert "chưa mở file" in BASIS_LABEL_VI[BASIS_NAME]
    assert "nhận ra" not in BASIS_LABEL_VI[BASIS_NAME]
    assert "đã mở file" in BASIS_LABEL_VI[BASIS_CONTENT]
    assert BASIS_LABEL_VI[BASIS_OFFICER] == "cán bộ chọn"
