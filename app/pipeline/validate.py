"""Kiểm tra dữ liệu BCQT/BCCT khi HQ tải lên — chống MISPARSE THẦM LẶNG.

Các adapter hardcode vị trí cột + sheet + dòng header (mẫu TT39/ECUS). File HQ
khác mẫu (TT38 cũ, cột đảo, header lệch dòng, sheet khác) sẽ đọc nhầm → fire sai
hoặc bỏ sót, KHÔNG báo lỗi. Module này phát hiện & giải thích bằng tiếng Việt
trước khi nạp, kèm heuristic dò cột thật để gợi ý sửa (không cần AI).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from app.adapters import parse_bcct, parse_m15, parse_m15a, parse_m16
from app.pipeline.discover import DiscoveredFiles, discover

SLOT_LABEL = {
    "m15": "Mẫu 15 — Cân đối NVL",
    "m15a": "Mẫu 15a — Cân đối SP",
    "m16": "Mẫu 16 — Định mức",
    "bcct": "BCCT — Báo cáo hàng chi tiết",
}

# Header mong đợi cho file cân đối (đồng bộ app/adapters/m15.py & m15a.py).
# field -> (cột chuẩn 0-indexed, các từ khoá nhận diện trong ô tiêu đề).
_BALANCE_EXPECT = {
    "m15": {
        "data_start": 9,
        "code": (1, ["mã nvl", "mã npl", "mã vật tư", "mã nguyên", "ma nvl"]),
        "fields": {
            "Tồn đầu": (4, ["tồn đầu", "ton dau"]),
            "Nhập trong kỳ": (5, ["nhập", "nhap"]),
            "Xuất sản xuất": (8, ["xuất sản xuất", "đưa vào", "xuat san xuat"]),
            "Tồn cuối": (10, ["tồn cuối", "ton cuoi"]),
        },
    },
    "m15a": {
        "data_start": 9,
        "code": (1, ["mã sp", "mã thành phẩm", "mã sản phẩm", "ma sp"]),
        "fields": {
            "Tồn đầu": (4, ["tồn đầu", "ton dau"]),
            "Nhập kho": (5, ["nhập", "nhap"]),
            "Xuất khẩu": (7, ["xuất khẩu", "xuất", "xuat khau"]),
            "Tồn cuối": (9, ["tồn cuối", "ton cuoi"]),
        },
    },
}


@dataclass
class Diagnostic:
    slot: str
    level: str  # "error" | "warning"
    title: str
    detail: str


@dataclass
class UploadDiagnosis:
    diagnostics: list[Diagnostic] = field(default_factory=list)
    discovered: dict[str, str | None] = field(default_factory=dict)

    @property
    def errors(self) -> list[Diagnostic]:
        return [d for d in self.diagnostics if d.level == "error"]

    @property
    def warnings(self) -> list[Diagnostic]:
        return [d for d in self.diagnostics if d.level == "warning"]

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s).strip().lower()


def _find_header_columns(path: Path, code_kw: list[str], field_kw: dict[str, list[str]]):
    """Dò dòng tiêu đề thật + vị trí từng cột theo từ khoá.

    Trả (header_row_idx, {nhãn: col_idx_thực}). header_row_idx=None nếu không thấy.
    """
    try:
        df = pd.read_excel(path, sheet_name=0, header=None, nrows=20)
    except Exception:  # noqa: BLE001
        return None, {}
    rows = df.values.tolist()
    all_kw = {"__code__": code_kw, **field_kw}
    best_row, best_hits, best_map = None, 0, {}
    for ri, raw in enumerate(rows):
        cells = [_norm(c) for c in raw]
        found: dict[str, int] = {}
        for label, kws in all_kw.items():
            for ci, cell in enumerate(cells):
                if cell and any(k in cell for k in kws):
                    found[label] = ci
                    break
        if len(found) > best_hits:
            best_hits, best_row, best_map = len(found), ri, found
    if best_hits < 2:
        return None, {}
    return best_row, best_map


def _check_balance(diag: UploadDiagnosis, slot: str, path: Path, parse_fn) -> None:
    label = SLOT_LABEL[slot]
    try:
        parsed = parse_fn(path)
    except Exception as e:  # noqa: BLE001 — surface parser error friendly
        diag.diagnostics.append(Diagnostic(
            slot, "error", f"{label}: không đọc được file",
            f"Lỗi khi phân tích ({type(e).__name__}): {e}. File có thể hỏng, bị khoá, "
            "hoặc không phải Excel hợp lệ.",
        ))
        return

    n = len(parsed.rows)
    if n == 0:
        exp = _BALANCE_EXPECT[slot]
        hrow, hmap = _find_header_columns(path, exp["code"][1], {k: v[1] for k, v in exp["fields"].items()})
        if hrow is None:
            detail = (
                "Đọc được file nhưng 0 dòng dữ liệu. Không tìm thấy dòng tiêu đề mong đợi "
                "(Mã, Tồn đầu/cuối, Nhập, Xuất). File có thể theo mẫu KHÁC (không phải Mẫu "
                "15/15a TT39), hoặc dữ liệu nằm ở sheet khác."
            )
        else:
            detail = _mismatch_detail(slot, hrow, hmap, exp)
        diag.diagnostics.append(Diagnostic(slot, "error", f"{label}: 0 dòng dữ liệu", detail))
        return

    # Có dòng nhưng cột số toàn 0 trên toàn bộ → khả năng lệch cột.
    # M15 dùng import_qty, M15a dùng intake_qty → lấy field-agnostic.
    def _inflow(r) -> float:
        return (getattr(r, "import_qty", 0) or 0) or (getattr(r, "intake_qty", 0) or 0)

    numeric_zero = all(
        (r.opening_qty or 0) == 0 and _inflow(r) == 0
        and (getattr(r, "closing_qty", 0) or 0) == 0
        for r in parsed.rows
    )
    if numeric_zero and n >= 3:
        diag.diagnostics.append(Diagnostic(
            slot, "warning", f"{label}: tất cả giá trị số = 0",
            f"Đọc được {n} dòng nhưng mọi cột số (tồn/nhập/xuất) đều bằng 0. Rất có thể "
            "cột bị lệch so với mẫu chuẩn — kiểm tra lại vị trí cột.",
        ))


def _mismatch_detail(slot: str, hrow: int, hmap: dict, exp: dict) -> str:
    """So cột tìm được với cột chuẩn → câu giải thích lệch cụ thể."""
    parts: list[str] = []
    code_exp = exp["code"][0]
    if "__code__" in hmap and hmap["__code__"] != code_exp:
        parts.append(f"cột Mã ở vị trí {hmap['__code__']} (chuẩn {code_exp})")
    for lbl, (col, _kw) in exp["fields"].items():
        if lbl in hmap and hmap[lbl] != col:
            parts.append(f"cột '{lbl}' ở vị trí {hmap[lbl]} (chuẩn {col})")
    head = f"Dò thấy dòng tiêu đề ở hàng {hrow} (mẫu chuẩn đặt dữ liệu từ hàng {exp['data_start']}). "
    if parts:
        return (head + "Các cột lệch vị trí: " + "; ".join(parts)
                + ". File theo mẫu khác TT39 → cần map lại cột.")
    return head + "Vị trí cột khớp chuẩn nhưng vẫn 0 dòng — có thể header lệch dòng hoặc mã ở định dạng lạ."


def _check_simple(diag: UploadDiagnosis, slot: str, path: Path, parse_fn, rows_attr: str = "rows") -> None:
    label = SLOT_LABEL[slot]
    try:
        parsed = parse_fn(path)
    except Exception as e:  # noqa: BLE001
        diag.diagnostics.append(Diagnostic(
            slot, "error", f"{label}: không đọc được file",
            f"Lỗi khi phân tích ({type(e).__name__}): {e}.",
        ))
        return
    if len(getattr(parsed, rows_attr)) == 0:
        extra = (
            "Mẫu 16 cần cấu trúc SP→NVL (sheet BCTT39 hoặc Sheet1)."
            if slot == "m16" else
            "BCCT cần sheet tờ khai (Sheet1) với số tờ khai 9–13 chữ số ở cột thứ 2."
        )
        diag.diagnostics.append(Diagnostic(
            slot, "error", f"{label}: 0 dòng dữ liệu",
            f"Đọc được file nhưng không trích được dòng nào. {extra} File có thể sai mẫu/sai sheet.",
        ))


def diagnose_upload(code: str, year: int, raw_root: Path) -> UploadDiagnosis:
    """Chẩn đoán bộ file đã tải cho 1 DN × năm trước khi nạp vào DB."""
    diag = UploadDiagnosis()
    try:
        files: DiscoveredFiles = discover(code, year, Path(raw_root))
    except FileNotFoundError as e:
        diag.diagnostics.append(Diagnostic(
            "m15", "error", "Không thấy thư mục dữ liệu",
            f"{e}. Hãy chắc đã tải lên ít nhất 1 file cho năm {year}.",
        ))
        return diag

    diag.discovered = {
        "m15": files.m15.name if files.m15 else None,
        "m15a": files.m15a.name if files.m15a else None,
        "m16": files.m16.name if files.m16 else None,
        "bcct": ", ".join(p.name for p in files.bcct) if files.bcct else None,
    }

    if files.m15:
        _check_balance(diag, "m15", files.m15, parse_m15)
    if files.m15a:
        _check_balance(diag, "m15a", files.m15a, parse_m15a)
    if files.m16:
        _check_simple(diag, "m16", files.m16, parse_m16)
    for p in files.bcct:
        _check_simple(diag, "bcct", p, parse_bcct)

    if not any(diag.discovered.values()):
        diag.diagnostics.append(Diagnostic(
            "m15", "error", "Không nhận diện được file nào",
            "Các file tải lên không khớp slot nào (Mẫu 15/15a/16/BCCT). Kiểm tra lại "
            "loại file và đặt đúng mục khi tải lên.",
        ))
    return diag
