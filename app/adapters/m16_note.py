"""Bộ mã cột (9) Mẫu 16 — PHỤ THUỘC KỲ (#114).

Nguyên văn hai bản văn bản ở `.ai/notes/2026-08-08-huong-dan-lap-mau-16-tt39.md`
(bản Công báo, đều là bản QUÉT, trích bằng `pdftoppm` + `tesseract -l vie`):

- **TT 39/2018** Phụ lục II tr. 8 — cột (9) có BA trạng thái: `X` mua trong nước ·
  để trống = nhập khẩu · `KXDĐM` không xây dựng được định mức.
- **TT 121/2025** tr. 238, hiệu lực **01/02/2026** — giữ nguyên ba trạng thái trên và
  thêm `TH` (nguyên liệu thu hồi từ sản phẩm tái nhập) và `SPTN` (sửa chữa, tái chế từ
  sản phẩm tái nhập).

Kho dữ liệu bắc qua CẢ HAI thế hệ (ZONSEN 2026 thuộc TT 121, mọi kỳ còn lại thuộc
TT 39), nên bộ mã hợp lệ **không được hằng số hoá**.

Vé này chỉ làm hệ thống ĐỌC ĐƯỢC các mã đó và không nhầm chúng với ô để trống.
`KXDĐM` nên tác động thế nào tới cổng độ phủ định mức (C4.9 / `norm_gate`) là câu hỏi
NGHIỆP VỤ, phải sửa catalog ở repo đề án trước — NGOÀI phạm vi #114.
"""

from __future__ import annotations

from datetime import date

__all__ = [
    "DOMESTIC",
    "NO_NORM",
    "NOTE_LABEL_VI",
    "RECOVERED_REIMPORT",
    "REWORK_REIMPORT",
    "TT121_EFFECTIVE",
    "is_domestic_origin",
    "is_unknown_note",
    "normalize_note",
    "note_codes_for",
]

# Ngày hiệu lực TT 121/2025/TT-BTC.
TT121_EFFECTIVE = date(2026, 2, 1)

DOMESTIC = "X"                 # nguyên liệu mua trong nước
NO_NORM = "KXDĐM"              # vật tư không xây dựng được định mức
RECOVERED_REIMPORT = "TH"      # thu hồi từ sản phẩm tái nhập (từ TT 121)
REWORK_REIMPORT = "SPTN"       # sửa chữa, tái chế từ sản phẩm tái nhập (từ TT 121)

# Ô để TRỐNG = nhập khẩu. Là một trạng thái hợp lệ của biểu chứ không phải mã, nên nó
# không nằm trong tập mã — chỗ nào cũng phải xử lý "rỗng" trước khi tra mã.
_TT39_CODES = frozenset({DOMESTIC, NO_NORM})
_TT121_CODES = _TT39_CODES | {RECOVERED_REIMPORT, REWORK_REIMPORT}

NOTE_LABEL_VI = {
    DOMESTIC: "Mua trong nước",
    NO_NORM: "Không xây dựng được định mức",
    RECOVERED_REIMPORT: "Thu hồi từ SP tái nhập",
    REWORK_REIMPORT: "Sửa chữa, tái chế từ SP tái nhập",
}


def note_codes_for(period_to: date) -> frozenset[str]:
    """Bộ mã cột (9) hợp lệ cho kỳ KẾT THÚC vào `period_to`.

    Neo vào ngày KẾT THÚC kỳ chứ không phải ngày bắt đầu: báo cáo quyết toán nộp sau
    khi kỳ đóng, nên văn bản áp dụng là văn bản đang có hiệu lực lúc đó. Đây cũng là
    cách duy nhất khớp cả hai dữ kiện đã biết — kỳ dương lịch 2026 (01/01–31/12/2026,
    BẮT ĐẦU trước mốc) thuộc TT 121, còn mọi kỳ 2025 thuộc TT 39.
    """
    return _TT121_CODES if period_to >= TT121_EFFECTIVE else _TT39_CODES


def normalize_note(note: str | None) -> str | None:
    """Chuẩn hoá ô cột (9) để tra mã: bỏ khoảng trắng, hoa hoá. Rỗng → None.

    `str.upper()` của Python xử lý đúng `đ` → `Đ`, nên `kxdđm` khớp `KXDĐM`.
    """
    if note is None:
        return None
    text = str(note).strip()
    return text.upper() if text else None


def is_domestic_origin(note: str | None) -> bool:
    """Cột (9) = "X" ⇒ NVL xuất xứ trong nước (không nhập khẩu).

    Hàng xuất xứ VN không có tờ khai nhập nên không đối chiếu lệch nhập khẩu. C4.1
    dùng hàm này để TRỪ nguyên liệu trong nước khỏi phạm vi (`c4_norm.py`).

    Hành vi giữ NGUYÊN qua #114: chỉ `X` là trong nước. `KXDĐM`, `TH`, `SPTN` đều
    KHÔNG phải trong nước — chúng nói về lý do khác, không nói về xuất xứ.
    """
    return normalize_note(note) == DOMESTIC


def is_unknown_note(note: str | None, period_to: date) -> bool:
    """Ô cột (9) có giá trị nhưng KHÔNG thuộc bộ mã của kỳ đó.

    Ô để trống không phải giá trị lạ — nó là trạng thái "nhập khẩu".
    """
    code = normalize_note(note)
    return code is not None and code not in note_codes_for(period_to)
