"""Gen bộ data demo để UPLOAD: anonymize file Excel GỐC (giữ nguyên format/cấu
trúc/cột/sheet thật), gom về `demo-data/` theo đúng slot upload.

KHÁC với export-từ-DB: script đọc chính các file canonical mà `discover()` chọn,
chỉ thay PII (tên DN, MST, địa chỉ, NCC) — giữ nguyên layout để upload chạy
ingest + checks tái hiện đúng demo. Vì là file thật anonymize, nó "sống" và đúng
cấu trúc HQ sẽ gặp, không phải bảng phẳng do DB sinh ra.

Phạm vi: 4 DN demo × mọi năm có trong DB. DN_003 (Hoa Sen) năm 2024 được nhúng
lại 7 sai phạm inject (§6.3, từ db-data/injected_changes.json) để giữ kịch bản
combo của demo.

Output gitignored (chứa dữ liệu anonymize — CLAUDE.md cấm commit).

Usage:
    python -m scripts.gen_demo_data            # gen + verify
    python -m scripts.gen_demo_data --verify-only
"""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import sys
import unicodedata
from pathlib import Path

import openpyxl
import pandas as pd

from app.adapters._common import normalize_code, normalize_name, safe_get, to_date, to_str
from app.pipeline.discover import discover
from app.settings import settings

ROOT = Path(__file__).resolve().parent.parent
OUT_ROOT = ROOT / "demo-data"
MAPPING_FILE = ROOT / "db-data" / "anonymize_mapping.json"

# real DN -> demo code (4 DN demo). Năm lấy từ DB (mọi năm có data).
DEMO: dict[str, dict] = {
    "GROWATT": {"code": "DN_001", "brand": "Phương Đông", "years": [2023, 2024, 2025],
                "tokens": ["GROWATT"]},
    "KIM_LONG": {"code": "DN_002", "brand": "Tiên Phong", "years": [2024, 2025],
                 "tokens": ["KIM LONG", "KIMLONG"]},
    "HONG_AN": {"code": "DN_003", "brand": "Hoa Sen", "years": [2021, 2022, 2023, 2024, 2025],
                "tokens": ["HỒNG AN", "HONG AN"]},
    "DO_THANH": {"code": "DN_004", "brand": "Nam Tiến", "years": [2024],
                 "tokens": ["ĐÔ THÀNH", "DO THANH"]},
}

# Sai phạm inject DN_003 2024 (giá trị cuối cùng đúng trong DB — xem
# db-data/injected_changes.json). Field -> cột M15 (0-indexed).
_M15_COL = {
    "opening_qty": 4, "import_qty": 5, "reexport_qty": 6, "repurpose_qty": 7,
    "production_out_qty": 8, "other_out_qty": 9, "closing_qty": 10,
}
_M15_DATA_START = 9
_M15_CODE_COL = 1

INJECT_DN003_2024: dict[str, dict[str, float]] = {
    "DG": {"closing_qty": -150.0},
    "KHUY": {"closing_qty": 203456.0},
    "DD-2": {"opening_qty": 0.0, "import_qty": 0.0, "production_out_qty": 500.0},
    "HDG": {"repurpose_qty": 250.0, "production_out_qty": 0.0},
}

# BCCT cột (0-indexed) — đồng bộ app/adapters/bcct.py.
_BC_DECL_NO = 1
_BC_DECL_DATE = 2
_BC_COMP_TAX = 47
_BC_COMP_NAME = 48
_BC_PARTNER = 49
_BC_DATA_START = 10
_BC_SHEETS = ("Sheet1", "Sheet 1", "BCCT")
_DECL_RE = re.compile(r"^\d{9,13}$")

# ĐM (Mẫu 16) thuộc bộ BCQT → gộp chung folder BCQT với M15/M15a.
_OUT_NAMES = {
    "m15": ("BCQT", "Mau15_NVL_{y}.xlsx"),
    "m15a": ("BCQT", "Mau15a_SP_{y}.xlsx"),
    "m16": ("BCQT", "Mau16_DinhMuc_{y}.xlsx"),
    "bcct": ("HANG_CHI_TIET", "BCCT_{y}.xlsx"),
}


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _load_mapping() -> dict:
    return json.loads(MAPPING_FILE.read_text(encoding="utf-8"))


def _company_pii(mapping: dict, real: str) -> dict:
    """Lấy (orig_name, orig_tax, orig_addr, demo_name, demo_tax, demo_addr) cho 1 DN."""
    info = next(v for v in mapping["companies"].values() if v.get("original_code") == real)
    return {
        "orig_name": info.get("original_name"),
        "orig_tax": info.get("original_tax_id"),
        "orig_addr": info.get("original_address"),
        "demo_name": info["new_name"],
        "demo_tax": info["new_tax_id"],
        "demo_addr": info["new_address"],
    }


def _partner_alias_map(mapping: dict) -> dict[str, str]:
    """normalized original partner -> alias (đảo từ mapping alias->original)."""
    out: dict[str, str] = {}
    for alias, orig in mapping["partners"].items():
        key = normalize_name(orig)
        if key:
            out[key] = alias
    return out


def _make_replacer(pii: dict, tokens: list[str], brand: str):
    """Trả hàm repl(str)->str thay mọi PII công ty (tên/MST/địa chỉ + brand token)."""
    pairs: list[tuple[str, str]] = []
    if pii["orig_name"]:
        pairs.append((pii["orig_name"], pii["demo_name"]))
    if pii["orig_tax"]:
        pairs.append((pii["orig_tax"], pii["demo_tax"]))
    if pii["orig_addr"]:
        pairs.append((pii["orig_addr"], pii["demo_addr"]))
    token_res = [(re.compile(re.escape(t), re.IGNORECASE), brand) for t in tokens]

    def repl(s: str) -> str:
        for a, b in pairs:
            if a and a in s:
                s = s.replace(a, b)
        for rx, b in token_res:
            if rx.search(s):
                s = rx.sub(b, s)
        return s

    return repl


def _clean(v):
    """Chuẩn hoá cell pandas -> giá trị openpyxl ghi được."""
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    if isinstance(v, pd.Timestamp):
        return v.to_pydatetime()
    item = getattr(v, "item", None)
    if callable(item) and v.__class__.__module__ == "numpy":
        return v.item()
    return v


# ---------- anonymize từng loại file ----------

def _scrub_xlsx_inplace(src: Path, dest: Path, repl, inject: dict | None = None) -> None:
    """M15/M15a/M16 .xlsx: copy + sửa cell tại chỗ (giữ style/sheet/formula)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)
    wb = openpyxl.load_workbook(dest)
    # data_only=True đọc giá trị cache của ô công thức (vd closing = =E+F-...).
    # Nếu không bake, openpyxl lưu lại công thức nhưng pandas đọc lại = 0.
    wb_vals = openpyxl.load_workbook(dest, data_only=True)
    for ws in wb.worksheets:
        wsv = wb_vals[ws.title]
        for row in ws.iter_rows():
            for cell in row:
                if cell.data_type == "f":  # công thức → bake giá trị cache
                    cell.value = wsv[cell.coordinate].value
                elif isinstance(cell.value, str):
                    nv = repl(cell.value)
                    if nv != cell.value:
                        cell.value = nv
    if inject:
        _apply_inject_m15(wb.worksheets[0], inject)
    wb.save(dest)


def _grid_to_xlsx(src: Path, dest: Path, repl, sheet_name: str,
                  inject: dict | None = None) -> None:
    """M16 .xls -> .xlsx: copy nguyên lưới (giữ vị trí cột/header), anonymize string."""
    xls = pd.ExcelFile(src)
    sheet = sheet_name if sheet_name in xls.sheet_names else xls.sheet_names[0]
    grid = pd.read_excel(xls, sheet_name=sheet, header=None).values.tolist()
    dest.parent.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.Workbook(write_only=True)
    ws = wb.create_sheet(title=sheet)
    for raw in grid:
        out = []
        for v in raw:
            cv = _clean(v)
            out.append(repl(cv) if isinstance(cv, str) else cv)
        ws.append(out)
    wb.save(dest)
    if inject:  # M16 không inject hiện tại — chừa hook
        raise NotImplementedError


def _apply_inject_m15(ws, inject: dict) -> None:
    """Áp sai phạm inject vào sheet M15 (openpyxl, row 1-indexed)."""
    seen = set()
    for row in ws.iter_rows(min_row=_M15_DATA_START + 1):
        if len(row) <= _M15_CODE_COL:
            continue
        code = normalize_code(to_str(row[_M15_CODE_COL].value))
        if code in inject and code not in seen:
            seen.add(code)
            for field, val in inject[code].items():
                ci = _M15_COL[field]
                if ci < len(row):
                    row[ci].value = val
    missing = set(inject) - seen
    if missing:
        print(f"    ⚠ inject: không thấy mã {missing} trong M15", file=sys.stderr)


_bcct_grid_cache: dict[Path, list] = {}


def _read_bcct_grid(src: Path) -> list:
    if src not in _bcct_grid_cache:
        xls = pd.ExcelFile(src)
        sheet = next((s for s in _BC_SHEETS if s in xls.sheet_names), xls.sheet_names[0])
        _bcct_grid_cache[src] = pd.read_excel(xls, sheet_name=sheet, header=None).values.tolist()
    return _bcct_grid_cache[src]


def _build_bcct(srcs: list[Path], year: int, dest: Path, repl,
                pii: dict, palias: dict[str, str]) -> int:
    """Gộp BCCT nhiều file, lọc theo năm tờ khai (như ingest), anonymize, ghi 1 file.

    Trả số dòng dữ liệu giữ lại.
    """
    header_rows: list | None = None
    data_rows: list = []
    for src in srcs:
        grid = _read_bcct_grid(src)
        if header_rows is None:
            header_rows = grid[:_BC_DATA_START]
        for raw in grid[_BC_DATA_START:]:
            dno = normalize_code(to_str(safe_get(raw, _BC_DECL_NO)))
            if not dno or not _DECL_RE.match(dno):
                continue
            ddate = to_date(safe_get(raw, _BC_DECL_DATE))
            row_year = ddate.year if ddate else year
            if row_year != year:
                continue
            data_rows.append(raw)

    dest.parent.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.Workbook(write_only=True)
    ws = wb.create_sheet(title="Sheet1")

    for raw in (header_rows or []):
        ws.append([repl(c) if isinstance(c := _clean(v), str) else c for v in raw])

    for raw in data_rows:
        out = [_clean(v) for v in raw]
        # đệm độ dài để chắc chắn có cột partner
        if len(out) <= _BC_PARTNER:
            out += [None] * (_BC_PARTNER + 1 - len(out))
        for i, v in enumerate(out):
            if isinstance(v, str):
                out[i] = repl(v)
        if out[_BC_COMP_TAX] not in (None, ""):
            out[_BC_COMP_TAX] = pii["demo_tax"]
        if out[_BC_COMP_NAME] not in (None, ""):
            out[_BC_COMP_NAME] = pii["demo_name"]
        pv = normalize_name(to_str(out[_BC_PARTNER]))
        if pv:
            out[_BC_PARTNER] = palias.get(pv) or f"NCC_UNK_{abs(hash(pv)) % 10**6:06d}"
        ws.append(out)

    wb.save(dest)
    return len(data_rows)


# ---------- driver ----------

def generate() -> list[dict]:
    mapping = _load_mapping()
    palias = _partner_alias_map(mapping)
    if OUT_ROOT.exists():
        shutil.rmtree(OUT_ROOT)
    raw_root = Path(settings.raw_data_path)
    manifest: list[dict] = []

    for real, cfg in DEMO.items():
        code = cfg["code"]
        pii = _company_pii(mapping, real)
        folder = pii["demo_name"]  # folder theo TÊN DN đã anonymize (không dùng mã DN_xxx)
        repl = _make_replacer(pii, cfg["tokens"], cfg["brand"])
        for year in cfg["years"]:
            d = discover(real, year, raw_root)
            entry = {"code": code, "name": folder, "year": year, "files": {}}
            inj = INJECT_DN003_2024 if (code == "DN_003" and year == 2024) else None

            if d.m15:
                sub, name = _OUT_NAMES["m15"]
                dest = OUT_ROOT / folder / str(year) / sub / name.format(y=year)
                _scrub_xlsx_inplace(d.m15, dest, repl, inject=inj)
                entry["files"]["m15"] = dest.name
            if d.m15a:
                sub, name = _OUT_NAMES["m15a"]
                dest = OUT_ROOT / folder / str(year) / sub / name.format(y=year)
                _scrub_xlsx_inplace(d.m15a, dest, repl)
                entry["files"]["m15a"] = dest.name
            if d.m16:
                sub, name = _OUT_NAMES["m16"]
                dest = OUT_ROOT / folder / str(year) / sub / name.format(y=year)
                if d.m16.suffix.lower() == ".xlsx":
                    _scrub_xlsx_inplace(d.m16, dest, repl)
                else:
                    _grid_to_xlsx(d.m16, dest, repl, sheet_name="BCTT39")
                entry["files"]["m16"] = dest.name
            if d.bcct:
                sub, name = _OUT_NAMES["bcct"]
                dest = OUT_ROOT / folder / str(year) / sub / name.format(y=year)
                n = _build_bcct(d.bcct, year, dest, repl, pii, palias)
                entry["files"]["bcct"] = f"{dest.name} ({n} dòng)"
            inj_note = " [INJECT §6.3]" if inj else ""
            manifest.append(entry)
            print(f"  {code} {year}: {list(entry['files'])}{inj_note}")

    _write_manifest(manifest)
    return manifest


def _write_manifest(manifest: list[dict]) -> None:
    lines = [
        "# Bộ data demo để UPLOAD (anonymize từ file gốc, giữ format thật)",
        "",
        "Thư mục đặt theo TÊN DN (đã anonymize). Mỗi DN × năm: vào trang DN >",
        "Tải lên dữ liệu, chọn năm, gắn file theo slot:",
        "  - Mẫu 15  (NVL)  ← BCQT/Mau15_NVL_*.xlsx",
        "  - Mẫu 15a (SP)   ← BCQT/Mau15a_SP_*.xlsx",
        "  - Mẫu 16  (ĐM)   ← BCQT/Mau16_DinhMuc_*.xlsx   (ĐM nằm trong bộ BCQT)",
        "  - BCCT           ← HANG_CHI_TIET/BCCT_*.xlsx",
        "",
        "May Mặc Hoa Sen / 2024 đã nhúng sai phạm inject §6.3 (combo demo).",
        "",
        "## Các DN trong bộ data (tên ↔ mã hệ thống ↔ năm)",
    ]
    by_name: dict[str, dict] = {}
    for e in manifest:
        d = by_name.setdefault(e["name"], {"code": e["code"], "years": []})
        d["years"].append(e["year"])
    for name, d in by_name.items():
        years = ", ".join(str(y) for y in d["years"])
        lines.append(f"  {name}  [{d['code']}]  —  năm: {years}")
    (OUT_ROOT / "README.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def verify() -> int:
    """Quét rò rỉ PII: mọi cell trong output không được chứa tên/MST/token thật."""
    mapping = _load_mapping()
    bad_tax = {v.get("original_tax_id") for v in mapping["companies"].values() if v.get("original_tax_id")}
    token_res = []
    for cfg in DEMO.values():
        for t in cfg["tokens"]:
            tok = _strip_accents(t).lower()
            token_res.append((tok, re.compile(rf"\b{re.escape(tok)}\b")))
    token_res = list({t: rx for t, rx in token_res}.items())

    files = sorted(OUT_ROOT.rglob("*.xlsx"))
    if not files:
        print("⚠ Không có file output để verify.", file=sys.stderr)
        return 1
    leaks: list[str] = []
    bcct_partner_leak = 0
    for f in files:
        xls = pd.ExcelFile(f)
        for sheet in xls.sheet_names:
            grid = pd.read_excel(xls, sheet_name=sheet, header=None).values.tolist()
            for ri, raw in enumerate(grid):
                for ci, v in enumerate(raw):
                    if not isinstance(v, str):
                        continue
                    low = _strip_accents(v).lower()
                    for tok, rx in token_res:
                        if rx.search(low):
                            leaks.append(f"{f.relative_to(OUT_ROOT)} [{sheet}] r{ri}c{ci}: token '{tok}'")
                    for tax in bad_tax:
                        if tax and tax in v:
                            leaks.append(f"{f.relative_to(OUT_ROOT)} [{sheet}] r{ri}c{ci}: MST '{tax}'")
            # BCCT partner column phải toàn NCC_
            if "BCCT" in f.name and sheet == "Sheet1":
                for raw in grid[_BC_DATA_START:]:
                    p = to_str(safe_get(raw, _BC_PARTNER))
                    if p and not p.startswith("NCC_"):
                        bcct_partner_leak += 1

    print(f"\n=== Verify {len(files)} file ===")
    if leaks:
        print(f"❌ {len(leaks)} rò rỉ PII:")
        for ln in leaks[:30]:
            print("   ", ln)
        return 1
    if bcct_partner_leak:
        print(f"❌ {bcct_partner_leak} dòng BCCT còn partner KHÔNG phải NCC_")
        return 1
    print("✅ Sạch: không tìm thấy tên/MST/token DN thật, partner toàn NCC_.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true", help="Chỉ quét rò rỉ PII trên output hiện có.")
    args = parser.parse_args(argv)
    if not args.verify_only:
        print("=== Gen demo upload data ===")
        generate()
        print(f"\nOutput: {OUT_ROOT}")
    return verify()


if __name__ == "__main__":
    sys.exit(main())
