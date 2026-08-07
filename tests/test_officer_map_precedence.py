"""T4 (#84) — `match_source` ghi ở MỌI đường đọc + map cán bộ thắng mẫu biểu curate.

Hai lỗi nền của tầng truy nguồn (ADR #24 mục 5):

- `match_source` chỉ được sinh ở nhánh CHUẨN của Mẫu 15/15a. Mẫu 16, BCCT và nhánh
  bố cục mở rộng không sinh khoá đó, nên `data_files.match_source` rỗng trên toàn bộ
  file và ba trong bốn nhãn truy nguồn chưa bao giờ hiện.
- Map cán bộ mới thắng ở NHÃN: `resolve_officer_confirmed` nâng nguồn bằng chứng SAU
  khi parse xong, còn CHỈ SỐ CỘT lúc đọc vẫn của template/mặc định. Cán bộ sửa cột
  xong hệ thống vẫn đọc cột cũ, im lặng — đúng lớp lỗi đã làm mất 28,5 tỷ.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from openpyxl import Workbook

from app.adapters import templates as tpl_mod
from app.adapters.bcct import BcctColumnError, parse_bcct
from app.adapters.evidence import (
    BUILTIN_TEMPLATE,
    OFFICER_CONFIRMED,
    POSITION_ONLY,
)
from app.adapters.extended_layout import OfficerMapBalanceError
from app.adapters.m15 import parse_m15
from app.adapters.m15a import parse_m15a
from app.adapters.m16 import parse_m16
from app.adapters.templates import (
    MATCH_BUILTIN,
    MATCH_DEFAULT,
    MATCH_EXTENDED,
    MATCH_KEYWORD,
    MATCH_OFFICER,
    BuiltinTemplate,
)
from tests.test_bcct_columns import STANDARD_54, _rows, _write
from tests.test_builtin_templates import _m15_band_with_changed_label, m15_fixture, signature_of
from tests.test_builtin_templates import _write as _write_band


def _write_grid(path: Path, sheet: str, grid: list[list]) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = sheet
    for row in grid:
        ws.append(row)
    path.parent.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    wb.save(buf)
    path.write_bytes(buf.getvalue())
    return path


# --- Bố cục MỞ RỘNG (map suy từ dòng đánh số, chứng minh bằng đẳng thức) --------


def _m15_extended_grid() -> list[list]:
    """Chèn Mã kế toán ở c1, tách (6) thành (6a)(6b) + cột Tổng — như 004/006."""
    grid: list[list] = [[None] * 13 for _ in range(5)]
    grid.append(["(1)", "152", "(2)", None, "(5)", "(6a)", "(6b)", "(6)",
                 "(7)", "(8)", "(9)", "(10)",
                 "(11)=(5)+(6)-(7)-(8)-(9)-(10)"])
    for i in range(3):
        grid.append([i + 1, "ACC", f"MAT{i}", None, 10, 40, 60, 100, 0, 0, 80, 0, 30])
    return grid


def _m15a_extended_grid() -> list[list]:
    """Số biểu phẳng + cột con decoy; xuất khẩu chọn theo NHÃN (EPE)."""
    n = 16
    grid: list[list] = [[None] * n for _ in range(5)]
    labels: list = [None] * n
    labels[9] = "Lượng SP đăng ký tờ khai năm trước, năm nay xuất kho"
    labels[10] = "Lượng SP đăng ký tờ khai và xuất kho năm nay\nExport this year"
    labels[11] = "Lượng SP xuất bán cho DNCX khác không TTHQ"
    labels[13] = "Lượng SP xuất cho nghiên cứu sản phẩm, hư hỏng"
    grid.append(labels)
    numbering: list = [None] * n
    for col, tok in {
        0: "(1)", 2: "(2)", 3: "(3)", 4: "(4)", 5: "(5)", 6: "(6)", 7: "(7)",
        8: "(8)", 9: "(8a)", 10: "(9)", 11: "(8c)", 13: "(10)", 14: "(9c)",
        15: "(11) = (5) +(6) +(7) -(8) - (9)-(10)",
    }.items():
        numbering[col] = tok
    grid.append(numbering)
    for i in range(3):
        row: list = [None] * n
        row[0], row[2], row[3], row[4] = i + 1, f"SP{i}", f"Name{i}", "PCE"
        row[5], row[6], row[7], row[8], row[10], row[13] = 100, 10, 5, 3, 80, 2
        row[9], row[11], row[14] = 999, 888, 777
        row[15] = 30
        grid.append(row)
    return grid


# --- Mẫu 16 (tiêu đề hai tầng, parent-child) ------------------------------------


def _m16_grid(*, actual_norm: bool = False) -> list[list]:
    """Dòng cha ở hàng 9, dòng con hàng 10, dữ liệu từ hàng 11 (mẫu TT39)."""
    grid: list[list] = [[None] * 10 for _ in range(9)]
    parent: list = [
        "STT", "Mã sản phẩm", "Tên sản phẩm", "Đơn vị tính",
        "Nguyên liệu, vật tư", None, None, None, "Ghi chú", None,
    ]
    child: list = [
        None, None, None, None, "Mã", "Tên", "Đơn vị tính",
        "Lượng định mức", None, None,
    ]
    if actual_norm:
        child[7] = "Định mức kỹ thuật\nTechnical BOM"
        child[9] = "Lượng NL, VT thực tế sử dụng\nActual BOM/ Product"
    grid.append(parent)
    grid.append(child)
    grid.append([1, "SP01", "Áo sơ mi", "PCE", None, None, None, None, None, None])
    grid.append([None, None, None, None, "NVL01", "Vải chính", "MTR", 2.5, None, 7.7])
    return grid


def _m16_file(tmp_path: Path, *, actual_norm: bool = False) -> Path:
    return _write_grid(tmp_path / "m16.xlsx", "BCTT39", _m16_grid(actual_norm=actual_norm))


def _bcct_file(tmp_path: Path) -> tuple[Path, float]:
    """BCCT bố cục chuẩn + một giá trị RIÊNG ở cột `Tổng số lượng 2` để phân biệt."""
    rows = _rows(STANDARD_54)
    other = 12345.0
    for row in rows:
        row[STANDARD_54.index("Tổng số lượng 2")] = other
    p = tmp_path / "bcct.xlsx"
    _write(p, STANDARD_54, rows)
    return p, other


# --- (1) Mọi đường đọc đều nói nó quyết định cột bằng gì ------------------------


def test_m15_extended_layout_names_its_source(tmp_path):
    """Bố cục mở rộng: map suy từ dòng đánh số + đẳng thức — KHÔNG phải từ khoá."""
    parsed = parse_m15(_write_grid(tmp_path / "m15x.xlsx", "BCQT_NPL", _m15_extended_grid()))
    assert parsed.provenance.layout == "extended"
    assert parsed.provenance.detail["match_source"] == MATCH_EXTENDED
    assert parsed.rows[0].import_qty == 100  # cột Tổng (6), không phải (6a)


def test_m15a_extended_layout_names_its_source(tmp_path):
    parsed = parse_m15a(_write_grid(tmp_path / "m15ax.xlsx", "BCQT_SP", _m15a_extended_grid()))
    assert parsed.provenance.layout == "extended"
    assert parsed.provenance.detail["match_source"] == MATCH_EXTENDED
    assert parsed.rows[0].export_qty == 80


def test_m16_names_its_source(tmp_path):
    parsed = parse_m16(_m16_file(tmp_path))
    assert parsed.provenance.detail["match_source"] == MATCH_KEYWORD
    assert parsed.rows[0].norm_qty == 2.5


def test_m16_labeled_actual_norm_names_its_source(tmp_path):
    """Cột ĐM thực tế chọn theo NHÃN → nguồn là từ khoá, và nói ra."""
    parsed = parse_m16(_m16_file(tmp_path, actual_norm=True))
    assert parsed.provenance.layout == "labeled"
    assert parsed.provenance.detail["match_source"] == MATCH_KEYWORD
    assert parsed.rows[0].norm_qty == 7.7


def test_bcct_names_its_source(tmp_path):
    path, _ = _bcct_file(tmp_path)
    parsed = parse_bcct(path)
    assert parsed.provenance.detail["match_source"] == MATCH_KEYWORD
    assert parsed.rows[0].quantity == 104000.0


# --- (2) Map cán bộ thắng mẫu biểu curate ở MỨC TỪNG TRƯỜNG --------------------


@pytest.fixture
def curated_conflict(tmp_path, monkeypatch):
    """File khớp một mẫu biểu curate có map cột KHÁC mặc định.

    Trả `(đường dẫn, vân tay)`. Mẫu biểu đặt `closing_qty` ở cột 11 và
    `production_out_qty` ở cột 12 — cả hai khác vị trí mặc định của slot, nên
    ai thắng ở từng trường đọc ra con số khác hẳn.
    """
    band = _m15_band_with_changed_label()  # vân tay không trùng họ nào đã seed
    path = _write_band(
        tmp_path / "m15.xlsx", "BCQT_NPL", band, 7,
        [[1, "NVL001", "Vải chính", "MTR", 10, 100, 0, 0, 80, 0, 30, 555, 888]],
    )
    sig, data_start = signature_of(path, "m15")
    template = BuiltinTemplate(
        id="m15-test-curate",
        name="Mẫu 15 — họ curate dùng cho test",
        slot="m15",
        signatures=frozenset({sig}),
        data_start=data_start,
        column_map={"closing_qty": 11, "production_out_qty": 12},
    )
    monkeypatch.setattr(tpl_mod, "BUILTIN_TEMPLATES", (*tpl_mod.BUILTIN_TEMPLATES, template))
    return path, sig


def test_curated_template_alone_decides_the_columns(curated_conflict):
    """Không có map cán bộ → mẫu biểu quyết định cả hai cột (mốc so sánh)."""
    path, _sig = curated_conflict
    parsed = parse_m15(path)
    assert parsed.provenance.detail["match_source"] == MATCH_BUILTIN
    assert parsed.rows[0].closing_qty == 555
    assert parsed.rows[0].production_out_qty == 888


def test_officer_position_beats_the_template_per_field(curated_conflict):
    """Trường map cán bộ có → vị trí của cán bộ; trường còn lại → mẫu biểu."""
    path, sig = curated_conflict
    parsed = parse_m15(path, officer_maps={sig: {"closing_qty": 10}})

    row = parsed.rows[0]
    assert row.closing_qty == 30       # cột 10 — cán bộ chỉ định
    assert row.production_out_qty == 888  # cột 12 — mẫu biểu, cán bộ không đụng

    evidence = parsed.provenance.evidence
    assert evidence["closing_qty"] == OFFICER_CONFIRMED
    assert evidence["production_out_qty"] == BUILTIN_TEMPLATE

    detail = parsed.provenance.detail
    assert detail["match_source"] == MATCH_OFFICER
    assert detail["template_id"] == "m15-test-curate"
    # Map ghi lại phải là map ĐÃ ÁP: màn xác nhận dựng ô nhập từ đây và so cột đổi.
    assert detail["column_map"]["closing_qty"] == 10
    assert detail["column_map"]["production_out_qty"] == 12


def test_officer_map_of_another_form_signature_is_ignored(curated_conflict):
    """Khoá map là (DN, slot, vân tay) — vân tay khác thì không được áp."""
    path, _sig = curated_conflict
    parsed = parse_m15(path, officer_maps={"vantay-khac": {"closing_qty": 10}})
    assert parsed.rows[0].closing_qty == 555
    assert parsed.provenance.detail["match_source"] == MATCH_BUILTIN


def test_officer_map_ignores_fields_the_slot_does_not_read(curated_conflict):
    """Field lạ trong map lưu không được tạo cột mới, cũng không làm hỏng lượt đọc."""
    path, sig = curated_conflict
    parsed = parse_m15(path, officer_maps={sig: {"khong_co_field": 3}})
    assert parsed.provenance.detail["match_source"] == MATCH_BUILTIN
    assert parsed.rows[0].closing_qty == 555


def test_officer_position_wins_without_any_template(tmp_path):
    """Không mẫu biểu nào khớp → map cán bộ vẫn thắng cột mặc định của slot."""
    path = m15_fixture(tmp_path, band=_m15_band_with_changed_label())
    sig, _ = signature_of(path, "m15")
    parsed = parse_m15(path, officer_maps={sig: {"closing_qty": 4}})
    assert parsed.rows[0].closing_qty == 10  # cột 4 = tồn đầu, đúng cột cán bộ chỉ
    assert parsed.provenance.detail["match_source"] == MATCH_OFFICER
    assert parsed.provenance.evidence["closing_qty"] == OFFICER_CONFIRMED


def test_officer_position_wins_on_m16(tmp_path):
    path = _m16_file(tmp_path, actual_norm=True)
    sig = parse_m16(path).provenance.detail["form_signature"]
    parsed = parse_m16(path, officer_maps={sig: {"norm_qty": 7}})
    assert parsed.rows[0].norm_qty == 2.5  # cột 7, không phải cột ĐM "thực tế" (9)
    assert parsed.provenance.detail["match_source"] == MATCH_OFFICER
    assert parsed.provenance.evidence["norm_qty"] == OFFICER_CONFIRMED


def test_officer_position_wins_on_bcct(tmp_path):
    path, other = _bcct_file(tmp_path)
    sig = parse_bcct(path).provenance.detail["form_signature"]
    col = STANDARD_54.index("Tổng số lượng 2")
    parsed = parse_bcct(path, officer_maps={sig: {"quantity": col}})
    assert parsed.rows[0].quantity == other
    assert parsed.provenance.detail["match_source"] == MATCH_OFFICER
    assert parsed.provenance.evidence["quantity"] == OFFICER_CONFIRMED


def test_extended_layout_reports_an_officer_map_that_breaks_the_balance(tmp_path):
    """#95 SỬA giới hạn của #84: bố cục mở rộng NAY nhận vị trí của cán bộ.

    Map một cột duy nhất cho `import_qty` đổi `(6a)+(6b)` thành `(6a)` — đẳng thức
    của biểu vỡ, nên lượt đọc bị TỪ CHỐI kèm lý do thay vì im lặng bỏ mất `(6b)`
    hoặc im lặng quay về map suy được. Ca áp thành công ở
    `tests/test_officer_map_extended.py`.
    """
    path = _write_grid(tmp_path / "m15x.xlsx", "BCQT_NPL", _m15_extended_grid())
    sig = parse_m15(path).provenance.detail["form_signature"]
    with pytest.raises(OfficerMapBalanceError):
        parse_m15(path, officer_maps={sig: {"import_qty": 5}})
    # Không map cán bộ → vẫn là đường mở rộng như cũ.
    assert parse_m15(path).provenance.detail["match_source"] == MATCH_EXTENDED


def test_bcct_rejects_an_officer_map_that_doubles_up_a_column(tmp_path):
    """#95 — cổng trùng cột của BCCT chạy TRƯỚC lúc áp map cán bộ, nên map cán bộ
    có thể đưa hai trường về cùng một cột mà không ai chặn."""
    path, _ = _bcct_file(tmp_path)
    sig = parse_bcct(path).provenance.detail["form_signature"]
    col = STANDARD_54.index("Tổng số lượng 2")
    with pytest.raises(BcctColumnError):
        parse_bcct(path, officer_maps={sig: {"quantity": col, "unit_price": col}})


def test_position_only_file_still_names_its_source(tmp_path):
    """Không nhãn nào khớp cột nào: nguồn phải là `default`, KHÔNG được rỗng."""
    grid = _m16_grid()
    # Xoá CẢ hai dòng tiêu đề. Bằng chứng nay phủ cả 8 trường (#111), nên chỉ xoá nhãn
    # của cột mã + cột ĐM là chưa đủ: "Mã sản phẩm", "Tên sản phẩm", "Ghi chú" ở dòng
    # cha vẫn khớp từ khoá và file không còn là ca "chỉ theo vị trí" nữa.
    grid[9] = [None] * 10   # dòng tiêu đề cha
    grid[10] = [None] * 10  # dòng tiêu đề con
    path = _write_grid(tmp_path / "m16plain.xlsx", "BCTT39", grid)
    parsed = parse_m16(path)
    assert parsed.provenance.detail["match_source"] == MATCH_DEFAULT
    assert set(parsed.provenance.evidence.values()) == {POSITION_ONLY}
