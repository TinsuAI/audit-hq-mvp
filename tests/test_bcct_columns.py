"""Cột BCCT đọc theo NHÃN tiêu đề, không theo vị trí cố định (mở rộng WS1, #63).

Fixture là bố cục THẬT quan sát trong `data/` (nhãn cột là cấu trúc biểu mẫu ECUS,
không phải dữ liệu DN) + vài dòng dữ liệu bịa. Ba bố cục:

- 54 cột — bố cục chuẩn, 8 DN đã kiểm dùng nó. Bản đồ theo nhãn phải BẰNG ĐÚNG `_COL`
  ở cả 19 trường: đường nhãn nay thay `_COL` cho mọi DN, một alias sai thứ tự ưu tiên
  sẽ dời cột im lặng.
- 50 cột — thiếu 5 cột giữa, thêm "Trọng lượng hàng" cuối; 16 trường lệch `_COL`.
- 55 cột — chèn thêm cột "Tên" sau "Tên hàng"; 11 trường lệch `_COL` (lệch đúng 1 cột).
"""

from __future__ import annotations

import io
from datetime import date
from pathlib import Path

import pytest
from openpyxl import Workbook

from app.adapters.bcct import _COL, BcctColumnError, parse_bcct
from app.adapters.evidence import HEADER_MATCHED, POSITION_ONLY

# Dòng tiêu đề bố cục chuẩn (hàng 9, dữ liệu từ hàng 10).
STANDARD_54 = [
    "STT", "Số TK", "Ngày ĐK", "Mã loại hình", "Mã địa điểm đích",
    "Tên địa điểm đích cho vận chuyển bảo thuế", "Địa điểm dỡ hàng", "Mã hiệu PTVC",
    "Ngày khởi hành vận chuyển", "Ký hiệu và số hiệu bao bì", "Tỷ giá thanh toán",
    "Đơn vị tiền tệ", "Số lượng kiện", "Mã ĐVT kiện", "Trọng lượng",
    "Mã ĐVT trọng lượng", "Số quản lý nội bộ", "Điều kiện giá hóa đơn", "Ghi chú",
    "STT hàng", "Mã NPL/SP", "Mã HS", "Tên hàng", "Xuất xứ", "Đơn giá",
    "Đơn giá tính thuế", "Tổng số lượng", "Đơn vị tính", "Tổng số lượng 2",
    "Đơn vị tính 2", "Trị giá NT", "Tổng trị giá", "Mã biểu thuế XNK",
    "Thuế suất XNK", "Tiền thuế XNK", "Số tiền miễn thuế XNK", "Thuế suất TV",
    "Tiền thuế TV", "Thuế suất PB", "Tiền thuế PB", "Thuế suất TTĐB",
    "Tiền thuế TTĐB", "Thuế suất BVMT", "Tiền thuế MT", "Thuế suất VA",
    "Tiền thuế VAT", "Tổng tiền thuế", "Mã doanh nghiệp", "Tên doanh nghiệp",
    "Tên đối tác", "Số hóa đơn", "Ngày hóa đơn", "Số hợp đồng", "Ngày hợp đồng",
]

# Bố cục 50 cột: bỏ 5 cột giữa, thêm "Trọng lượng hàng" ở cuối.
_DROPPED_50 = {
    "Địa điểm dỡ hàng", "Ghi chú", "Tổng số lượng 2", "Đơn vị tính 2",
    "Mã biểu thuế XNK",
}
LAYOUT_50 = [h for h in STANDARD_54 if h not in _DROPPED_50] + ["Trọng lượng hàng"]

# Bố cục 55 cột: chèn cột "Tên" ngay sau "Tên hàng" — mọi cột từ đó lệch 1.
LAYOUT_55 = list(STANDARD_54)
LAYOUT_55.insert(STANDARD_54.index("Tên hàng") + 1, "Tên")

_FIELDS = tuple(_COL)


def _write(path: Path, header: list[str], rows: list[list]) -> None:
    """Workbook 1 sheet: 9 dòng đầu (2 dòng tổng như file thật), tiêu đề hàng 9."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    width = len(header)
    for _ in range(6):
        ws.append([None] * width)
    ws.append(["Tổng trị giá:", None, 123456] + [None] * (width - 3))
    ws.append(["Tổng tiền thuế:", None, 0] + [None] * (width - 3))
    ws.append([None] * width)
    ws.append(list(header))
    for r in rows:
        ws.append(r)
    path.parent.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    wb.save(buf)
    path.write_bytes(buf.getvalue())


def _rows(header: list[str]) -> list[list]:
    out = []
    for i in (1, 2):
        row: list = [None] * len(header)
        row[header.index("STT")] = i
        row[header.index("Số TK")] = f"10000000{i:02d}"
        row[header.index("Ngày ĐK")] = date(2024, 6, 15)
        row[header.index("Mã loại hình")] = "E31"
        row[header.index("STT hàng")] = i
        row[header.index("Mã NPL/SP")] = f"NPL-TEST-{i}"
        row[header.index("Mã HS")] = "39269099"
        row[header.index("Tên hàng")] = "Hàng thử nghiệm"
        row[header.index("Xuất xứ")] = "CN"
        row[header.index("Đơn giá")] = 1.25
        row[header.index("Đơn giá tính thuế")] = 31250.0
        row[header.index("Tổng số lượng")] = 104000.0
        row[header.index("Đơn vị tính")] = "KILO-GRAMMES"
        row[header.index("Đơn vị tiền tệ")] = "USD"
        row[header.index("Trị giá NT")] = 100880.0
        row[header.index("Tổng trị giá")] = 2522000000.0
        row[header.index("Tổng tiền thuế")] = 0.0
        row[header.index("Mã doanh nghiệp")] = "0100000000"
        row[header.index("Tên doanh nghiệp")] = "CÔNG TY THỬ NGHIỆM"
        row[header.index("Tên đối tác")] = "TEST PARTNER CO LTD"
        row[header.index("Số hóa đơn")] = f"INV-TEST-{i}"
        row[header.index("Ngày hợp đồng")] = date(2020, 8, 25)
        out.append(row)
    return out


def _parsed(tmp_path: Path, header: list[str], name: str = "bcct.xlsx"):
    p = tmp_path / name
    _write(p, header, _rows(header))
    return parse_bcct(p)


def _column_map(res) -> dict[str, int]:
    return res.provenance.detail["column_map"]


def _expected(header: list[str]) -> dict[str, int]:
    """Cột đúng của từng trường, đọc thẳng từ nhãn trong fixture."""
    label = {
        "declaration_no": "Số TK", "declaration_date": "Ngày ĐK",
        "customs_code": "Mã loại hình", "line_no": "STT hàng",
        "item_code": "Mã NPL/SP", "hs_code": "Mã HS", "item_name": "Tên hàng",
        "origin": "Xuất xứ", "unit_price": "Đơn giá", "quantity": "Tổng số lượng",
        "unit": "Đơn vị tính", "currency": "Đơn vị tiền tệ",
        "value_foreign": "Trị giá NT", "value_total": "Tổng trị giá",
        "tax_total": "Tổng tiền thuế", "company_tax_id": "Mã doanh nghiệp",
        "company_name": "Tên doanh nghiệp", "partner": "Tên đối tác",
        "invoice_no": "Số hóa đơn",
    }
    return {f: header.index(lbl) for f, lbl in label.items()}


def _assert_values(res) -> None:
    """Giá trị rơi đúng trường — bản đồ sai vẫn parse "thành công" nên phải soi giá trị."""
    assert res.company_tax_id == "0100000000"
    assert res.company_name == "CÔNG TY THỬ NGHIỆM"
    assert len(res.rows) == 2
    r = res.rows[0]
    assert r.declaration_no == "1000000001"
    assert r.item_code == "NPL-TEST-1"
    assert r.quantity == 104000.0          # "Tổng số lượng", KHÔNG phải Trị giá NT
    assert r.unit == "KILO-GRAMMES"        # "Đơn vị tính", KHÔNG phải Tổng trị giá
    assert r.unit_price == 1.25            # "Đơn giá", KHÔNG phải Đơn giá tính thuế
    assert r.value_foreign == 100880.0
    assert r.value_total == 2522000000.0
    assert r.currency == "USD"
    assert r.partner == "TEST PARTNER CO LTD"


def test_standard_54_label_map_equals_col(tmp_path: Path) -> None:
    """Bố cục chuẩn: map theo nhãn BẰNG ĐÚNG `_COL` ở cả 19 trường (chống hồi quy)."""
    res = _parsed(tmp_path, STANDARD_54)
    assert _column_map(res) == _COL
    assert res.provenance.evidence == {f: HEADER_MATCHED for f in _FIELDS}
    assert res.provenance.layout == "standard"
    _assert_values(res)


def test_layout_50_resolves_every_field_by_label(tmp_path: Path) -> None:
    """50 cột: cả 19 trường khớp nhãn, 16 trường lệch `_COL` — không rơi về vị trí."""
    res = _parsed(tmp_path, LAYOUT_50)
    col = _column_map(res)
    assert col == _expected(LAYOUT_50)
    assert res.provenance.evidence == {f: HEADER_MATCHED for f in _FIELDS}
    assert res.provenance.layout == "labeled"
    differ = sorted(f for f in _FIELDS if col[f] != _COL[f])
    assert len(differ) == 16
    # Ba trường trùng vị trí là lý do bố cục này đọc "trôi" bằng `_COL` mà không lỗi.
    assert [f for f in _FIELDS if col[f] == _COL[f]] == [
        "declaration_no", "declaration_date", "customs_code",
    ]
    _assert_values(res)


def test_layout_55_resolves_every_field_by_label(tmp_path: Path) -> None:
    """55 cột: chèn 1 cột giữa → 11 trường lệch `_COL` đúng 1 cột."""
    res = _parsed(tmp_path, LAYOUT_55)
    col = _column_map(res)
    assert col == _expected(LAYOUT_55)
    assert res.provenance.evidence == {f: HEADER_MATCHED for f in _FIELDS}
    assert res.provenance.layout == "labeled"
    differ = sorted(f for f in _FIELDS if col[f] != _COL[f])
    assert len(differ) == 11
    assert all(col[f] == _COL[f] + 1 for f in differ)
    _assert_values(res)


def test_missing_required_label_on_shifted_layout_refuses(tmp_path: Path) -> None:
    """Thiếu nhãn bắt buộc mà vị trí cũng không xác nhận được → ném lỗi, không trả dữ liệu."""
    header = list(LAYOUT_50)
    header[header.index("Mã NPL/SP")] = "Mã hàng hóa"   # không phải alias của item_code
    p = tmp_path / "bcct.xlsx"
    _write(p, header, _rows(LAYOUT_50))
    with pytest.raises(BcctColumnError) as e:
        parse_bcct(p)
    assert "item_code" in str(e.value)


def test_standard_layout_confirms_position_for_unlabelled_field(tmp_path: Path) -> None:
    """Bố cục chuẩn thiếu MỘT nhãn: các nhãn còn lại xác nhận `_COL` → đọc tiếp,
    trường đó mang nguồn `position-only` để cán bộ thấy, không im lặng."""
    header = list(STANDARD_54)
    header[header.index("Tổng số lượng")] = "Lượng"     # không phải alias
    p = tmp_path / "bcct.xlsx"
    _write(p, header, _rows(STANDARD_54))
    res = parse_bcct(p)
    assert _column_map(res) == _COL
    assert res.provenance.evidence["quantity"] == POSITION_ONLY
    assert res.provenance.evidence["item_code"] == HEADER_MATCHED
    assert res.rows[0].quantity == 104000.0


def test_header_with_line_break_and_double_space_still_matches(tmp_path: Path) -> None:
    """`norm` gộp whitespace: ô tiêu đề xuống dòng / hai dấu cách vẫn khớp nhãn.

    Với `strip().lower()` các ô này trượt khớp rồi rơi im lặng về `_COL` — bố cục 50
    cột sẽ đọc `quantity` ra trị giá NT mà không lỗi nào phát ra.
    """
    header = list(LAYOUT_50)
    header[header.index("Tổng số lượng")] = "Tổng\nsố lượng"
    header[header.index("Mã NPL/SP")] = "Mã  NPL/SP"
    p = tmp_path / "bcct.xlsx"
    _write(p, header, _rows(LAYOUT_50))
    res = parse_bcct(p)
    assert _column_map(res) == _expected(LAYOUT_50)
    assert res.provenance.evidence["quantity"] == HEADER_MATCHED
    assert res.provenance.evidence["item_code"] == HEADER_MATCHED
    assert res.rows[0].quantity == 104000.0


def test_two_fields_on_one_column_refuses(tmp_path: Path) -> None:
    """Hai trường về cùng một cột → từ chối, không nhân đôi một cột thành hai trường.

    Dựng bằng tiêu đề hai tầng: cột 26 mang "Tổng số lượng" ở dòng cha và "Đơn vị tính"
    ở dòng con, còn cột ĐVT thật đổi nhãn — `unit` và `quantity` cùng trỏ cột 26.
    """
    header = list(STANDARD_54)
    header[header.index("Đơn vị tính")] = "ĐVT"     # không phải alias
    sub: list = [None] * len(header)
    sub[STANDARD_54.index("Tổng số lượng")] = "Đơn vị tính"
    p = tmp_path / "bcct.xlsx"
    _write(p, header, [sub, *_rows(STANDARD_54)])
    with pytest.raises(BcctColumnError) as e:
        parse_bcct(p)
    assert "đơn ánh" in str(e.value)
