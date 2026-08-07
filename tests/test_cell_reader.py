"""Bộ đọc ô: nhận dạng theo BYTE ĐẦU, ba định dạng thật, công thức không bị nuốt.

Ba ca bắt buộc của vé #83, mỗi ca ứng với một dạng hỏng đã xảy ra:

- ô công thức — file gộp tay của 006 có 2.076 ô lưu dạng công thức mà bộ đọc trả
  về 0, mất 28,5 tỷ đồng mà không kiểm tra nào bắt được. Bộ đọc không được nuốt
  công thức, cũng không được hiện `=SUM(...)` thay cho số khi công tắc tắt.
- trang tính 257 cột — 52/170 trang tính đo được vượt 40 cột, rộng nhất 257.
- cả ba định dạng thật — đuôi file nói dối: 38 file đuôi `.xls` là XML
  SpreadsheetML, mở bằng thư viện đọc BIFF thì hỏng.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.adapters.cell_reader import (
    FORMAT_BIFF,
    FORMAT_SSML,
    FORMAT_XLSX,
    UnsupportedFileFormat,
    detect_format,
    open_reader,
)
from tests.excel_fixtures import write_biff_xls, write_spreadsheetml, write_xlsx

# ------------------------------------------------------------ nhận dạng byte --


def test_detects_xlsx_by_leading_bytes(tmp_path):
    # Đuôi nói dối theo chiều ngược lại: file zip OOXML mang đuôi `.xls`.
    p = write_xlsx(tmp_path / "bao_cao.xls", [["a", 1]])
    assert detect_format(p).kind == FORMAT_XLSX


def test_detects_biff_by_leading_bytes(tmp_path):
    p = write_biff_xls(tmp_path / "bao_cao.xls", [["a", 1]])
    assert p.read_bytes()[:4] == b"\xd0\xcf\x11\xe0"
    assert detect_format(p).kind == FORMAT_BIFF


def test_detects_spreadsheetml_under_an_xls_extension(tmp_path):
    """38 file trong kho đúng dạng này — đuôi `.xls` nhưng nội dung là XML."""
    p = write_spreadsheetml(tmp_path / "ton_kho.xls", [["a", 1]])
    assert detect_format(p).kind == FORMAT_SSML


def test_unknown_format_names_what_was_detected_and_never_the_extension(tmp_path):
    p = tmp_path / "bao_cao.xlsx"
    p.write_bytes(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")

    with pytest.raises(UnsupportedFileFormat) as err:
        open_reader(p)

    assert "PDF" in str(err.value)
    assert ".xlsx" not in str(err.value)
    assert "xlsx" not in err.value.detected.kind


def test_zip_that_is_not_a_workbook_is_reported_as_such(tmp_path):
    import zipfile

    p = tmp_path / "tai_lieu.xlsx"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("word/document.xml", "<w/>")

    with pytest.raises(UnsupportedFileFormat) as err:
        open_reader(p)
    assert "ZIP" in str(err.value)
    assert ".xlsx" not in str(err.value)


def test_truncated_workbook_is_an_error_not_a_crash(tmp_path):
    """2 file trong kho hỏng — phải ra lỗi có chữ, không phải traceback."""
    good = write_xlsx(tmp_path / "ok.xlsx", [["a", 1]])
    p = tmp_path / "hong.xlsx"
    p.write_bytes(good.read_bytes()[: len(good.read_bytes()) // 3])

    with pytest.raises(UnsupportedFileFormat) as err:
        open_reader(p)
    assert str(err.value)


def test_empty_file_is_reported_as_empty(tmp_path):
    p = tmp_path / "rong.xls"
    p.write_bytes(b"")
    with pytest.raises(UnsupportedFileFormat) as err:
        open_reader(p)
    assert "rỗng" in str(err.value).lower()


# ------------------------------------------------------------------ công thức --


def _read_sheet(path, sheet_index=0):
    reader = open_reader(path)
    return reader, list(reader.iter_sheet_rows(sheet_index))


def test_xlsx_formula_cell_keeps_both_the_number_and_the_formula(tmp_path):
    p = write_xlsx(
        tmp_path / "cong_thuc.xlsx",
        [["Mã", "SL", "Tiền"], ["A1", 3, None]],
        formulas={(1, 2): ("=B2*100", 300)},
    )

    reader, rows = _read_sheet(p)

    assert reader.formulas_supported is True
    # Giá trị: SỐ đã tính, không phải chuỗi công thức.
    assert rows[1].values[2] == 300
    assert "=B2*100" not in [str(v) for v in rows[1].values]
    # Công thức: giữ nguyên, gắn đúng chỉ số cột.
    assert rows[1].formulas == {2: "=B2*100"}
    assert rows[0].formulas == {}


def test_spreadsheetml_reads_the_formula_beside_the_value(tmp_path):
    p = write_spreadsheetml(
        tmp_path / "cong_thuc.xls",
        [["Mã", "SL"], ["A1", 3]],
        formulas={(1, 1): "=RC[-1]*2"},
    )

    reader, rows = _read_sheet(p)

    assert reader.formulas_supported is True
    assert rows[1].values[1] == 3
    assert rows[1].formulas == {1: "=RC[-1]*2"}


def test_biff_declares_that_it_cannot_read_formulas(tmp_path):
    """Giảm chất lượng có chủ ý — phải khai ra, không được im lặng trả rỗng."""
    p = write_biff_xls(tmp_path / "cu.xls", [["Mã", "SL"], ["A1", 3]])

    reader, rows = _read_sheet(p)

    assert reader.formulas_supported is False
    assert reader.formula_note  # câu nói thẳng cho giao diện
    # Lưới KHÔNG rỗng: mất công thức chứ không mất dữ liệu.
    assert [r.values for r in rows] == [["Mã", "SL"], ["A1", 3.0]]
    assert all(r.formulas == {} for r in rows)


# ---------------------------------------------------------------- 257 cột --


def _wide_rows(n_cols: int = 257):
    header = [f"C{i}" for i in range(n_cols)]
    return [header, list(range(n_cols))]


def test_xlsx_reads_all_257_columns(tmp_path):
    p = write_xlsx(tmp_path / "rong.xlsx", _wide_rows())
    _, rows = _read_sheet(p)
    assert len(rows[0].values) == 257
    assert rows[0].values[256] == "C256"
    assert rows[1].values[256] == 256


def test_biff_reads_its_own_full_width_of_256_columns(tmp_path):
    """BIFF chỉ có 256 cột — trang 257 cột trong kho không thể là file dạng này."""
    p = write_biff_xls(tmp_path / "rong.xls", _wide_rows(256))
    _, rows = _read_sheet(p)
    assert len(rows[0].values) == 256
    assert rows[0].values[255] == "C255"


def test_spreadsheetml_reads_all_257_columns(tmp_path):
    p = write_spreadsheetml(tmp_path / "rong.xls", _wide_rows())
    _, rows = _read_sheet(p)
    assert len(rows[0].values) == 257
    assert rows[0].values[256] == "C256"


# ------------------------------------------------------- ba định dạng thật --


def test_all_three_formats_read_the_same_content(tmp_path):
    rows = [["Mã", "SL", "Đơn giá"], ["NVL-1", 3, 1.5]]
    made = {
        FORMAT_XLSX: write_xlsx(tmp_path / "a.xlsx", rows),
        FORMAT_BIFF: write_biff_xls(tmp_path / "b.xls", rows),
        FORMAT_SSML: write_spreadsheetml(tmp_path / "c.xls", rows),
    }
    for kind, path in made.items():
        reader, got = _read_sheet(path)
        assert reader.fmt == kind
        assert [r.values[0] for r in got] == ["Mã", "NVL-1"]
        assert [float(r.values[1]) for r in got[1:]] == [3.0]


def test_sheet_names_come_from_the_file_in_all_three_formats(tmp_path):
    rows = [["a", 1]]
    extra = {"Tổng hợp": [["x", 2]]}
    for path in (
        write_xlsx(tmp_path / "a.xlsx", rows, sheet_name="Chi tiết", extra_sheets=extra),
        write_biff_xls(tmp_path / "b.xls", rows, sheet_name="Chi tiết", extra_sheets=extra),
        write_spreadsheetml(tmp_path / "c.xls", rows, sheet_name="Chi tiết", extra_sheets=extra),
    ):
        reader = open_reader(path)
        assert reader.sheet_names() == ["Chi tiết", "Tổng hợp"]
        assert [r.values[0] for r in reader.iter_sheet_rows(1)] == ["x"]


def test_reading_a_sheet_index_out_of_range_raises_a_named_error(tmp_path):
    from app.adapters.cell_reader import SheetOutOfRange

    for path in (
        write_xlsx(tmp_path / "a.xlsx", [["a"]]),
        write_biff_xls(tmp_path / "b.xls", [["a"]]),
        write_spreadsheetml(tmp_path / "c.xls", [["a"]]),
    ):
        reader = open_reader(path)
        with pytest.raises(SheetOutOfRange):
            list(reader.iter_sheet_rows(7))


# ------------------------------------------------------------ kiểu giá trị --


def test_dates_and_blanks_survive_as_readable_values(tmp_path):
    p = write_xlsx(
        tmp_path / "ngay.xlsx",
        [["Ngày", "Trống", "Số"], [datetime(2025, 3, 4), None, 0]],
    )
    _, rows = _read_sheet(p)
    assert str(rows[1].values[0]).startswith("2025-03-04")
    assert rows[1].values[1] in (None, "")
    assert rows[1].values[2] == 0


def test_spreadsheetml_honours_a_row_index_jump(tmp_path):
    """Dòng cũng nhảy được: dòng thứ hai khai `ss:Index="6"` là dòng 5 (0-based)."""
    p = write_spreadsheetml(
        tmp_path / "nhay_dong.xls",
        [["đầu"], ["sau khoảng trống"]],
        row_index={1: 6},
    )
    _, rows = _read_sheet(p)
    assert [r.index for r in rows] == [0, 5]
    assert rows[1].values[0] == "sau khoảng trống"


def test_spreadsheetml_honours_a_column_index_jump(tmp_path):
    """`ss:Index` là cách file kết xuất bỏ qua ô rỗng — đọc sai thì cột lệch."""
    p = write_spreadsheetml(
        tmp_path / "nhay.xls",
        [["a", "b"]],
        sparse_index={(0, 1): 5},
    )
    _, rows = _read_sheet(p)
    assert rows[0].values[0] == "a"
    assert rows[0].values[4] == "b"
    assert len(rows[0].values) == 5
