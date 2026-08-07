"""Sinh file Excel THẬT cho test — ba định dạng, không commit file nhị phân nào.

Kho dữ liệu có ba định dạng và cái đuôi file nói dối (38 file đuôi `.xls` thật ra
là XML SpreadsheetML). Test của bộ đọc phải chạy trên file thật của cả ba, nên
mỗi builder ở đây sinh ra byte thật của định dạng đó:

- `write_xlsx` — zip OOXML, viết bằng `xlsxwriter` (ghi được giá trị đã tính KÈM
  công thức, thứ `openpyxl` không làm được: openpyxl lưu `<f>` mà bỏ `<v>`).
- `write_biff_xls` — OLE2/CFB + BIFF5 dựng tay bằng `struct`. Không có thư viện
  ghi `.xls` trong dự án và vé cấm thêm phụ thuộc; đây là cách duy nhất có file
  BIFF thật mà không commit file nhị phân.
- `write_spreadsheetml` — XML SpreadsheetML 2003, viết thẳng ra text.
"""

from __future__ import annotations

import struct
from datetime import datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------- xlsx (zip) --


def write_xlsx(
    path: Path,
    rows: list[list[Any]],
    *,
    sheet_name: str = "Sheet1",
    formulas: dict[tuple[int, int], tuple[str, Any]] | None = None,
    extra_sheets: dict[str, list[list[Any]]] | None = None,
) -> Path:
    """File .xlsx thật. `formulas[(dòng, cột)] = (công thức, giá trị đã tính)`.

    Giá trị đã tính là phần bắt buộc: file do Excel ghi luôn có `<v>` cạnh `<f>`,
    và chính nó là thứ lưới phải hiện khi công tắc công thức TẮT.
    """
    import xlsxwriter

    wb = xlsxwriter.Workbook(str(path), {"in_memory": True, "default_date_format": "dd/mm/yyyy"})
    ws = wb.add_worksheet(sheet_name)
    formulas = formulas or {}
    for r, row in enumerate(rows):
        for c, value in enumerate(row):
            if (r, c) in formulas:
                continue
            if value is None:
                continue
            if isinstance(value, datetime):
                ws.write_datetime(r, c, value)
            else:
                ws.write(r, c, value)
    for (r, c), (formula, cached) in formulas.items():
        ws.write_formula(r, c, formula, None, cached)
    for name, extra in (extra_sheets or {}).items():
        ws2 = wb.add_worksheet(name)
        for r, row in enumerate(extra):
            for c, value in enumerate(row):
                if value is not None:
                    ws2.write(r, c, value)
    wb.close()
    return path


# ------------------------------------------------------- SpreadsheetML (XML) --

_SSML_HEADER = """<?xml version="1.0"?>
<?mso-application progid="Excel.Sheet"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
 xmlns:o="urn:schemas-microsoft-com:office:office"
 xmlns:x="urn:schemas-microsoft-com:office:excel"
 xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
"""


def _ssml_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _ssml_cell(value: Any, formula: str | None, index: int | None) -> str:
    attrs = ""
    if index is not None:
        attrs += f' ss:Index="{index}"'
    if formula is not None:
        attrs += f' ss:Formula="{_ssml_escape(formula)}"'
    if value is None:
        return f"<Cell{attrs}/>"
    if isinstance(value, bool):
        return f'<Cell{attrs}><Data ss:Type="Boolean">{int(value)}</Data></Cell>'
    if isinstance(value, datetime):
        stamp = value.strftime("%Y-%m-%dT%H:%M:%S.000")
        return f'<Cell{attrs}><Data ss:Type="DateTime">{stamp}</Data></Cell>'
    if isinstance(value, int | float):
        return f'<Cell{attrs}><Data ss:Type="Number">{value}</Data></Cell>'
    return f'<Cell{attrs}><Data ss:Type="String">{_ssml_escape(str(value))}</Data></Cell>'


def write_spreadsheetml(
    path: Path,
    rows: list[list[Any]],
    *,
    sheet_name: str = "Sheet1",
    formulas: dict[tuple[int, int], str] | None = None,
    sparse_index: dict[tuple[int, int], int] | None = None,
    row_index: dict[int, int] | None = None,
    extra_sheets: dict[str, list[list[Any]]] | None = None,
) -> Path:
    """File XML SpreadsheetML 2003 — thường mang đuôi `.xls` dù không phải BIFF.

    `sparse_index[(dòng, cột)] = chỉ số 1-based` ghi `ss:Index` trên ô và
    `row_index[dòng] = chỉ số 1-based` ghi `ss:Index` trên dòng — hai cách file
    kết xuất bỏ qua ô/dòng rỗng thay vì ghi ra. Đọc sai là lệch cột hoặc lệch dòng.
    """
    formulas = formulas or {}
    sparse_index = sparse_index or {}
    row_index = row_index or {}
    parts = [_SSML_HEADER]
    sheets: list[tuple[str, list[list[Any]]]] = [(sheet_name, rows)]
    sheets += list((extra_sheets or {}).items())
    for name, sheet_rows in sheets:
        parts.append(f'<Worksheet ss:Name="{_ssml_escape(name)}"><Table>\n')
        for r, row in enumerate(sheet_rows):
            at = row_index.get(r) if name == sheet_name else None
            parts.append(f'<Row ss:Index="{at}">' if at else "<Row>")
            for c, value in enumerate(row):
                parts.append(_ssml_cell(value, formulas.get((r, c)), sparse_index.get((r, c))))
            parts.append("</Row>\n")
        parts.append("</Table></Worksheet>\n")
    parts.append("</Workbook>\n")
    path.write_text("".join(parts), encoding="utf-8")
    return path


# ------------------------------------------------------------ BIFF5 in OLE2 --

_BOF_WORKBOOK = 0x0005
_BOF_WORKSHEET = 0x0010


def _rec(code: int, payload: bytes) -> bytes:
    return struct.pack("<HH", code, len(payload)) + payload


def _bof(dt: int) -> bytes:
    return _rec(0x0809, struct.pack("<HHHHII", 0x0600, dt, 0x0DBB, 0x07CC, 0, 0))


def _unicode_short(text: str) -> bytes:
    """Chuỗi BIFF8 với độ dài 1 byte — cờ 0x01 = UTF-16LE, giữ được dấu tiếng Việt."""
    return bytes([len(text), 0x01]) + text.encode("utf-16-le")


def _unicode_long(text: str) -> bytes:
    return struct.pack("<HB", len(text), 0x01) + text.encode("utf-16-le")


def _biff8_stream(sheets: list[tuple[str, list[list[Any]]]]) -> bytes:
    """Substream globals + một substream mỗi trang tính, BIFF8 (version 0x0600).

    Chỉ ghi NUMBER và LABEL: `ixfe = 0` là chỉ số XF mà xlrd mặc định coi là số,
    nên không cần dựng chuỗi FONT/FORMAT/XF chỉ để mở được file. Dùng LABEL
    (chuỗi nằm ngay trong record) thay vì LABELSST để khỏi phải dựng bảng chuỗi
    dùng chung — xlrd đọc được cả hai.
    """
    sheet_streams = []
    for name, rows in sheets:
        body = [_bof(_BOF_WORKSHEET)]
        n_rows = len(rows)
        n_cols = max((len(r) for r in rows), default=0)
        body.append(_rec(0x0200, struct.pack("<IIHHH", 0, n_rows, 0, n_cols, 0)))
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                if value is None or value == "":
                    continue
                if isinstance(value, bool):
                    value = int(value)
                if isinstance(value, int | float):
                    body.append(_rec(0x0203, struct.pack("<HHHd", r, c, 0, float(value))))
                else:
                    body.append(
                        _rec(0x0204, struct.pack("<HHH", r, c, 0) + _unicode_long(str(value)))
                    )
        body.append(_rec(0x000A, b""))
        sheet_streams.append((name, b"".join(body)))

    globals_body = [_bof(_BOF_WORKBOOK), _rec(0x0042, struct.pack("<H", 0x04B0))]  # CODEPAGE UTF-16
    # BOUNDSHEET giữ OFFSET TUYỆT ĐỐI tới BOF của trang tính trong stream, nên phải
    # biết độ dài phần globals trước khi ghi.
    tails = [struct.pack("<BB", 0, 0) + _unicode_short(name) for name, _ in sheet_streams]
    globals_len = (
        sum(len(b) for b in globals_body)
        + sum(4 + 4 + len(t) for t in tails)
        + 4  # EOF
    )
    out = list(globals_body)
    pos = globals_len
    for (_, stream), tail in zip(sheet_streams, tails, strict=True):
        out.append(_rec(0x0085, struct.pack("<I", pos) + tail))
        pos += len(stream)
    out.append(_rec(0x000A, b""))
    assert sum(len(b) for b in out) == globals_len, "tính sai độ dài substream globals"
    for _, stream in sheet_streams:
        out.append(stream)
    return b"".join(out)


_FREESECT = 0xFFFFFFFF
_ENDOFCHAIN = 0xFFFFFFFE
_FATSECT = 0xFFFFFFFD
_SECTOR = 512


def _dir_entry(name: str, obj_type: int, child: int, start: int, size: int) -> bytes:
    raw = name.encode("utf-16-le") + b"\x00\x00"
    entry = raw.ljust(64, b"\x00")[:64]
    entry += struct.pack("<H", len(raw))
    entry += struct.pack("<BB", obj_type, 1)  # 1 = black
    entry += struct.pack("<III", _FREESECT, _FREESECT, child)
    entry += b"\x00" * 16  # CLSID
    entry += struct.pack("<I", 0)  # state bits
    entry += b"\x00" * 16  # creation + modified time
    entry += struct.pack("<I", start)
    entry += struct.pack("<Q", size)
    assert len(entry) == 128
    return entry


def _ole2_container(stream_name: str, payload: bytes) -> bytes:
    """Gói `payload` thành một file OLE2/CFB một stream.

    Đệm payload lên >= 4096 byte để nó nằm ở sector thường, khỏi phải dựng
    mini-FAT — phần rắc rối nhất của định dạng và không cần cho một fixture.
    """
    if len(payload) < 4096:
        payload = payload + b"\x00" * (4096 - len(payload))
    if len(payload) % _SECTOR:
        payload = payload + b"\x00" * (_SECTOR - len(payload) % _SECTOR)
    n_data = len(payload) // _SECTOR
    n_fat = 1
    while True:
        total = n_fat + 1 + n_data
        need = -(-total // (_SECTOR // 4))
        if need <= n_fat:
            break
        n_fat = need
    dir_sector = n_fat
    first_data = n_fat + 1

    fat = [_FATSECT] * n_fat + [_ENDOFCHAIN]
    for i in range(n_data):
        fat.append(_ENDOFCHAIN if i == n_data - 1 else first_data + i + 1)
    fat += [_FREESECT] * (n_fat * (_SECTOR // 4) - len(fat))

    header = bytearray(_SECTOR)
    header[0:8] = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
    struct.pack_into("<HHHHH", header, 24, 0x003E, 0x0003, 0xFFFE, 0x0009, 0x0006)
    struct.pack_into("<II", header, 40, 0, n_fat)
    struct.pack_into("<II", header, 48, dir_sector, 0)
    struct.pack_into("<III", header, 56, 0x00001000, _ENDOFCHAIN, 0)
    struct.pack_into("<II", header, 68, _ENDOFCHAIN, 0)
    difat = [i for i in range(n_fat)] + [_FREESECT] * (109 - n_fat)
    struct.pack_into("<109I", header, 76, *difat)

    directory = (
        _dir_entry("Root Entry", 5, 1, _ENDOFCHAIN, 0)
        + _dir_entry(stream_name, 2, _FREESECT, first_data, len(payload))
        + _dir_entry("", 0, _FREESECT, 0, 0) * 2
    )
    return (
        bytes(header)
        + struct.pack(f"<{len(fat)}I", *fat)
        + directory
        + payload
    )


def write_biff_xls(
    path: Path,
    rows: list[list[Any]],
    *,
    sheet_name: str = "Sheet1",
    extra_sheets: dict[str, list[list[Any]]] | None = None,
) -> Path:
    """File `.xls` BIFF thật (OLE2 + BIFF8). Không ghi công thức: BIFF lưu công
    thức ở record FORMULA mà `xlrd` không phơi ra — đúng chỗ giảm chất lượng mà
    bộ đọc phải khai báo, nên fixture không giả vờ có nó.

    Định dạng này chỉ có 256 cột, nên trang 257 cột phải test bằng .xlsx / XML."""
    sheets = [(sheet_name, rows)] + list((extra_sheets or {}).items())
    path.write_bytes(_ole2_container("Workbook", _biff8_stream(sheets)))
    return path
