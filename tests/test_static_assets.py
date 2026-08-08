"""Bất biến của tài sản tĩnh: đọc thẳng `app/static/style.css`, không dựng app, không thư viện ngoài.

Ba trạng thái ở đây (`:disabled`, `.empty-state`, `.badge.danger`) có markup dùng tới mà không có
khai báo nào, nên trên màn hình chúng hiện y như ô thường. Trước bài này không test nào đọc
stylesheet, nên rule mất đi thì không có gì đỏ.

**Phép đo tương phản dưới đây so MỘT CẶP GIÁ TRỊ MÀU đã ghim trong stylesheet.** Nó KHÔNG khẳng
định trang đạt WCAG: `opacity`, thứ tự xếp lớp, nền thừa hưởng và màu nửa trong suốt không nằm
trong phép tính. Ngưỡng 4,5 và 3,0 lấy từ vé #118; ngưỡng 1,2 giữa ô khoá và ô sửa được là mức
chốt ở chính bài này, không có trong vé.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import pytest

STYLESHEET = Path(__file__).resolve().parents[1] / "app" / "static" / "style.css"

_HEX = re.compile(r"#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})")
_VAR = re.compile(r"var\(\s*(--[a-z0-9-]+)")
_TOKEN = re.compile(rf"(--[a-z0-9-]+)\s*:\s*({_HEX.pattern})")

# Cặp màu ghim theo TÊN. Danh sách viết tay chứ không quét `:root`: quét thì mỗi token thêm vào
# sau này tự động bị chặn, kể cả cặp không bao giờ chồng lên nhau trên màn hình.
PINNED_TEXT_PAIRS = [
    ("--c-text-subtle", "--c-bg"),
    ("--c-text-subtle", "--c-surface"),
    ("--c-text-muted", "--c-bg"),
    # Dòng cán bộ đã khai vắng ở màn gán cột (#121): nền `--c-surface-alt`, chữ căn cứ
    # `--c-text-muted`. Đây là chỗ thay `opacity: .55` (đo được 2,55), nên cặp phải ghim.
    ("--c-text-muted", "--c-surface-alt"),
    ("--c-critical-fg", "--c-critical-bg"),
    ("--c-warning-fg", "--c-warning-bg"),
    ("--c-info-fg", "--c-info-bg"),
    ("--c-success-fg", "--c-success-bg"),
    ("--c-status-new-fg", "--c-status-new-bg"),
    ("--c-status-confirmed-fg", "--c-status-confirmed-bg"),
    ("--c-status-rejected-fg", "--c-status-rejected-bg"),
    ("--c-status-noted-fg", "--c-status-noted-bg"),
]


@lru_cache(maxsize=1)
def _stylesheet() -> str:
    """Nội dung style.css đã bỏ chú thích, GIỮ số dòng để thông báo lỗi trỏ đúng dòng gốc."""
    raw = STYLESHEET.read_text(encoding="utf-8")
    return re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), raw, flags=re.S)


@lru_cache(maxsize=1)
def _rules() -> tuple[tuple[str, str], ...]:
    """(bộ chọn, thân) cho mọi rule trong cùng, kể cả rule nằm trong at-rule."""
    rules: list[tuple[str, str]] = []
    stack: list[str] = []
    buf = ""
    for ch in _stylesheet():
        if ch == "{":
            stack.append(buf.strip())
            buf = ""
        elif ch == "}":
            if stack:
                rules.append((stack.pop(), buf))
            buf = ""
        else:
            buf += ch
    return tuple(rules)


def _rule_body(selector_part: str) -> str:
    """Thân của rule ĐẦU TIÊN có bộ chọn chứa `selector_part`."""
    for sel, body in _rules():
        if selector_part in sel:
            return body
    raise AssertionError(f"không có rule nào mang bộ chọn chứa {selector_part!r}")


def _declaration(body: str, prop: str) -> str | None:
    for decl in body.split(";"):
        name, sep, value = decl.partition(":")
        if sep and name.strip() == prop:
            return value.strip()
    return None


@lru_cache(maxsize=1)
def _tokens() -> dict[str, str]:
    return dict(_TOKEN.findall(_rule_body(":root")))


def _color(value: str) -> str:
    """Giá trị màu → mã hex. `var(--x, #fallback)` lấy theo TOKEN, không lấy fallback."""
    m = _VAR.search(value)
    if m:
        assert m.group(1) in _tokens(), f"token {m.group(1)} không khai ở :root"
        return _tokens()[m.group(1)]
    m = _HEX.search(value)
    assert m, f"không đọc được màu từ {value!r}"
    return m.group(0)


def _relative_luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    channels = []
    for i in (0, 2, 4):
        c = int(h[i : i + 2], 16) / 255
        channels.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(fg: str, bg: str) -> float:
    a, b = _relative_luminance(fg), _relative_luminance(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


@pytest.mark.parametrize("selector_part", [":disabled", ".empty-state", ".badge.danger"])
def test_state_has_a_rule(selector_part: str) -> None:
    """Ba trạng thái có markup dùng tới; thiếu rule là ô khoá / vùng rỗng / nhãn khoá dòng vô hình."""
    assert any(selector_part in sel for sel, _ in _rules()), (
        f"{selector_part} không có rule nào trong style.css"
    )


def test_disabled_field_looks_different_from_an_editable_one() -> None:
    """Có rule là chưa đủ: nền `--c-surface-alt` chỉ chênh 1,03 với ô trắng, tức là nhìn như nhau."""
    enabled = _rule_body(".form-input,")
    disabled = _rule_body(".form-input:disabled")
    enabled_bg = _color(_declaration(enabled, "background") or "")
    disabled_bg = _color(_declaration(disabled, "background") or "")
    ratio = _contrast(disabled_bg, enabled_bg)
    assert ratio >= 1.2, f"nền ô khoá {disabled_bg} so ô sửa được {enabled_bg}: {ratio:.2f}"

    enabled_border = _color(_declaration(enabled, "border") or "")
    disabled_border = _color(_declaration(disabled, "border-color") or "")
    assert _relative_luminance(disabled_border) <= _relative_luminance(enabled_border), (
        f"viền ô khoá {disabled_border} NHẠT hơn viền ô thường {enabled_border}"
    )


def test_brace_depth_never_negative_and_ends_at_zero() -> None:
    """Quét theo ĐỘ SÂU: một `}` thừa cộng một block chưa đóng thì đếm trần vẫn ra số cân bằng."""
    depth, line = 0, 1
    negatives: list[int] = []
    for ch in _stylesheet():
        if ch == "\n":
            line += 1
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                negatives.append(line)
                depth = 0
    assert not negatives, f"dấu `}}` thừa ở dòng {negatives}"
    assert depth == 0, f"còn {depth} block chưa đóng ở cuối file"


@pytest.mark.parametrize(
    "selector_part, background_token",
    [
        (".form-input:focus", "--c-surface"),
        (".toolbar-search:focus", "--c-surface"),
    ],
)
def test_focus_ring_contrast_against_the_field_it_rings(
    selector_part: str, background_token: str
) -> None:
    """Vòng focus phải thấy được trên nền ô nhập. `outline: none` + box-shadow nhạt thì không."""
    outline = _declaration(_rule_body(selector_part), "outline")
    assert outline is not None, f"{selector_part} không khai `outline`"
    assert outline.strip() != "none", f"{selector_part} tắt outline, cán bộ mất dấu bàn phím"
    ratio = _contrast(_color(outline), _tokens()[background_token])
    assert ratio >= 3.0, f"{selector_part}: vòng focus tương phản {ratio:.2f}, ngưỡng 3,0"


@pytest.mark.parametrize("foreground_token, background_token", PINNED_TEXT_PAIRS)
def test_pinned_text_token_contrast(foreground_token: str, background_token: str) -> None:
    ratio = _contrast(_tokens()[foreground_token], _tokens()[background_token])
    assert ratio >= 4.5, f"{foreground_token} trên {background_token}: {ratio:.2f}, ngưỡng 4,5"


def test_unknown_operation_badge_contrast() -> None:
    """Cặp màu khai TẠI CHỖ trong rule, không qua token — đọc từ chính rule đó."""
    body = _rule_body(".badge-op-unknown")
    fg, bg = _declaration(body, "color"), _declaration(body, "background")
    assert fg and bg, ".badge-op-unknown thiếu `color` hoặc `background`"
    ratio = _contrast(_color(fg), _color(bg))
    assert ratio >= 4.5, f".badge-op-unknown: {ratio:.2f}, ngưỡng 4,5"
