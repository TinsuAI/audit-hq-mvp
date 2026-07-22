"""Chọn sheet theo NỘI DUNG thay vì theo tên.

Trước đây mỗi adapter so tên sheet với một whitelist cứng rồi rơi về `sheet_names[0]`
khi trượt. Hai kiểu hỏng đo được trên dữ liệu thật:

- Whitelist TRÚNG nhầm sheet: workbook Mẫu 15 của một DN có `Sheet1` là bảng
  "cân đối tồn kho" 9 cột (không phải Mẫu 15) và whitelist chọn đúng nó, bỏ qua
  sheet `BCQT <năm>` là biểu thật.
- Rơi về sheet 0 im lặng: sheet đầu là kỳ cũ, hoặc là biểu khác trong cùng workbook.

Điểm số ở đây KHÔNG dựa vào tiêu đề biểu, vì "BÁO CÁO QUYẾT TOÁN NHẬP-XUẤT-TỒN"
dùng chung cho cả Mẫu 15 lẫn 15a. Tín hiệu phân biệt là **nhãn cột nằm ĐÚNG vị trí
mà adapter mong đợi** — sheet đúng biểu, đúng bố cục thì nhãn khớp cả tên lẫn cột.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from app.adapters._common import normalize_code, parse_company_header, to_str
from app.adapters.layout import BALANCE_EXPECT, find_data_start, find_header_columns

# Nhãn đúng vị trí đáng giá gấp 3 nhãn chỉ đúng tên: sheet sai bố cục vẫn có thể
# khớp nhiều nhãn (bảng tồn kho có đủ tồn đầu/nhập/tồn cuối) nhưng ở cột khác.
_POSITION_WEIGHT = 3
_MIN_AT_POSITION = 2
_MIN_SCORE = 5
# Các hằng số trên là ĐO rồi chọn, không suy ra từ đâu. Dải điểm quan sát được trên
# dữ liệu thật (2026-07-22, 12 cặp DN×năm whitelist + 3 DN pilot), sheet đúng biểu:
#   m15 = 8 · m15a = 9 · m16 = 16 · bcct = 16   (mọi file đều đúng bằng các số này)
# Tức biên so với ngưỡng 5 là 3 điểm ở chỗ hẹp nhất (m15). Sửa cách chấm điểm thì
# đo lại dải này TRƯỚC, đừng chỉnh ngưỡng theo cảm tính.
# Chấm điểm chỉ cần vùng tiêu đề. File tờ khai lớn nhất trong dữ liệu thật là 71 MB /
# 6 sheet — đọc đủ mọi sheet chỉ để chấm điểm là không chấp nhận được.
_PROFILE_ROWS = 40


class SheetNotFound(LookupError):
    """Không sheet nào đạt ngưỡng — báo lỗi thay vì im lặng lấy sheet 0."""

    def __init__(self, slot: str, path: Path, scores: dict[str, int]) -> None:
        self.slot = slot
        self.path = path
        self.scores = scores
        detail = ", ".join(f"{n!r}={s}" for n, s in sorted(scores.items(), key=lambda x: -x[1]))
        super().__init__(
            f"{slot}: không sheet nào trong {path.name} khớp bố cục mong đợi "
            f"(ngưỡng {_MIN_SCORE}). Điểm từng sheet: {detail or '(không có sheet)'}"
        )


@dataclass
class SheetCandidate:
    name: str
    score: int
    colmap: dict[str, int]
    data_start: int
    row_count: int | None
    period_from: Any = None
    period_to: Any = None

    def period_rank(self, year: int) -> int:
        """2 = kỳ bắt đầu ĐÚNG năm đang nạp · 1 = năm nằm trong kỳ · 0 = không liên quan.

        Không dùng boolean: kỳ tài chính 01/04/2025–31/03/2026 vừa "bắt đầu năm 2025"
        vừa "chứa năm 2026", nên hai sheet kỳ liên tiếp sẽ cùng khớp và hoà tiếp.
        """
        if self.period_from is None:
            return 0
        if self.period_from.year == year:
            return 2
        if self.period_to is not None and self.period_from.year <= year <= self.period_to.year:
            return 1
        return 0


def _score(cells: list[list[Any]], slot: str) -> tuple[int, dict[str, int]]:
    exp = BALANCE_EXPECT[slot]
    hrow, hmap = find_header_columns(
        cells, exp["code"][1], {k: v[1] for k, v in exp["fields"].items()}
    )
    if hrow is None:
        return 0, {}
    expected = {"__code__": exp["code"][0], **{k: v[0] for k, v in exp["fields"].items()}}
    # Cột mã phải nằm ĐÚNG chỗ adapter đọc, nếu không adapter không lấy được mã dù
    # sheet có đúng biểu — coi như không dùng được, đừng cho điểm.
    if hmap.get("__code__") != expected["__code__"]:
        return 0, {}
    at_position = sum(1 for label, col in hmap.items() if expected.get(label) == col)
    # Một nhãn đúng chỗ có thể là trùng hợp: sheet tổng hợp của BCCT cũng có "Số TK"
    # ở c1 rồi lệch hết phần sau. Phải có ít nhất hai nhãn đúng chỗ.
    if at_position < _MIN_AT_POSITION:
        return 0, {}
    return _POSITION_WEIGHT * at_position + len(hmap), hmap


def _count_rows(cells: list[list[Any]], slot: str, data_start: int) -> int:
    code_col = BALANCE_EXPECT[slot]["code"][0]
    return sum(
        1
        for raw in cells[data_start:]
        if code_col < len(raw) and normalize_code(to_str(raw[code_col]))
    )


def profile_sheets(path: Path, slot: str) -> list[SheetCandidate]:
    """Chấm điểm mọi sheet. `row_count` để -1 (chưa đếm) — chỉ đếm khi cần phá hoà."""
    xls = pd.ExcelFile(path)
    out: list[SheetCandidate] = []
    for name in xls.sheet_names:
        cells = pd.read_excel(
            xls, sheet_name=name, header=None, nrows=_PROFILE_ROWS
        ).values.tolist()
        score, colmap = _score(cells, slot)
        start = find_data_start(cells, slot)
        header = parse_company_header(cells, scan_rows=14)
        out.append(SheetCandidate(
            name=name, score=score, colmap=colmap, data_start=start, row_count=None,
            period_from=header.period_from, period_to=header.period_to,
        ))
    return out


def _fill_row_count(path: Path, slot: str, cand: SheetCandidate) -> None:
    cells = pd.read_excel(path, sheet_name=cand.name, header=None).values.tolist()
    cand.row_count = _count_rows(cells, slot, cand.data_start)


def select_sheet(path: Path, slot: str, year: int | None = None) -> SheetCandidate:
    """Sheet phục vụ `slot` trong workbook `path`. Ném SheetNotFound nếu không có.

    Phá hoà: kỳ báo cáo của sheet khớp `year` trước, rồi tới số dòng dữ liệu. Hai
    sheet cùng bố cục khác kỳ (kỳ này / kỳ sau) chỉ phân biệt được bằng kỳ.
    """
    candidates = profile_sheets(path, slot)
    if not candidates:
        raise SheetNotFound(slot, path, {})

    best = max(c.score for c in candidates)
    if best < _MIN_SCORE:
        raise SheetNotFound(slot, path, {c.name: c.score for c in candidates})

    top = [c for c in candidates if c.score == best]
    if len(top) > 1 and year is not None:
        ranks = [c.period_rank(year) for c in top]
        best_rank = max(ranks)
        if best_rank > 0:
            top = [c for c, r in zip(top, ranks, strict=True) if r == best_rank]
    if len(top) > 1:
        for c in top:
            _fill_row_count(path, slot, c)
        top.sort(key=lambda c: -(c.row_count or 0))
    return top[0]


__all__ = ["SheetCandidate", "SheetNotFound", "profile_sheets", "select_sheet"]
