"""Kiểm tra dữ liệu BCQT/BCCT khi HQ tải lên — chống MISPARSE THẦM LẶNG.

Các adapter hardcode vị trí cột + sheet + dòng header (mẫu TT39/ECUS). File HQ
khác mẫu (TT38 cũ, cột đảo, header lệch dòng, sheet khác) sẽ đọc nhầm → fire sai
hoặc bỏ sót, KHÔNG báo lỗi. Module này phát hiện & giải thích bằng tiếng Việt
trước khi nạp, kèm heuristic dò cột thật để gợi ý sửa (không cần AI).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from app.adapters import parse_bcct, parse_m15, parse_m15a, parse_m16
from app.adapters.evidence import FIELD_LABEL_VI
from app.adapters.layout import BALANCE_EXPECT, find_header_columns
from app.adapters.sheet_select import SheetNotFound
from app.pipeline.discover import DiscoveredFiles, discover

SLOT_LABEL = {
    "m15": "Mẫu 15 — Cân đối NVL",
    "m15a": "Mẫu 15a — Cân đối SP",
    "m16": "Mẫu 16 — Định mức",
    "bcct": "BCCT — Báo cáo hàng chi tiết",
}

# Header mong đợi cho file cân đối — định nghĩa ở app/adapters/layout.py để adapter
# và chẩn đoán dùng CHUNG một bộ từ khoá (adapter không import ngược được module này).
_BALANCE_EXPECT = BALANCE_EXPECT


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


def _find_header_columns(
    path: Path, code_kw: list[str], field_kw: dict[str, list[str]], sheet: str | int = 0,
):
    """Dò dòng tiêu đề thật + vị trí từng cột theo từ khoá, TRÊN SHEET ĐÃ CHỌN.

    Đọc sheet 0 là sai khi adapter chọn sheet khác — lời giải thích lệch cột sẽ mô tả
    một sheet không hề được nạp.

    Trả (header_row_idx, {nhãn: col_idx_thực}). header_row_idx=None nếu không thấy.
    """
    try:
        df = pd.read_excel(path, sheet_name=sheet, header=None, nrows=20)
    except Exception:  # noqa: BLE001
        return None, {}
    return find_header_columns(df.values.tolist(), code_kw, field_kw)


def _check_balance(
    diag: UploadDiagnosis, slot: str, path: Path, parse_fn, year: int | None = None,
    sheet: str | None = None,
) -> None:
    label = SLOT_LABEL[slot]
    try:
        parsed = parse_fn(path, sheet, year)
    except SheetNotFound as e:
        # Không sheet nào khớp bố cục. Vẫn dò tiêu đề để nói ĐƯỢC lệch ở đâu —
        # "không chọn được sheet" một mình thì cán bộ không sửa được gì.
        exp = _BALANCE_EXPECT[slot]
        # Giải thích trên sheet ĐIỂM CAO NHẤT, không phải sheet 0.
        scores = e.scores
        probe = max(scores, key=lambda n: scores[n]) if scores else 0
        hrow, hmap = _find_header_columns(
            path, exp["code"][1], {k: v[1] for k, v in exp["fields"].items()}, probe
        )
        detail = _mismatch_detail(slot, hrow, hmap, exp) if hrow is not None else str(e)
        diag.diagnostics.append(Diagnostic(
            slot, "error", f"{label}: không chọn được sheet đúng biểu", detail,
        ))
        return
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
        hrow, hmap = _find_header_columns(
            path, exp["code"][1], {k: v[1] for k, v in exp["fields"].items()},
            parsed.sheet if parsed.sheet is not None else 0,
        )
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

    _report_parse_issues(diag, slot, parsed)


def _report_parse_issues(diag: UploadDiagnosis, slot: str, parsed) -> None:
    """Ô lỗi Excel + liên kết ngoài — cảnh báo, KHÔNG đổi số liệu đã nạp."""
    issues = getattr(parsed, "issues", None)
    if not issues:
        return
    label = SLOT_LABEL[slot]
    parts: list[str] = []
    if issues.error_cells:
        breakdown = ", ".join(f"{k} ×{v}" for k, v in sorted(issues.error_cells.items()))
        parts.append(
            f"{issues.error_total} ô lỗi Excel trong vùng dữ liệu ({breakdown}). "
            "Các ô này nạp vào thành 0 hoặc chuỗi rác, không phải số liệu thật."
        )
    if issues.external_workbooks:
        parts.append(
            f"{issues.external_workbooks} liên kết tới workbook NGOÀI bộ dữ liệu. "
            "Giá trị đang đọc là bản cache của lần mở gần nhất; nếu liên kết gãy "
            "thì các ô đó lặng lẽ về 0 mà không có dấu hiệu nào."
        )
    if issues.formula_cells:
        breakdown = ", ".join(
            f"{FIELD_LABEL_VI.get(f, f)} ×{n}"
            for f, n in sorted(issues.formula_cells.items())
        )
        parts.append(
            f"{issues.formula_total} ô công thức ghi thành chuỗi thay vì số "
            f"({breakdown}). Hệ thống lấy giá trị kết quả trong ô nên số liệu vẫn "
            "đúng, nhưng file đã qua một công cụ gộp/xuất khác — đối chiếu lại tổng "
            "với file gốc trước khi dùng."
        )
    diag.diagnostics.append(Diagnostic(
        slot, "warning", f"{label}: nguồn số liệu cần truy nguyên", " ".join(parts),
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


def _check_simple(
    diag: UploadDiagnosis, slot: str, path: Path, parse_fn,
    rows_attr: str = "rows", year: int | None = None, sheet: str | None = None,
) -> None:
    label = SLOT_LABEL[slot]
    try:
        parsed = parse_fn(path, sheet, year)
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
            "BCCT cần sheet CHI TIẾT hàng hoá (không phải sheet tổng hợp cấp tờ khai)."
        )
        diag.diagnostics.append(Diagnostic(
            slot, "error", f"{label}: 0 dòng dữ liệu",
            f"Đọc được file nhưng không trích được dòng nào. {extra} File có thể sai mẫu/sai sheet.",
        ))
        return
    _report_parse_issues(diag, slot, parsed)


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

    # Trang tính cán bộ đã ghim — chẩn đoán PHẢI đọc đúng trang mà lượt nạp sẽ đọc.
    # Bỏ qua thì file được ghim trang vẫn trượt ở bước chẩn đoán và không bao giờ tới
    # được bước nạp: cán bộ ghim xong mà vẫn thấy nguyên lỗi cũ.
    from app.pipeline.ingest import sheet_overrides
    picked = sheet_overrides(code, year, Path(raw_root))

    if files.m15:
        _check_balance(diag, "m15", files.m15, parse_m15, year, picked.get(str(files.m15)))
    if files.m15a:
        _check_balance(diag, "m15a", files.m15a, parse_m15a, year, picked.get(str(files.m15a)))
    if files.m16:
        _check_simple(diag, "m16", files.m16, parse_m16, year=year, sheet=picked.get(str(files.m16)))
    for p in files.bcct:
        _check_simple(diag, "bcct", p, parse_bcct, year=year, sheet=picked.get(str(p)))

    if not any(diag.discovered.values()):
        diag.diagnostics.append(Diagnostic(
            "m15", "error", "Không nhận diện được file nào",
            "Các file tải lên không khớp slot nào (Mẫu 15/15a/16/BCCT). Kiểm tra lại "
            "loại file và đặt đúng mục khi tải lên.",
        ))
    return diag
