"""Bộ đọc ô thô — ba định dạng sau MỘT giao diện, nhận dạng theo BYTE ĐẦU.

Đuôi file NÓI DỐI. Đếm 493 file trong kho ra 268 `.xlsx` thật, 185 `.xls` BIFF
thật, **38 file mang đuôi `.xls` mà nội dung là XML SpreadsheetML** (190,8 MB) và
2 file hỏng. Mở nhóm 38 file đó bằng thư viện đọc BIFF thì hỏng, nên nhận dạng
đọc byte đầu: `PK` → gói ZIP OOXML · `D0CF` → OLE2/BIFF · `<?xml` → SpreadsheetML.
File không khớp dạng nào ném `UnsupportedFileFormat` NÊU ĐÚNG ĐỊNH DẠNG DÒ ĐƯỢC
và không nhắc lại cái đuôi sai.

Công thức là lý do bộ đọc này tồn tại: một bộ file gộp tay từng lưu 2.076 ô dạng
công thức mà bộ đọc trả về 0, mất 28,5 tỷ đồng không kiểm tra nào bắt được. Nên:

- `values` luôn là GIÁ TRỊ đã tính, không bao giờ là chuỗi `=SUM(...)`;
- `formulas` là từ điển THƯA `{chỉ số cột: công thức}`, giữ nguyên văn công thức;
- `.xls` BIFF **không đọc được công thức** — `xlrd` chỉ trả giá trị đã tính và
  không phân biệt được ô nào là công thức. Bộ đọc KHAI RA bằng
  `formulas_supported = False` + `formula_note`, không trả lưới rỗng im lặng.
"""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

FORMAT_XLSX = "xlsx"
FORMAT_BIFF = "xls_biff"
FORMAT_SSML = "spreadsheetml"

SSML_NS = "urn:schemas-microsoft-com:office:spreadsheet"
_SS = f"{{{SSML_NS}}}"

BIFF_FORMULA_NOTE = (
    "Định dạng sổ Excel cũ (OLE2/BIFF) không cho đọc công thức: thư viện đọc "
    "định dạng này chỉ trả về giá trị đã tính và không phân biệt được ô nào là "
    "công thức. Lưới bên dưới là giá trị thật của file, chỉ riêng công thức là "
    "không xem được."
)


class CellReadError(Exception):
    """Không đọc được file/trang tính — luôn có câu chữ, không bao giờ im lặng."""


class SheetOutOfRange(CellReadError, LookupError):
    pass


@dataclass(frozen=True)
class DetectedFormat:
    kind: str
    label: str
    supported: bool


class UnsupportedFileFormat(CellReadError):
    def __init__(self, detected: DetectedFormat) -> None:
        super().__init__(f"Không mở được file: {detected.label}.")
        self.detected = detected


@dataclass(frozen=True)
class SheetRow:
    """Một dòng đã đọc. `index` là chỉ số dòng 0-based TRONG TRANG TÍNH."""

    index: int
    values: list[Any]
    formulas: dict[int, str] = field(default_factory=dict)


# ------------------------------------------------------------- nhận dạng ----


def _label_unknown(head: bytes) -> str:
    dump = " ".join(f"{b:02X}" for b in head[:8])
    return f"Không nhận ra định dạng (byte đầu: {dump})"


def _zip_kind(path: Path) -> DetectedFormat:
    try:
        with zipfile.ZipFile(path) as z:
            names = set(z.namelist())
            if "xl/workbook.xml" in names:
                return DetectedFormat(FORMAT_XLSX, "Bảng tính Excel dạng gói ZIP (OOXML)", True)
            if "mimetype" in names and b"opendocument.spreadsheet" in z.read("mimetype"):
                return DetectedFormat("ods", "Bảng tính OpenDocument (ODS)", False)
            if any(n.startswith("word/") for n in names):
                return DetectedFormat("zip_word", "Tài liệu Word trong gói ZIP (OOXML)", False)
    except (OSError, zipfile.BadZipFile):
        return DetectedFormat("zip_broken", "Gói ZIP hỏng, không giải nén được", False)
    return DetectedFormat("zip_other", "Gói ZIP không chứa bảng tính Excel", False)


def _xml_kind(path: Path, head: bytes) -> DetectedFormat:
    probe = head
    try:
        with path.open("rb") as fh:
            probe = fh.read(8192)
    except OSError:
        pass
    text = probe.decode("utf-8", errors="ignore")
    if "\x00" in text:  # UTF-16 — bỏ byte 0 để dò chuỗi namespace
        text = probe.decode("utf-16", errors="ignore")
    if SSML_NS in text:
        return DetectedFormat(FORMAT_SSML, "XML SpreadsheetML 2003", True)
    return DetectedFormat("xml_other", "Tệp XML không phải SpreadsheetML", False)


def detect_format(path: Path) -> DetectedFormat:
    """Định dạng THẬT theo byte đầu — không hỏi tới đuôi file."""
    try:
        with path.open("rb") as fh:
            head = fh.read(512)
    except OSError as e:
        raise CellReadError(f"Không đọc được file: {type(e).__name__}") from e

    if not head:
        return DetectedFormat("empty", "Tệp rỗng (0 byte)", False)
    if head[:2] == b"PK":
        return _zip_kind(path)
    if head[:4] == b"\xd0\xcf\x11\xe0":
        return DetectedFormat(FORMAT_BIFF, "Sổ Excel cũ dạng OLE2 (BIFF)", True)
    stripped = head
    for bom in (b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff"):
        if head.startswith(bom):
            stripped = head[len(bom):]
            break
    # UTF-16 thì byte đầu vẫn là "<" rồi tới \x00, nên một phép so là đủ cho cả hai.
    if stripped[:1] == b"<":
        return _xml_kind(path, head)
    if head[:5] == b"%PDF-":
        return DetectedFormat("pdf", "Tài liệu PDF", False)
    if head[:1] == b"{" or head[:1] == b"[":
        return DetectedFormat("json", "Tệp JSON", False)
    try:
        head.decode("utf-8")
    except UnicodeDecodeError:
        return DetectedFormat("unknown", _label_unknown(head), False)
    if all(b >= 0x20 or b in (9, 10, 13) for b in head):
        return DetectedFormat("text", "Tệp văn bản thuần (có thể là CSV)", False)
    return DetectedFormat("unknown", _label_unknown(head), False)


# --------------------------------------------------------- chuẩn hoá giá trị --


def normalise_value(v: Any) -> Any:
    """Về kiểu JSON ghi được. Ngày thành chuỗi đọc được, NaN/Inf thành chuỗi.

    `allow_nan=False` của tầng JSON sẽ ném lỗi nếu để lọt NaN, nên chặn tại đây.
    """
    if v is None or isinstance(v, bool | int | str):
        return v
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return str(v)
        return v
    if isinstance(v, datetime):
        if (v.hour, v.minute, v.second, v.microsecond) == (0, 0, 0, 0):
            return v.strftime("%Y-%m-%d")
        return v.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(v, date):
        return v.strftime("%Y-%m-%d")
    if isinstance(v, time):
        return v.strftime("%H:%M:%S")
    return str(v)


def _formula_text(raw: Any) -> str | None:
    """Chuỗi công thức của một ô, hoặc None nếu ô không phải công thức.

    `openpyxl` chế độ đọc tuần tự trả công thức thường dạng `"=..."`, còn công
    thức mảng là đối tượng `ArrayFormula` — lấy `.text` chứ không `str()`, vì
    `str()` của đối tượng đó là repr, không phải công thức.
    """
    if isinstance(raw, str):
        return raw if raw.startswith("=") else None
    text = getattr(raw, "text", None)
    if isinstance(text, str) and text:
        return text if text.startswith("=") else f"={text}"
    return None


# --------------------------------------------------------------- bộ đọc ----


class CellReader:
    """Giao diện chung. `fmt` là định dạng dò được, không phải đuôi file."""

    fmt: str = ""
    formulas_supported: bool = False
    formula_note: str | None = None

    def __init__(self, path: Path, detected: DetectedFormat) -> None:
        self.path = Path(path)
        self.detected = detected

    @property
    def format_label(self) -> str:
        return self.detected.label

    def sheet_names(self) -> list[str]:
        raise NotImplementedError

    def iter_sheet_rows(self, sheet_index: int) -> Iterator[SheetRow]:
        raise NotImplementedError

    def _check_index(self, sheet_index: int, names: list[str]) -> None:
        if not 0 <= sheet_index < len(names):
            raise SheetOutOfRange(
                f"Không có trang tính chỉ số {sheet_index} — file có {len(names)} trang tính."
            )


class XlsxReader(CellReader):
    """`.xlsx` đọc tuần tự. Hai lượt: giá trị đã tính và công thức, đi song song.

    Chế độ đọc tuần tự chỉ phơi được MỘT trong hai (`data_only`), mà lưới cần cả
    hai: số để hiện khi công tắc tắt, công thức để hiện khi bật. Mở hai workbook
    rồi kéo song song từng dòng — vẫn là một vòng lặp, không nhảy lùi lần nào.
    """

    fmt = FORMAT_XLSX
    formulas_supported = True

    def sheet_names(self) -> list[str]:
        try:
            with zipfile.ZipFile(self.path) as z:
                root = ET.fromstring(z.read("xl/workbook.xml"))
        except (OSError, zipfile.BadZipFile, ET.ParseError, KeyError) as e:
            raise CellReadError(f"Không đọc được danh sách trang tính: {type(e).__name__}") from e
        names = [
            el.get("name") for el in root.iter()
            if el.tag.rpartition("}")[2] == "sheet" and el.get("name")
        ]
        return [n for n in names if n]

    def iter_sheet_rows(self, sheet_index: int) -> Iterator[SheetRow]:
        from itertools import zip_longest

        from openpyxl import load_workbook

        names = self.sheet_names()
        self._check_index(sheet_index, names)
        name = names[sheet_index]
        wb_values = load_workbook(self.path, read_only=True, data_only=True)
        wb_formulas = load_workbook(self.path, read_only=True, data_only=False)
        try:
            ws_values = wb_values[name]
            ws_formulas = wb_formulas[name]
            if not hasattr(ws_values, "iter_rows"):
                raise CellReadError(
                    f"Trang tính “{name}” không phải trang dữ liệu (biểu đồ) nên không có ô để xem."
                )
            pairs = zip_longest(
                ws_values.iter_rows(values_only=True),
                ws_formulas.iter_rows(values_only=True),
                fillvalue=(),
            )
            for index, (values, raw_formulas) in enumerate(pairs):
                formulas = {}
                for col, raw in enumerate(raw_formulas):
                    text = _formula_text(raw)
                    # So với lượt giá trị: ô chữ gõ tay bắt đầu bằng "=" thì hai
                    # lượt trả về CÙNG một chuỗi — đó là chữ, không phải công thức.
                    if text is not None and (col >= len(values) or values[col] != raw):
                        formulas[col] = text
                yield SheetRow(index, [normalise_value(v) for v in values], formulas)
        finally:
            wb_values.close()
            wb_formulas.close()


class BiffReader(CellReader):
    """`.xls` BIFF qua `xlrd`. KHÔNG đọc được công thức — khai ra, xem docstring module."""

    fmt = FORMAT_BIFF
    formulas_supported = False
    formula_note = BIFF_FORMULA_NOTE

    def __init__(self, path: Path, detected: DetectedFormat) -> None:
        super().__init__(path, detected)
        import xlrd

        try:
            self._book = xlrd.open_workbook(str(self.path), on_demand=True)
        except Exception as e:  # noqa: BLE001 — OLE2 nhưng không phải sổ Excel
            raise UnsupportedFileFormat(
                DetectedFormat(
                    "ole2_other",
                    f"Tệp OLE2 nhưng không phải sổ Excel đọc được ({type(e).__name__})",
                    False,
                )
            ) from e

    def sheet_names(self) -> list[str]:
        return list(self._book.sheet_names())

    def iter_sheet_rows(self, sheet_index: int) -> Iterator[SheetRow]:
        import xlrd

        names = self.sheet_names()
        self._check_index(sheet_index, names)
        sheet = self._book.sheet_by_index(sheet_index)
        datemode = self._book.datemode
        try:
            for r in range(sheet.nrows):
                values = []
                for c in range(sheet.ncols):
                    kind = sheet.cell_type(r, c)
                    raw = sheet.cell_value(r, c)
                    if kind == xlrd.XL_CELL_DATE:
                        try:
                            raw = xlrd.xldate_as_datetime(raw, datemode)
                        except Exception:  # noqa: BLE001 — số ngày sai thì giữ số thô
                            pass
                    elif kind == xlrd.XL_CELL_BOOLEAN:
                        raw = bool(raw)
                    elif kind == xlrd.XL_CELL_ERROR:
                        raw = xlrd.error_text_from_code.get(raw, "#ERR")
                    elif kind in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK):
                        raw = None
                    values.append(normalise_value(raw))
                yield SheetRow(r, values, {})
        finally:
            try:
                self._book.unload_sheet(sheet_index)
            except Exception:  # noqa: BLE001 — dọn bộ nhớ, hỏng thì thôi
                pass


class SpreadsheetMLReader(CellReader):
    """XML SpreadsheetML 2003 — 38 file trong kho mang đuôi `.xls` nhưng là dạng này.

    Đọc bằng `xml.etree.ElementTree.iterparse` của thư viện chuẩn (không thêm phụ
    thuộc); công thức nằm ngay ở thuộc tính `ss:Formula` cạnh giá trị nên định
    dạng này có đủ cả hai công tắc. Phải tôn trọng `ss:Index` (nhảy cột/dòng) và
    `ss:MergeAcross` — đọc sai thì cột lệch âm thầm.
    """

    fmt = FORMAT_SSML
    formulas_supported = True

    def __init__(self, path: Path, detected: DetectedFormat) -> None:
        super().__init__(path, detected)
        self._names: list[str] | None = None

    def sheet_names(self) -> list[str]:
        if self._names is None:
            names: list[str] = []
            for _, el in self._iterparse(("start",)):
                if el.tag == f"{_SS}Worksheet":
                    names.append(el.get(f"{_SS}Name") or f"Trang {len(names) + 1}")
            self._names = names
        return list(self._names)

    def _iterparse(self, events: tuple[str, ...]):
        try:
            yield from ET.iterparse(str(self.path), events=events)
        except ET.ParseError as e:
            raise CellReadError(f"XML hỏng, không đọc hết được: {e}") from e

    @staticmethod
    def _cell_value(cell: ET.Element) -> Any:
        data = cell.find(f"{_SS}Data")
        if data is None or data.text is None:
            return None
        text = "".join(data.itertext())
        kind = data.get(f"{_SS}Type")
        if kind == "Number":
            try:
                num = float(text)
            except ValueError:
                return text
            return int(num) if num.is_integer() and abs(num) < 2**53 else num
        if kind == "Boolean":
            return text.strip() in ("1", "true", "True")
        if kind == "DateTime":
            for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
                try:
                    return normalise_value(datetime.strptime(text, fmt))
                except ValueError:
                    continue
            return text
        return text

    def iter_sheet_rows(self, sheet_index: int) -> Iterator[SheetRow]:
        names: list[str] = []
        current = -1
        table: ET.Element | None = None
        row_cursor = 0
        seen_target = False

        for event, el in self._iterparse(("start", "end")):
            tag = el.tag
            if event == "start":
                if tag == f"{_SS}Worksheet":
                    current += 1
                    names.append(el.get(f"{_SS}Name") or f"Trang {current + 1}")
                    row_cursor = 0
                elif tag == f"{_SS}Table" and current == sheet_index:
                    table = el
                continue

            if tag == f"{_SS}Row" and current == sheet_index:
                seen_target = True
                index_attr = el.get(f"{_SS}Index")
                row_index = int(index_attr) - 1 if index_attr else row_cursor
                yield SheetRow(row_index, *self._read_row(el))
                row_cursor = row_index + 1
                el.clear()
                if table is not None:
                    try:
                        table.remove(el)
                    except ValueError:
                        pass
            elif tag == f"{_SS}Worksheet":
                if current == sheet_index:
                    table = None
                el.clear()

        self._names = names
        if not seen_target:
            self._check_index(sheet_index, names)

    @staticmethod
    def _read_row(row_el: ET.Element) -> tuple[list[Any], dict[int, str]]:
        values: list[Any] = []
        formulas: dict[int, str] = {}
        col = 0
        for cell in row_el.findall(f"{_SS}Cell"):
            index_attr = cell.get(f"{_SS}Index")
            if index_attr:
                col = int(index_attr) - 1
            while len(values) < col:
                values.append(None)
            values.append(normalise_value(SpreadsheetMLReader._cell_value(cell)))
            formula = cell.get(f"{_SS}Formula")
            if formula:
                formulas[col] = formula
            merge = cell.get(f"{_SS}MergeAcross")
            col += 1 + (int(merge) if merge and merge.isdigit() else 0)
        return values, formulas


_READERS: dict[str, type[CellReader]] = {
    FORMAT_XLSX: XlsxReader,
    FORMAT_BIFF: BiffReader,
    FORMAT_SSML: SpreadsheetMLReader,
}


def open_reader(path: Path) -> CellReader:
    """Bộ đọc hợp với NỘI DUNG file. Ném `UnsupportedFileFormat` nếu không dạng nào khớp."""
    detected = detect_format(Path(path))
    reader_cls = _READERS.get(detected.kind) if detected.supported else None
    if reader_cls is None:
        raise UnsupportedFileFormat(detected)
    return reader_cls(Path(path), detected)


__all__ = [
    "BIFF_FORMULA_NOTE",
    "FORMAT_BIFF",
    "FORMAT_SSML",
    "FORMAT_XLSX",
    "CellReadError",
    "CellReader",
    "DetectedFormat",
    "SheetOutOfRange",
    "SheetRow",
    "UnsupportedFileFormat",
    "detect_format",
    "normalise_value",
    "open_reader",
]
