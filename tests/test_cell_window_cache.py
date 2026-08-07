"""Kho đệm trích xuất một lần: dựng một lần, truy vấn khoảng dòng, vô hiệu hoá đúng.

Chế độ đọc tuần tự của thư viện .xlsx CHỈ ĐI TỚI — nhảy tới dòng 200.000 mất
3,87 giây, nên cuộn một trang 270k dòng theo cửa sổ là ~1.000 lượt đọc với chi
phí tăng dần. Kho đệm trả chi phí đó đúng một lần; test ở đây khoá đúng ba tính
chất đó: dựng một lần, cửa sổ đọc từ kho, và kho hết hiệu lực khi file đổi.
"""

from __future__ import annotations

import sqlite3
import threading

import pytest

from app.adapters import cell_window
from app.adapters.cell_window import cache_dir, extract_sheet, sheet_window
from app.settings import settings
from tests.excel_fixtures import write_biff_xls, write_spreadsheetml, write_xlsx


@pytest.fixture(autouse=True)
def _cache_in_tmp(tmp_path, monkeypatch):
    """Kho đệm về thư mục tạm — test KHÔNG được ghi vào kho của máy dev."""
    monkeypatch.setattr(settings, "preview_cache_path", tmp_path / "kho-dem", raising=False)
    monkeypatch.setattr(settings, "preview_cache_max_bytes", 50 * 1024 * 1024, raising=False)
    cell_window.reset_build_locks()
    yield


def _grid(n_rows=30, n_cols=6):
    return [[f"r{r}c{c}" for c in range(n_cols)] for r in range(n_rows)]


def test_window_reads_a_row_range_without_reopening_the_workbook(tmp_path):
    p = write_xlsx(tmp_path / "a.xlsx", _grid())

    first = sheet_window(p, 0, row_start=0, n_rows=5)
    second = sheet_window(p, 0, row_start=20, n_rows=5)

    assert first.from_cache is False
    assert second.from_cache is True
    assert second.rows[0][0] == "r20c0"
    assert len(second.rows) == 5


def test_totals_come_from_the_extraction_not_from_the_declared_dimension(tmp_path):
    """File kết xuất khai sai kích thước; thanh cuộn ảo cần số THẬT."""
    p = write_xlsx(tmp_path / "a.xlsx", _grid(12, 7))
    _lie_about_dimension(p, "A1:ZZ9999")

    w = sheet_window(p, 0, row_start=0, n_rows=3)

    assert (w.total_rows, w.total_cols) == (12, 7)


def _lie_about_dimension(path, ref: str) -> None:
    import re
    import zipfile

    src = zipfile.ZipFile(path)
    names = src.namelist()
    blobs = {n: src.read(n) for n in names}
    src.close()
    target = next(n for n in names if n.startswith("xl/worksheets/sheet1"))
    blobs[target] = re.sub(
        rb'<dimension ref="[^"]*"/>', f'<dimension ref="{ref}"/>'.encode(), blobs[target]
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for n in names:
            z.writestr(n, blobs[n])


def test_cache_lives_outside_the_raw_data_directory(tmp_path):
    p = write_xlsx(tmp_path / "a.xlsx", _grid(4, 3))
    sheet_window(p, 0)

    files = list(cache_dir().glob("*.sqlite"))
    assert files, "phải có file kho đệm"
    for f in files:
        assert not str(f.resolve()).startswith(str(settings.raw_data_path))
        assert str(f.resolve()).startswith(str(cache_dir().resolve()))


def test_a_changed_file_invalidates_the_cache(tmp_path):
    p = tmp_path / "a.xlsx"
    write_xlsx(p, [["cũ", 1]])
    assert sheet_window(p, 0).rows[0][0] == "cũ"

    write_xlsx(p, [["mới", 2, 3]])
    w = sheet_window(p, 0)

    assert w.rows[0][0] == "mới"
    assert (w.total_rows, w.total_cols) == (1, 3)


def test_extraction_runs_once_under_concurrent_first_requests(tmp_path):
    p = write_xlsx(tmp_path / "a.xlsx", _grid(50, 4))
    builds = []
    real = cell_window._build_cache

    def counting(*args, **kwargs):
        builds.append(1)
        return real(*args, **kwargs)

    cell_window._build_cache = counting
    try:
        threads = [threading.Thread(target=lambda: sheet_window(p, 0)) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    finally:
        cell_window._build_cache = real

    assert len(builds) == 1


def test_a_failed_extraction_leaves_no_half_built_cache(tmp_path, monkeypatch):
    p = write_xlsx(tmp_path / "a.xlsx", _grid(10, 3))

    def boom(*_a, **_k):
        raise RuntimeError("đọc hỏng giữa chừng")

    monkeypatch.setattr(cell_window, "open_reader", boom)
    with pytest.raises(RuntimeError):
        sheet_window(p, 0)

    assert list(cache_dir().glob("*.sqlite")) == []
    assert list(cache_dir().glob("*.tmp-*")) == []


def test_cache_is_pruned_when_it_grows_past_the_limit(tmp_path, monkeypatch):
    first = write_xlsx(tmp_path / "f0.xlsx", _grid(60, 8))
    sheet_window(first, 0)
    one = next(iter(cache_dir().glob("*.sqlite"))).stat().st_size
    limit = one * 2
    monkeypatch.setattr(settings, "preview_cache_max_bytes", limit, raising=False)

    for i in range(1, 6):
        sheet_window(write_xlsx(tmp_path / f"f{i}.xlsx", _grid(60, 8)), 0)

    kept = list(cache_dir().glob("*.sqlite"))
    assert len(kept) < 6, "kho phải bị dọn bớt"
    # Trần cộng đúng một file: file vừa dựng không bị dọn vì request này còn đọc nó.
    assert sum(f.stat().st_size for f in kept) <= limit + one
    # Dọn rồi vẫn phục vụ được — dựng lại chứ không hỏng.
    assert sheet_window(first, 0).rows[0][0] == "r0c0"


def test_rows_are_stored_one_json_array_per_row_with_sparse_formulas(tmp_path):
    """Khoá `(chỉ số trang, chỉ số dòng)`, giá trị mảng JSON, công thức từ điển thưa."""
    p = write_xlsx(
        tmp_path / "a.xlsx",
        [["Mã", "SL", "Tiền"], ["A1", 3, None]],
        formulas={(1, 2): ("=B2*100", 300)},
    )
    cache_file, _ = extract_sheet(p, 0)

    with sqlite3.connect(cache_file) as conn:
        got = conn.execute(
            "SELECT sheet_index, row_index, values_json, formulas_json FROM rows ORDER BY row_index"
        ).fetchall()

    assert [(r[0], r[1]) for r in got] == [(0, 0), (0, 1)]
    assert got[0][2].startswith("[")
    assert got[0][3] is None
    assert '"2"' in got[1][3] and "=B2*100" in got[1][3]


def test_window_serves_formulas_only_when_asked(tmp_path):
    p = write_xlsx(
        tmp_path / "a.xlsx",
        [["Mã", "Tiền"], ["A1", None]],
        formulas={(1, 1): ("=SUM(B1:B1)", 250)},
    )

    off = sheet_window(p, 0, with_formulas=False)
    on = sheet_window(p, 0, with_formulas=True)

    assert off.rows[1][1] == 250
    assert off.formulas is None
    assert on.rows[1][1] == 250
    assert on.formulas[1] == {1: "=SUM(B1:B1)"}


def test_a_row_gap_keeps_the_row_numbers_and_fills_the_gap(tmp_path):
    """Dòng bị bỏ qua trong file vẫn phải chiếm chỗ, nếu không cả lưới trượt lên."""
    p = write_spreadsheetml(tmp_path / "nhay.xls", [["đầu"], ["cuối"]], row_index={1: 6})

    w = sheet_window(p, 0, n_rows=10)

    assert w.total_rows == 6
    assert w.rows[0][0] == "đầu"
    assert w.rows[1:5] == [[None]] * 4
    assert w.rows[5][0] == "cuối"


def test_window_clamps_a_range_past_the_end_of_the_sheet(tmp_path):
    p = write_xlsx(tmp_path / "a.xlsx", _grid(5, 3))

    w = sheet_window(p, 0, row_start=900, n_rows=10, col_start=900, n_cols=10)

    assert w.rows == []
    assert (w.total_rows, w.total_cols) == (5, 3)


def test_window_pads_short_rows_to_a_rectangle(tmp_path):
    p = write_xlsx(tmp_path / "a.xlsx", [["a", "b", "c"], ["d"]])

    w = sheet_window(p, 0, n_cols=3)

    assert w.rows[1] == ["d", None, None]


def test_column_window_starts_where_asked(tmp_path):
    p = write_xlsx(tmp_path / "a.xlsx", [[f"C{i}" for i in range(257)]])

    w = sheet_window(p, 0, col_start=250, n_cols=10)

    assert w.total_cols == 257
    assert w.rows[0] == [f"C{i}" for i in range(250, 257)]


def test_extract_records_format_and_formula_support_for_each_reader(tmp_path):
    rows = [["a", 1]]
    cases = {
        write_xlsx(tmp_path / "a.xlsx", rows): (True, "xlsx"),
        write_spreadsheetml(tmp_path / "c.xls", rows): (True, "spreadsheetml"),
        write_biff_xls(tmp_path / "b.xls", rows): (False, "xls_biff"),
    }
    for path, (supported, fmt) in cases.items():
        w = sheet_window(path, 0, with_formulas=True)
        assert w.fmt == fmt
        assert w.formulas_supported is supported
        assert bool(w.formula_note) is not supported
        # Không định dạng nào được trả lưới rỗng chỉ vì thiếu công thức.
        assert w.rows and w.rows[0][0] == "a"
