"""Cache parse phạm vi một lượt nạp (`app/adapters/parse_cache.py`).

Chẩn đoán → xem trước → nạp thật mở lại cùng workbook ba lần; với BCCT 68MB mỗi
lượt mất 97 giây nên một lần tải lên vượt 100 giây Cloudflare cho phép. Test giữ
hai điều: trong phạm vi cache mỗi (file, sheet, năm, map cột cán bộ) chỉ parse một
lần, và file đổi trên đĩa thì parse lại chứ không trả bản cũ.
"""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import pytest
from openpyxl import Workbook

from app.adapters.parse_cache import memoize_parse, parse_cache

_M15_HEADER = [
    "STT", "Mã NVL", "Tên NVL", "Đơn vị tính", "Tồn đầu kỳ", "Nhập trong kỳ",
    "Tái xuất", "Chuyển mục đích sử dụng", "Xuất sản xuất", "Xuất khác", "Tồn cuối kỳ",
]


def _m15_bytes(rows: int = 3) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "BCQT_NVL"
    for _ in range(8):
        ws.append([None] * len(_M15_HEADER))
    ws.append(_M15_HEADER)
    for i in range(rows):
        ws.append([i + 1, f"MAT{i}", "Tên", "KG", 10, 100, 0, 0, 80, 0, 30])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _write_m15(root: Path, code: str = "DN_CACHE", year: int = 2024, rows: int = 3) -> Path:
    p = root / code / str(year) / "BCQT" / f"M15_NVL_{year}.xlsx"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(_m15_bytes(rows))
    return p


def _counting():
    calls: list[tuple] = []

    def fn(path, sheet=None, year=None, officer_maps=None):
        calls.append((str(path), sheet, year))
        return f"parsed:{len(calls)}"

    return calls, memoize_parse(fn)


def test_no_cache_outside_scope(tmp_path):
    p = _write_m15(tmp_path)
    calls, cached = _counting()
    cached(p, None, 2024)
    cached(p, None, 2024)
    assert len(calls) == 2


def test_same_file_parsed_once_in_scope(tmp_path):
    p = _write_m15(tmp_path)
    calls, cached = _counting()
    with parse_cache():
        first = cached(p, None, 2024)
        second = cached(p, None, 2024)
    assert len(calls) == 1
    assert first is second


def test_scope_released_after_exit(tmp_path):
    p = _write_m15(tmp_path)
    calls, cached = _counting()
    with parse_cache():
        cached(p, None, 2024)
    with parse_cache():
        cached(p, None, 2024)
    assert len(calls) == 2


def test_sheet_and_year_are_part_of_key(tmp_path):
    p = _write_m15(tmp_path)
    calls, cached = _counting()
    with parse_cache():
        cached(p, None, 2024)
        cached(p, "BCQT_NVL", 2024)
        cached(p, None, 2025)
    assert len(calls) == 3


def test_officer_map_content_is_part_of_key(tmp_path):
    """Map cột đổi = bộ cột đọc đổi → phải parse lại, không trả bản đọc cột cũ."""
    p = _write_m15(tmp_path)
    calls, cached = _counting()
    with parse_cache():
        cached(p, None, 2024, None)
        cached(p, None, 2024, {"sig": {"closing_qty": 10}})
        cached(p, None, 2024, {"sig": {"closing_qty": 9}})
    assert len(calls) == 3


def test_equal_officer_map_content_hits_the_same_entry(tmp_path):
    """Một lượt nạp nạp map ở hai chỗ → hai dict khác danh tính, cùng nội dung.

    Khoá theo danh tính thì mỗi file mở hai lần — đúng thứ hàng đợi nạp phải tránh.
    """
    p = _write_m15(tmp_path)
    calls, cached = _counting()
    with parse_cache():
        cached(p, None, 2024, {"sig": {"closing_qty": 10, "opening_qty": 4}})
        cached(p, None, 2024, {"sig": {"opening_qty": 4, "closing_qty": 10}})
    assert len(calls) == 1


def test_file_rewritten_is_parsed_again(tmp_path):
    """Tải lên đè file trong cùng phạm vi → mtime/size đổi → không trả bản cũ."""
    p = _write_m15(tmp_path, rows=3)
    calls, cached = _counting()
    with parse_cache():
        cached(p, None, 2024)
        p.write_bytes(_m15_bytes(rows=9))
        cached(p, None, 2024)
    assert len(calls) == 2


def test_error_is_cached_and_reraised(tmp_path):
    p = _write_m15(tmp_path)
    calls: list[str] = []

    def fn(path, sheet=None, year=None, officer_maps=None):
        calls.append(str(path))
        raise ValueError("không đọc được")

    cached = memoize_parse(fn)
    with parse_cache():
        for _ in range(2):
            with pytest.raises(ValueError, match="không đọc được"):
                cached(p, None, 2024)
    assert len(calls) == 1


def test_nested_scope_shares_cache(tmp_path):
    p = _write_m15(tmp_path)
    calls, cached = _counting()
    with parse_cache():
        cached(p, None, 2024)
        with parse_cache():
            cached(p, None, 2024)
        cached(p, None, 2024)
    assert len(calls) == 1


def test_upload_pass_opens_workbook_fewer_times(tmp_path, monkeypatch):
    """Chẩn đoán + xem trước trong một phạm vi mở workbook ít lần hơn hẳn."""
    from app.pipeline.ingest import ingest
    from app.pipeline.validate import diagnose_upload

    _write_m15(tmp_path)
    opens: list[str] = []
    real_excel_file = pd.ExcelFile
    real_read_excel = pd.read_excel

    def spy_excel_file(path, *a, **kw):
        opens.append(str(path))
        return real_excel_file(path, *a, **kw)

    def spy_read_excel(io_arg, *a, **kw):
        if isinstance(io_arg, str | Path):
            opens.append(str(io_arg))
        return real_read_excel(io_arg, *a, **kw)

    monkeypatch.setattr(pd, "ExcelFile", spy_excel_file)
    monkeypatch.setattr(pd, "read_excel", spy_read_excel)

    def one_pass():
        diagnose_upload("DN_CACHE", 2024, tmp_path)
        ingest("DN_CACHE", 2024, raw_root=tmp_path, dry_run=True)

    opens.clear()
    one_pass()
    without = len(opens)

    opens.clear()
    with parse_cache():
        one_pass()
    with_cache = len(opens)

    assert without > 0
    assert with_cache < without
