"""Bất biến của tài sản tĩnh: đọc thẳng `app/static/style.css`, không dựng app, không thư viện ngoài.

Ba rule ở đây (`:disabled`, `.empty-state`, `.badge.danger`) đã có markup dùng tới mà không có
khai báo nào, nên trên màn hình chúng vô hình. Không test nào từng đọc stylesheet, nên mất lại là
mất im lặng.

**Phép đo tương phản dưới đây so MỘT CẶP GIÁ TRỊ MÀU đã ghim trong stylesheet.** Nó KHÔNG khẳng
định trang đạt WCAG: `opacity`, thứ tự xếp lớp, nền thừa hưởng và màu nửa trong suốt không nằm
trong phép tính. Ngưỡng 4,5 và 3,0 lấy từ vé #118, không suy ra từ chính giá trị đang đo.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

STYLESHEET = Path(__file__).resolve().parents[1] / "app" / "static" / "style.css"

_HEX = re.compile(r"#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})")
_VAR = re.compile(r"var\(\s*(--[a-z0-9-]+)")
_TOKEN = re.compile(r"(--[a-z0-9-]+)\s*:\s*(#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3}))")


def _source() -> str:
    return STYLESHEET.read_text(encoding="utf-8")


def _strip_comments(css: str) -> str:
    """Bỏ chú thích mà GIỮ số dòng, để thông báo lỗi trỏ đúng dòng trong file gốc."""
    return re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), css, flags=re.S)


def _rules(css: str) -> list[tuple[str, str]]:
    """(bộ chọn, thân) cho mọi rule trong cùng, kể cả rule nằm trong at-rule."""
    rules: list[tuple[str, str]] = []
    stack: list[str] = []
    buf = ""
    for ch in css:
        if ch == "{":
            stack.append(buf.strip())
            buf = ""
        elif ch == "}":
            if stack:
                rules.append((stack.pop(), buf))
            buf = ""
        else:
            buf += ch
    return rules


def _selectors(css: str) -> list[str]:
    return [sel for sel, _ in _rules(css)]


def _block(css: str, selector_part: str) -> str:
    """Thân của rule ĐẦU TIÊN có bộ chọn chứa `selector_part`."""
    for sel, body in _rules(css):
        if selector_part in sel:
            return body
    raise AssertionError(f"không có rule nào mang bộ chọn chứa {selector_part!r}")


def _declaration(body: str, prop: str) -> str | None:
    for decl in body.split(";"):
        name, sep, value = decl.partition(":")
        if sep and name.strip() == prop:
            return value.strip()
    return None


def _tokens(css: str) -> dict[str, str]:
    root = _block(css, ":root")
    return dict(_TOKEN.findall(root))


def _color(value: str, tokens: dict[str, str]) -> str:
    """Giá trị màu → mã hex. `var(--x, #fallback)` lấy theo TOKEN, không lấy fallback."""
    m = _VAR.search(value)
    if m:
        assert m.group(1) in tokens, f"token {m.group(1)} không khai ở :root"
        return tokens[m.group(1)]
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


@pytest.mark.parametrize(
    "selector_part",
    [
        ":disabled",
        ".empty-state",
        ".badge.danger",
    ],
)
def test_state_has_a_rule(selector_part: str) -> None:
    """Ba trạng thái có markup dùng tới; thiếu rule là ô khoá / vùng rỗng / nhãn khoá dòng vô hình."""
    css = _strip_comments(_source())
    assert any(selector_part in sel for sel in _selectors(css)), (
        f"{selector_part} không có rule nào trong style.css"
    )


def test_brace_depth_never_negative_and_ends_at_zero() -> None:
    """Quét theo ĐỘ SÂU, không đếm trần: một `}` thừa cộng một block chưa đóng thì số đếm cân bằng."""
    css = _strip_comments(_source())
    depth, line = 0, 1
    negatives: list[int] = []
    for ch in css:
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
    css = _strip_comments(_source())
    tokens = _tokens(css)
    body = _block(css, selector_part)
    outline = _declaration(body, "outline")
    assert outline is not None, f"{selector_part} không khai `outline`"
    assert outline.strip() != "none", f"{selector_part} tắt outline, cán bộ mất dấu bàn phím"
    ratio = _contrast(_color(outline, tokens), tokens[background_token])
    assert ratio >= 3.0, f"{selector_part}: vòng focus tương phản {ratio:.2f}, ngưỡng 3,0"


@pytest.mark.parametrize(
    "foreground_token, background_token",
    [
        ("--c-text-subtle", "--c-bg"),
        ("--c-text-subtle", "--c-surface"),
        ("--c-text-muted", "--c-bg"),
    ],
)
def test_pinned_text_token_contrast(foreground_token: str, background_token: str) -> None:
    css = _strip_comments(_source())
    tokens = _tokens(css)
    ratio = _contrast(tokens[foreground_token], tokens[background_token])
    assert ratio >= 4.5, (
        f"{foreground_token} trên {background_token}: {ratio:.2f}, ngưỡng 4,5"
    )


def test_severity_and_status_token_pairs_stay_readable() -> None:
    """Mọi cặp `*-fg` / `*-bg` khai ở :root — sàn hồi quy cho nhãn mức và nhãn trạng thái."""
    css = _strip_comments(_source())
    tokens = _tokens(css)
    pairs = [(fg, fg[: -len("-fg")] + "-bg") for fg in tokens if fg.endswith("-fg")]
    checked = [(fg, bg) for fg, bg in pairs if bg in tokens]
    assert checked, "không tìm được cặp fg/bg nào ở :root"
    for fg, bg in checked:
        ratio = _contrast(tokens[fg], tokens[bg])
        assert ratio >= 4.5, f"{fg} trên {bg}: {ratio:.2f}, ngưỡng 4,5"


@pytest.mark.parametrize(
    "selector_part",
    [
        ".badge-op-unknown",
        ".badge-op-other",
        ".badge-op-import",
        ".badge-op-export",
    ],
)
def test_operation_badge_contrast(selector_part: str) -> None:
    """Cặp màu khai TẠI CHỖ trong rule, không qua token — đọc từ chính rule đó."""
    css = _strip_comments(_source())
    tokens = _tokens(css)
    body = _block(css, selector_part)
    fg = _declaration(body, "color")
    bg = _declaration(body, "background")
    assert fg and bg, f"{selector_part} thiếu `color` hoặc `background`"
    ratio = _contrast(_color(fg, tokens), _color(bg, tokens))
    assert ratio >= 4.5, f"{selector_part}: {ratio:.2f}, ngưỡng 4,5"
