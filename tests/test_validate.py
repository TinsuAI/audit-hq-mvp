"""Tests cho app/pipeline/validate.py — chẩn đoán file BCQT khi nạp."""

from __future__ import annotations

from pathlib import Path

import openpyxl

from app.pipeline.validate import diagnose_upload


def _write(path: Path, sheet: str, grid: list[list]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet
    for row in grid:
        ws.append(row)
    wb.save(path)


def _good_m15_grid() -> list[list]:
    # 9 hàng tiêu đề + dữ liệu từ hàng 9 (cột chuẩn TT39).
    grid = [["Tên tổ chức: CTY DEMO"] + [None] * 10]
    grid += [[None] * 11 for _ in range(8)]
    # row_no, code, name, unit, opening, import, reexport, repurpose, prod, other, closing
    grid.append([1, "MAT01", "Vật tư A", "KG", 10, 100, 0, 0, 80, 0, 30])
    grid.append([2, "MAT02", "Vật tư B", "KG", 5, 50, 0, 0, 40, 0, 15])
    return grid


def test_good_m15_no_errors(tmp_path: Path) -> None:
    _write(tmp_path / "DN_X" / "2024" / "BCQT" / "Mau15_NVL.xlsx", "BCQT_NPL", _good_m15_grid())
    diag = diagnose_upload("DN_X", 2024, tmp_path)
    assert not diag.has_errors, [d.title for d in diag.errors]


def test_good_m15a_no_errors(tmp_path: Path) -> None:
    # Regression: M15a dùng intake_qty (không có import_qty) — không được crash.
    grid = [["Tên tổ chức: CTY DEMO"] + [None] * 9]
    grid += [[None] * 10 for _ in range(8)]
    # row_no, code, name, unit, opening, intake, repurpose, export, other, closing
    grid.append([1, "SP01", "Áo sơ mi", "Cái", 10, 100, 0, 80, 0, 30])
    grid.append([2, "SP02", "Quần kaki", "Cái", 5, 50, 0, 40, 0, 15])
    _write(tmp_path / "DN_X" / "2024" / "BCQT" / "Mau15a_SP.xlsx", "BCQT_SP", grid)
    diag = diagnose_upload("DN_X", 2024, tmp_path)
    assert not diag.has_errors, [d.title for d in diag.errors]


def test_shifted_m15_reports_column_mismatch(tmp_path: Path) -> None:
    # Cột lệch +2: Mã NVL ở cột 3, Tồn cuối ở cột 12. Header ở hàng 5.
    grid = [[None] * 13 for _ in range(5)]
    grid.append([None, None, None, "Mã NVL", "Tên", "ĐVT", "Tồn đầu", "Nhập",
                 None, None, "Xuất sản xuất", None, "Tồn cuối"])
    for i in range(3):
        grid.append([None, None, None, f"MAT0{i}", "Tên", "KG", 10, 100, 0, 0, 80, 0, 30])
    _write(tmp_path / "DN_X" / "2024" / "BCQT" / "Mau15_NVL.xlsx", "Sheet1", grid)

    diag = diagnose_upload("DN_X", 2024, tmp_path)
    assert diag.has_errors
    err = diag.errors[0]
    assert err.slot == "m15"
    # heuristic nêu vị trí cột thực tế (3 cho Mã, 12 cho Tồn cuối)
    assert "vị trí" in err.detail.lower()
    assert "12" in err.detail or "Tồn cuối" in err.detail


def test_empty_dir_reports_error(tmp_path: Path) -> None:
    (tmp_path / "DN_X" / "2024").mkdir(parents=True)
    diag = diagnose_upload("DN_X", 2024, tmp_path)
    assert diag.has_errors


def test_unreadable_bcct_reports_error(tmp_path: Path) -> None:
    p = tmp_path / "DN_X" / "2024" / "HANG_CHI_TIET" / "BCCT.xlsx"
    p.parent.mkdir(parents=True)
    p.write_bytes(b"not an excel file")
    diag = diagnose_upload("DN_X", 2024, tmp_path)
    assert diag.has_errors
    assert any(d.slot == "bcct" for d in diag.errors)
