"""Kho đệm trích xuất MỘT LẦN mỗi (file, trang tính) — mọi cửa sổ sau là truy vấn dòng.

Số đo dựng nên thiết kế này: mở file 71,3 MB ở chế độ đọc tuần tự chỉ mất 1,19
giây (hạn mức 25 MB cũ là hệ quả của việc đọc trọn trang bằng pandas, không phải
chi phí mở), NHƯNG chế độ đó CHỈ ĐI TỚI — nhảy tới dòng 200.000 mất 3,87 giây.
Cuộn hết một trang 270.000 dòng theo cửa sổ 200 dòng là ~1.000 lượt đọc với chi
phí tăng dần. Trích xuất trả chi phí đó đúng một lần, đổi lại nhảy tới dòng bất
kỳ là một câu truy vấn khoảng.

Kho đệm:

- một file SQLite mỗi (đường dẫn, mtime, kích thước, chỉ số trang tính) — bốn
  thứ đó nằm trong tên file nên file nguồn đổi là kho cũ tự hết hiệu lực, cùng
  quy tắc `parse_cache` đang dùng;
- ghi THEO DÒNG: khoá `(chỉ số trang, chỉ số dòng)`, giá trị là một mảng JSON,
  công thức là từ điển thưa `{cột: công thức}`. Ghi theo ô thì trang 257 cột
  thành 270.000 × 257 lượt ghi;
- dựng NGAY trong request đầu tiên sau một khoá chống dựng trùng, ghi ra file
  tạm rồi đổi tên nguyên tử — hàng đợi chạy một việc một lúc nên xếp việc trích
  xuất sau một lượt nạp dài là bắt cán bộ chờ vài phút chỉ để xem file;
- thư mục kho nằm NGOÀI thư mục dữ liệu thật (thư mục đó là liên kết tới dữ liệu
  khách) và không commit; có trần dung lượng, dọn file ít dùng nhất trước.

Số dòng/cột TỔNG lấy từ kết quả trích xuất, KHÔNG lấy từ khai báo kích thước
trong file: file kết xuất khai `A1:ZZ9999` trong khi dữ liệu có 12 dòng, mà thanh
cuộn cần số thật.

**Đo trên ba file lớn nhất kho** (07/08/2026, máy dev rảnh):

| file | trích xuất | kết quả | kho đệm | cửa sổ sau |
|---|---|---|---|---|
| `.xlsx` 71,3 MB | **164,6 s** | 243.464 dòng × 56 cột | 182 MB | 5 ms |
| XML SpreadsheetML 64,5 MB | **5,4 s** | 12.749 dòng × 23 cột | 2,9 MB | 2 ms |
| `.xls` BIFF 39,3 MB | 7,1 s | 51.599 dòng × 54 cột | 49 MB | 2 ms |

Nhảy tới dòng cuối cũng 5 ms — đúng thứ mà đọc thẳng workbook không làm được.

CHỖ KHÔNG ĐẠT, phải nói rõ: 164,6 s của file 71,3 MB vượt biên 100 giây của
Cloudflare, nên request ĐẦU TIÊN trên đúng file đó sẽ bị cắt (lỗi 524). Hai lượt
đọc `openpyxl` chiếm 130 s trong số đó (60 s lượt giá trị + 67 s lượt công thức)
— chế độ đọc tuần tự chỉ phơi được một trong hai nên không gộp được. Lượt dựng
vẫn CHẠY TIẾP sau khi máy khách rớt và kho vào chỗ bằng đổi tên nguyên tử, nên
lần bấm thứ hai có ngay; nhưng vé giao diện cần một màn chờ cho ca này chứ không
để cán bộ nhìn trang lỗi. Các file còn lại trong kho đều dưới 10 giây.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from app.adapters.cell_reader import (
    CellReadError,
    open_reader,
)
from app.settings import settings

_SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE rows (
    sheet_index INTEGER NOT NULL,
    row_index   INTEGER NOT NULL,
    values_json TEXT NOT NULL,
    formulas_json TEXT,
    PRIMARY KEY (sheet_index, row_index)
) WITHOUT ROWID;
"""

_BATCH = 2000
_TMP_ORPHAN_AGE_S = 3600

_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


@dataclass(frozen=True)
class SheetExtract:
    """Siêu dữ liệu của một lượt trích xuất. `total_*` là số ĐO ĐƯỢC, không phải số khai."""

    fmt: str
    format_label: str
    sheet_index: int
    sheet_name: str
    sheet_names: list[str]
    total_rows: int
    total_cols: int
    formulas_supported: bool
    formula_note: str | None
    build_ms: int
    from_cache: bool = False


@dataclass(frozen=True)
class CellWindow:
    extract: SheetExtract
    row_start: int
    col_start: int
    rows: list[list[Any]]
    formulas: list[dict[int, str]] | None = field(default=None)

    @property
    def fmt(self) -> str:
        return self.extract.fmt

    @property
    def format_label(self) -> str:
        return self.extract.format_label

    @property
    def total_rows(self) -> int:
        return self.extract.total_rows

    @property
    def total_cols(self) -> int:
        return self.extract.total_cols

    @property
    def formulas_supported(self) -> bool:
        return self.extract.formulas_supported

    @property
    def formula_note(self) -> str | None:
        return self.extract.formula_note

    @property
    def from_cache(self) -> bool:
        return self.extract.from_cache


def cache_dir() -> Path:
    """Thư mục kho đệm — ngoài `data/` (liên kết tới dữ liệu khách) và không commit."""
    d = Path(settings.preview_cache_path)
    d.mkdir(parents=True, exist_ok=True)
    return d


def reset_build_locks() -> None:
    """Chỉ dùng cho test — xoá khoá dựng còn treo giữa các ca."""
    with _LOCKS_GUARD:
        _LOCKS.clear()


def _lock_for(name: str) -> threading.Lock:
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(name, threading.Lock())


def cache_file_for(path: Path, sheet_index: int) -> Path:
    """Tên kho gói cả bốn thành phần vô hiệu hoá vào một băm — không lộ tên file khách."""
    st = Path(path).stat()
    key = f"{Path(path).resolve()}\0{st.st_mtime_ns}\0{st.st_size}\0{sheet_index}"
    return cache_dir() / f"{hashlib.sha256(key.encode()).hexdigest()[:32]}.sqlite"


def _read_meta(cache_file: Path) -> SheetExtract | None:
    try:
        with sqlite3.connect(f"file:{cache_file}?mode=ro", uri=True) as conn:
            raw = dict(conn.execute("SELECT key, value FROM meta").fetchall())
    except sqlite3.Error:
        return None
    if not raw or "total_rows" not in raw:
        return None
    return SheetExtract(
        fmt=raw["fmt"],
        format_label=raw["format_label"],
        sheet_index=int(raw["sheet_index"]),
        sheet_name=raw["sheet_name"],
        sheet_names=json.loads(raw["sheet_names"]),
        total_rows=int(raw["total_rows"]),
        total_cols=int(raw["total_cols"]),
        formulas_supported=raw["formulas_supported"] == "1",
        formula_note=raw["formula_note"] or None,
        build_ms=int(raw["build_ms"]),
    )


def _build_cache(src: Path, sheet_index: int, dest: Path) -> SheetExtract:
    """Đọc trọn một trang tính vào file tạm rồi đổi tên nguyên tử sang `dest`."""
    started = time.perf_counter()
    reader = open_reader(src)
    tmp = dest.with_name(f"{dest.name}.tmp-{os.getpid()}-{threading.get_ident()}")
    total_rows = total_cols = 0
    try:
        conn = sqlite3.connect(tmp)
        try:
            # Kho vứt đi được: hỏng giữa chừng thì xoá file tạm và dựng lại, nên
            # không cần nhật ký ghi — đổi lại nhanh hơn nhiều lúc chèn 243k dòng.
            conn.execute("PRAGMA journal_mode = OFF")
            conn.execute("PRAGMA synchronous = OFF")
            conn.executescript(_SCHEMA)
            batch: list[tuple] = []
            for row in reader.iter_sheet_rows(sheet_index):
                values = _trim_trailing_blanks(row.values)
                if not values and not row.formulas:
                    continue  # dòng rỗng không ghi — kho thưa, cửa sổ tự đắp lại
                width = max(len(values), max(row.formulas, default=-1) + 1)
                total_rows = max(total_rows, row.index + 1)
                total_cols = max(total_cols, width)
                batch.append((
                    sheet_index,
                    row.index,
                    json.dumps(values, ensure_ascii=False, separators=(",", ":")),
                    json.dumps(
                        {str(k): v for k, v in row.formulas.items()},
                        ensure_ascii=False, separators=(",", ":"),
                    ) if row.formulas else None,
                ))
                if len(batch) >= _BATCH:
                    conn.executemany("INSERT INTO rows VALUES (?, ?, ?, ?)", batch)
                    batch.clear()
            if batch:
                conn.executemany("INSERT INTO rows VALUES (?, ?, ?, ?)", batch)

            names = reader.sheet_names()
            sheet_name = names[sheet_index] if 0 <= sheet_index < len(names) else ""
            extract = SheetExtract(
                fmt=reader.fmt,
                format_label=reader.format_label,
                sheet_index=sheet_index,
                sheet_name=sheet_name,
                sheet_names=names,
                total_rows=total_rows,
                total_cols=total_cols,
                formulas_supported=reader.formulas_supported,
                formula_note=reader.formula_note,
                build_ms=int((time.perf_counter() - started) * 1000),
            )
            conn.executemany(
                "INSERT INTO meta VALUES (?, ?)",
                [
                    ("fmt", extract.fmt),
                    ("format_label", extract.format_label),
                    ("sheet_index", str(sheet_index)),
                    ("sheet_name", sheet_name),
                    ("sheet_names", json.dumps(names, ensure_ascii=False)),
                    ("total_rows", str(total_rows)),
                    ("total_cols", str(total_cols)),
                    ("formulas_supported", "1" if extract.formulas_supported else "0"),
                    ("formula_note", extract.formula_note or ""),
                    ("build_ms", str(extract.build_ms)),
                ],
            )
            conn.commit()
        finally:
            conn.close()
        os.replace(tmp, dest)
        return extract
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _trim_trailing_blanks(values: list[Any]) -> list[Any]:
    """Bỏ đuôi ô rỗng — file khai thừa cột thì mỗi dòng đệm hàng trăm `None`."""
    end = len(values)
    while end and (values[end - 1] is None or values[end - 1] == ""):
        end -= 1
    return list(values[:end])


def extract_sheet(path: Path, sheet_index: int = 0) -> tuple[Path, SheetExtract]:
    """Đảm bảo có kho đệm cho (file, trang tính); trả (file kho, siêu dữ liệu)."""
    src = Path(path)
    if not src.is_file():
        raise CellReadError("File không còn trên đĩa.")
    dest = cache_file_for(src, sheet_index)

    hit = _read_meta(dest) if dest.exists() else None
    if hit is not None:
        _touch(dest)
        return dest, replace(hit, from_cache=True)

    with _lock_for(dest.name):
        # Kiểm lại sau khi giành được khoá: luồng khác có thể vừa dựng xong.
        hit = _read_meta(dest) if dest.exists() else None
        if hit is not None:
            _touch(dest)
            return dest, replace(hit, from_cache=True)
        extract = _build_cache(src, sheet_index, dest)
    _prune_cache(keep=dest)
    return dest, extract


def _touch(path: Path) -> None:
    """Dấu thời gian dùng lần cuối — cơ sở để dọn file ít dùng nhất trước."""
    try:
        os.utime(path, None)
    except OSError:
        pass


def _prune_cache(keep: Path | None = None) -> None:
    limit = int(settings.preview_cache_max_bytes)
    root = cache_dir()
    now = time.time()
    for orphan in root.glob("*.tmp-*"):
        try:
            if now - orphan.stat().st_mtime > _TMP_ORPHAN_AGE_S:
                orphan.unlink(missing_ok=True)
        except OSError:
            pass
    files = []
    total = 0
    for f in root.glob("*.sqlite"):
        try:
            st = f.stat()
        except OSError:
            continue
        files.append((st.st_mtime, st.st_size, f))
        total += st.st_size
    if total <= limit:
        return
    # File vừa dựng KHÔNG bị dọn: chính request này còn phải đọc nó ra.
    for _, size, f in sorted(files):
        if total <= limit:
            break
        if keep is not None and f == keep:
            continue
        try:
            f.unlink()
            total -= size
        except OSError:
            pass


def sheet_window(
    path: Path,
    sheet_index: int = 0,
    *,
    row_start: int = 0,
    n_rows: int = 100,
    col_start: int = 0,
    n_cols: int = 40,
    with_formulas: bool = False,
) -> CellWindow:
    """Cửa sổ ô `[row_start, row_start+n_rows) × [col_start, col_start+n_cols)`.

    Chỉ số 0-based. Cửa sổ vượt quá cuối trang thì cắt về đúng phần có thật —
    không ném lỗi, vì thanh cuộn ảo hỏi quá tay là chuyện thường.
    """
    cache_file, extract = extract_sheet(Path(path), sheet_index)
    end_row = min(row_start + max(n_rows, 0), extract.total_rows)
    width = max(0, min(col_start + max(n_cols, 0), extract.total_cols) - col_start)
    if end_row <= row_start or width == 0:
        return CellWindow(extract, row_start, col_start, [], [] if with_formulas else None)

    try:
        with sqlite3.connect(f"file:{cache_file}?mode=ro", uri=True) as conn:
            found = conn.execute(
                "SELECT row_index, values_json, formulas_json FROM rows "
                "WHERE sheet_index = ? AND row_index >= ? AND row_index < ? ORDER BY row_index",
                (sheet_index, row_start, end_row),
            ).fetchall()
    except sqlite3.Error as e:
        raise CellReadError(f"Kho đệm xem trước không đọc được: {e}") from e

    by_index = {r[0]: (r[1], r[2]) for r in found}
    rows: list[list[Any]] = []
    formulas: list[dict[int, str]] = []
    for index in range(row_start, end_row):
        raw_values, raw_formulas = by_index.get(index, ("[]", None))
        values = json.loads(raw_values)[col_start:col_start + width]
        values += [None] * (width - len(values))
        rows.append(values)
        if with_formulas:
            cells = json.loads(raw_formulas) if raw_formulas else {}
            formulas.append({
                int(c): f for c, f in cells.items() if col_start <= int(c) < col_start + width
            })
    return CellWindow(extract, row_start, col_start, rows, formulas if with_formulas else None)


__all__ = [
    "CellWindow",
    "SheetExtract",
    "cache_dir",
    "cache_file_for",
    "extract_sheet",
    "reset_build_locks",
    "sheet_window",
]
