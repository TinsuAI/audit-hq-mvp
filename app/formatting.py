"""Định dạng số/ngày cho giao diện — một chỗ duy nhất quyết định dấu phân cách.

Quy ước phân cách đọc từ `app_settings.get_number_format()`: `vi` cho
`1.234,56` (mặc định, khớp UI tiếng Việt), `en` cho `1,234.56`. Hàm ở đây
nhận `style` tường minh để test không cần DB; template gọi qua Jinja global
(`fmt_qty`, `fmt_pct`, …) và để `style=None` — lúc đó đọc setting.

Ba loại số trên màn hình có ba luật khác nhau, đừng gộp:
- `qty`  — số lượng hàng: 2 chữ số thập phân, bỏ `,00` khi tròn; số rất nhỏ
  (định mức tiêu hao ~0,0018 kg/sp) rơi về 6 chữ số có nghĩa để không thành `0,00`.
- `pct`  — tỷ lệ: 1 chữ số thập phân, LUÔN kèm dấu và `%`.
- `money`— tiền: 0 chữ số thập phân, LUÔN kèm mã tiền tệ.
"""

from __future__ import annotations

from datetime import date, datetime

# style → (dấu phân cách nghìn, dấu thập phân)
SEPARATORS: dict[str, tuple[str, str]] = {
    "vi": (".", ","),
    "en": (",", "."),
}

EMPTY = "—"


def _resolve_style(style: str | None) -> str:
    if style in SEPARATORS:
        return style
    from app.app_settings import get_number_format

    return get_number_format()


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _apply_separators(text: str, style: str) -> str:
    """`1,234.56` (đầu ra của `format`) → quy ước đang chọn."""
    thousands, decimal = SEPARATORS[style]
    if (thousands, decimal) == (",", "."):
        return text
    return text.replace(",", "\x00").replace(".", decimal).replace("\x00", thousands)


def group_number(
    value: object,
    decimals: int = 2,
    *,
    style: str | None = None,
    signed: bool = False,
) -> str:
    """Số → chuỗi có phân cách nghìn. Không phải số → chuỗi thô, không nuốt dữ liệu."""
    if value is None or value == "":
        return EMPTY
    if not _is_number(value):
        return str(value)
    spec = f"{'+' if signed else ''},.{decimals}f"
    return _apply_separators(format(float(value), spec), _resolve_style(style))


def fmt_qty(value: object, unit: str | None = None, *, style: str | None = None) -> str:
    """Số lượng hàng. Tròn thì bỏ phần thập phân; rất nhỏ thì giữ chữ số có nghĩa."""
    if value is None or value == "":
        return EMPTY
    if not _is_number(value):
        return str(value)
    v = float(value)
    if v.is_integer():
        text = group_number(v, 0, style=style)
    elif abs(v) >= 0.01:
        text = group_number(v, 2, style=style)
    else:
        # Dưới 0,01: 2 chữ số thành `0,00` → giữ 6 chữ số CÓ NGHĨA. `%g` nhả ký hiệu
        # mũ khi số quá nhỏ (`1.234e-06`) — cán bộ không đọc được — nên ca đó rơi về
        # dấu phẩy động cố định rồi cắt số 0 thừa.
        _, decimal = SEPARATORS[_resolve_style(style)]
        text = f"{v:.6g}"
        if "e" in text or "E" in text:
            text = f"{v:.10f}".rstrip("0").rstrip(".") or "0"
        text = text.replace(".", decimal)
    return f"{text} {unit}" if unit else text


def fmt_pct(value: object, *, decimals: int = 1, style: str | None = None) -> str:
    """Tỷ lệ phần trăm, luôn có dấu và ký hiệu `%`. Giá trị vào là 12.4, không phải 0.124."""
    if value is None or value == "":
        return EMPTY
    if not _is_number(value):
        return str(value)
    return f"{group_number(value, decimals, style=style, signed=True)} %"


def fmt_money(value: object, currency: str | None = "VND", *, style: str | None = None) -> str:
    """Tiền: không phần thập phân, luôn kèm mã tiền tệ."""
    if value is None or value == "":
        return EMPTY
    if not _is_number(value):
        return str(value)
    text = group_number(value, 0, style=style)
    return f"{text} {currency}" if currency else text


def fmt_price(value: object, currency: str | None = None, *, style: str | None = None) -> str:
    """Đơn giá: 4 chữ số thập phân — đơn giá NPL hay nhỏ hơn 1."""
    if value is None or value == "":
        return EMPTY
    if not _is_number(value):
        return str(value)
    text = group_number(value, 4, style=style)
    return f"{text} {currency}" if currency else text


def fmt_int(value: object, *, style: str | None = None) -> str:
    if value is None or value == "":
        return EMPTY
    if not _is_number(value):
        return str(value)
    return group_number(value, 0, style=style)


def fmt_date(value: object) -> str:
    if isinstance(value, datetime | date):
        return value.strftime("%d/%m/%Y")
    if value is None or value == "":
        return EMPTY
    return str(value)


def fmt_bool(value: object) -> str:
    return "Có" if value else "Không"


JINJA_GLOBALS = {
    "fmt_qty": fmt_qty,
    "fmt_pct": fmt_pct,
    "fmt_money": fmt_money,
    "fmt_price": fmt_price,
    "fmt_int": fmt_int,
    "fmt_date": fmt_date,
    "fmt_num": group_number,
}
