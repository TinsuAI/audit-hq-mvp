"""Tests cho chọn sheet theo nội dung + dò dòng dữ liệu (A1/A2)."""

from __future__ import annotations

from pathlib import Path

import openpyxl
import pytest

from app.adapters.layout import find_data_start
from app.adapters.sheet_select import SheetNotFound, select_sheet

_M15_HEADER = ["STT", "Mã NVL", "Tên NVL", "Đơn vị tính", "Tồn đầu kỳ",
               "Nhập trong kỳ", "Tái xuất", "Chuyển MĐSD", "Xuất sản xuất",
               "Xuất khác", "Tồn cuối kỳ"]


def _write(path: Path, sheets: dict[str, list[list]]) -> None:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, grid in sheets.items():
        ws = wb.create_sheet(title=name)
        for row in grid:
            ws.append(row)
    wb.save(path)


def _m15_grid(period: str = "Kỳ báo cáo: Từ ngày 01/01/2024 đến ngày 31/12/2024",
              n_rows: int = 2) -> list[list]:
    grid: list[list] = [[period] + [None] * 10]
    grid += [[None] * 11 for _ in range(7)]
    grid.append(list(_M15_HEADER))
    for i in range(n_rows):
        grid.append([i + 1, f"MAT{i:02d}", "Vật tư", "KG", 10, 100, 0, 0, 80, 0, 30])
    return grid


def test_picks_matching_layout_over_decoy_with_shifted_columns(tmp_path: Path) -> None:
    """Sheet phụ có đủ nhãn nhưng SAI vị trí cột không được thắng sheet đúng biểu.

    Đây là ca thật: workbook Mẫu 15 có `Sheet1` là bảng cân đối tồn kho 9 cột —
    khớp nhiều nhãn hơn nhưng lệch cột, và whitelist cũ chọn đúng nó.
    """
    decoy = [["CÂN ĐỐI TỒN KHO"] + [None] * 8]
    decoy.append(["STT", "Mã NVL NK", "Mã NVL", "Tên NVL", "Đơn vị",
                  "Lượng tồn đầu kỳ", "Lượng nhập trong kỳ", "Lượng xuất trong kỳ",
                  "Lượng tồn cuối kỳ"])
    decoy.append([1, "NK-BK", "BK", "Băng keo", "Cuộn", 0, 80, 80, 0])
    p = tmp_path / "m15.xlsx"
    _write(p, {"BCQT 2024": _m15_grid(), "Sheet1": decoy})

    assert select_sheet(p, "m15", 2024).name == "BCQT 2024"


def test_tie_breaks_on_reporting_period(tmp_path: Path) -> None:
    """Hai sheet cùng bố cục, cùng số dòng — chỉ kỳ báo cáo phân biệt được."""
    p = tmp_path / "m15.xlsx"
    _write(p, {
        "BCQT_NPL 2026": _m15_grid("Kỳ báo cáo: Từ ngày 01/01/2026 đến ngày 31/12/2026"),
        "BCQT_NPL 2025": _m15_grid("Kỳ báo cáo: Từ ngày 01/01/2025 đến ngày 31/12/2025"),
    })
    assert select_sheet(p, "m15", 2025).name == "BCQT_NPL 2025"
    assert select_sheet(p, "m15", 2026).name == "BCQT_NPL 2026"


def test_raises_when_no_sheet_matches(tmp_path: Path) -> None:
    p = tmp_path / "m15.xlsx"
    _write(p, {"Tổng hợp": [["Báo cáo nội bộ"], [1, 2, 3], [4, 5, 6]]})
    with pytest.raises(SheetNotFound):
        select_sheet(p, "m15", 2024)


def test_data_start_skips_numbering_row_but_keeps_numeric_data(tmp_path: Path) -> None:
    """Dòng đánh số `(1) (2)` phải bỏ; dòng dữ liệu toàn số nguyên nhỏ phải GIỮ.

    Regression: luật nhận diện theo "chữ số trần" từng nuốt luôn dòng dữ liệu đầu.
    """
    grid: list[list] = [[None] * 11 for _ in range(8)]
    grid.append(list(_M15_HEADER))
    grid.append([f"({i})" for i in range(1, 12)])
    grid.append([1, "MAT01", "Vật tư", "KG", 10, 100, 0, 0, 80, 0, 30])
    assert find_data_start(grid, "m15") == 10


def test_data_start_falls_back_when_no_header(tmp_path: Path) -> None:
    grid = [[None] * 11 for _ in range(12)]
    assert find_data_start(grid, "m15") == 9


def test_bcct_prefers_detail_sheet_over_declaration_summary(tmp_path: Path) -> None:
    """Sheet tổng hợp cấp tờ khai cũng có "Số TK" ở c1 và số tờ khai khớp
    `_DECLARATION_RE`, nên chọn nhầm nó sinh dòng SAI chứ không phải 0 dòng."""
    def _grid(header: list) -> list[list]:
        g: list[list] = [[None] * len(header) for _ in range(9)]
        g[1] = ["", "BÁO CÁO"] + [None] * (len(header) - 2)
        g.append(header)
        g.append([1, "306974366810"] + [None] * (len(header) - 2))
        return g

    detail = _grid(["STT", "Số TK", "Ngày ĐK", "Mã loại hình", "Mã địa điểm đích",
                    "Tên địa điểm đích", "Địa điểm dỡ hàng", "Mã hiệu PTVC"])
    summary = _grid(["STT", "Số TK", "Số tờ khai đầu tiên", "Nhánh", "Ngày ĐK",
                     "Mã HQ", "Mã loại hình", "Số tờ khai tạm nhập"])
    p = tmp_path / "bcct.xlsx"
    _write(p, {"Tổng hợp": summary, "Chi tiết": detail})

    assert select_sheet(p, "bcct", 2024).name == "Chi tiết"


def test_parse_issues_reports_error_cells_and_external_links() -> None:
    from app.adapters._common import ParseIssues
    from app.pipeline.validate import UploadDiagnosis, _report_parse_issues

    clean = ParseIssues()
    assert not clean and clean.error_total == 0

    diag = UploadDiagnosis()
    _report_parse_issues(diag, "m15", type("P", (), {
        "issues": ParseIssues(error_cells={"#N/A": 276, "#REF!": 2}, external_workbooks=3)
    })())
    assert len(diag.warnings) == 1
    detail = diag.warnings[0].detail
    assert "278 ô lỗi" in detail          # tổng, không phải từng loại
    assert "#N/A ×276" in detail
    assert "3 liên kết" in detail
    assert not diag.has_errors            # cảnh báo, không chặn nạp


def test_no_warning_when_source_is_clean() -> None:
    from app.adapters._common import ParseIssues
    from app.pipeline.validate import UploadDiagnosis, _report_parse_issues

    diag = UploadDiagnosis()
    _report_parse_issues(diag, "m15", type("P", (), {"issues": ParseIssues()})())
    assert not diag.diagnostics
