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


@lru_cache(maxsize=2)
def _rules(top_level_only: bool = False) -> tuple[tuple[str, str], ...]:
    """(bộ chọn, thân) cho mọi rule trong cùng, kể cả rule nằm trong at-rule.

    `top_level_only` bỏ rule nằm trong at-rule. Phép so "một bộ chọn khai một giá trị"
    cần nó: rule trong `@media` / `@supports` ĐƯỢC PHÉP đặt lại giá trị của rule nền —
    đó là cách khai một breakpoint. Trộn hai tầng thì mọi breakpoint hoá thành xung khắc.
    """
    rules: list[tuple[str, str]] = []
    stack: list[str] = []
    buf = ""
    for ch in _stylesheet():
        if ch == "{":
            stack.append(buf.strip())
            buf = ""
        elif ch == "}":
            if stack:
                sel = stack.pop()
                if not (top_level_only and stack):
                    rules.append((sel, buf))
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


# Class đã xoá ở #127. Mỗi tên ở đây từng có rule trong `style.css` mà không chỗ nào
# phát ra: không `class=`, không `classList`, không tên ghép lúc chạy, không tham số
# class truyền vào hàm dựng DOM, không giá trị `cls` trong dữ liệu Python. Giữ danh
# sách để chúng không quay lại: một rule không ai gọi tới thì không có phép thử nào đỏ,
# nên nó chỉ lộ ra ở một lượt quét viết tay.
#
# Bốn cụm, bốn lý do khác nhau:
# - `.upload-slot*` (12 tên): ô tải lên theo từng loại biểu, thay bằng ô thả cả bộ (#88).
# - lớp tiện ích (`.flex*`, `.items-*`, `.mt-0`, `.text-center`…): dựng theo lối
#   utility-first rồi không màn nào dùng — repo này viết CSS theo khối, không theo tiện ích.
# - `.fm-*` của BẢNG CHUYỂN VỊ: #121 bỏ bảng đó và xoá rule ngay trong cùng commit, nên
#   #127 không còn gì để xoá ở đây. Ghim vẫn cần: đó là cụm mà vé này được xếp SAU #121
#   để dọn, và không ghim thì không gì chặn nó quay lại cùng một bố cục cũ.
# - còn lại: tàn dư của những màn đã viết lại (`.card-section`, `.dn-code`, `.badge-dot`,
#   `.score-pill.low/.mid/.high` — hạng rủi ro dùng `tier-*`, không dùng ba tên này).
DELETED_CLASSES = (
    "badge-dot",
    "card-section",
    "card-table-wrapper",
    "dim",
    "dn-code",
    "dn-name",
    "ds-upload-slot",
    "flex",
    "flex-col",
    "flex-gap-2",
    "flex-gap-3",
    "flex-gap-4",
    "flex-wrap",
    "flush",
    "fm-absentrow",
    "fm-blank",
    "fm-col-absent",
    "fm-corner",
    "fm-datarow",
    "fm-foot",
    "fm-metarow",
    "fm-pickrow",
    "form-help",
    "hide",
    "items-center",
    "items-end",
    "justify-between",
    "logout-btn",
    "mb-0",
    "mb-5",
    "mt-0",
    "text-center",
    "text-num",
    "text-right",
    "upload-section-hint",
    "upload-section-title",
    "upload-slot",
    "upload-slot-code",
    "upload-slot-drop",
    "upload-slot-filename",
    "upload-slot-info",
    "upload-slot-input",
    "upload-slot-label",
    "upload-slot-placeholder",
    "upload-slot-sample",
    "upload-slots",
)

# `.score-pill.low/.mid/.high` và `.stat.success` không còn ai phát ra ở phần TU CHỈNH,
# còn tên cơ sở (`.score-pill`, `.stat`) vẫn sống. Ghim riêng để lượt kiểm không đòi
# xoá cả hai.
#
# `.data-table .date` TỪNG nằm trong danh sách này và đó là một lỗi: tên `date` không
# xuất hiện trong template nào vì nó là phần tử thứ ba của `view_cols` ở
# `app/routes/companies.py`, đi ra qua `<td class="{{ cls }}">`. Lượt quét chỗ gán class
# không nhìn thấy đường đó. `test_table_cell_classes_from_python_data_have_a_rule` bên
# dưới đóng lỗ hổng ấy — nó hỏi thẳng cấu hình bảng, không quét chuỗi.
DELETED_MODIFIERS = (
    ".score-pill.low",
    ".score-pill.mid",
    ".score-pill.high",
    ".stat.success",
)

# Bộ chọn khai hai lần với giá trị khác nhau là hai chỗ phải sửa cho một quyết định, và
# chỗ đứng sau thắng lặng lẽ. Hai cặp dưới đây KHÔNG phải lỗi đó: chúng là lối "nhóm đặt
# mặc định, rồi một bộ chọn trong nhóm đặt lại" — cùng một khai, cố ý ghi đè chính nó.
CASCADE_OVERRIDES = {
    ".catalog-table th": {"border-top"},
    ".cg-col": {"height"},
}


def _class_names(selector: str) -> set[str]:
    return set(re.findall(r"\.(-?[_a-zA-Z][\w-]*)", selector))


@pytest.mark.parametrize("name", DELETED_CLASSES)
def test_a_deleted_class_stays_deleted(name: str) -> None:
    """Xoá rồi mà quay lại thì stylesheet lại nuôi một khối không màn nào gọi tới."""
    back = [sel for sel, _ in _rules() if name in _class_names(sel)]
    assert not back, f".{name} đã xoá ở #127 nhưng quay lại ở: {back}"


@pytest.mark.parametrize("selector", DELETED_MODIFIERS)
def test_a_deleted_modifier_stays_deleted(selector: str) -> None:
    assert not any(selector in sel for sel, _ in _rules()), (
        f"{selector} đã xoá ở #127 nhưng quay lại"
    )


def test_table_cell_classes_from_python_data_have_a_rule() -> None:
    """Class ô bảng khai trong DỮ LIỆU Python phải có rule.

    `view_cols` ở `app/routes/companies.py` mang phần tử thứ ba là tên class, và nó ra
    màn qua `<td class="{{ cls }}">`. Không template nào chứa những tên đó, nên mọi lượt
    quét "chỗ nào gán class" đều bỏ sót — đúng cách `.data-table .date` bị xoá nhầm ở
    lượt đầu của #127. Hỏi thẳng cấu hình bảng thì không phải quét chuỗi nữa.

    Chỉ đòi rule cho class dùng làm KIỂU Ô. `file`, `price`, `item-link` chưa bao giờ có
    rule nào và không thuộc phạm vi vé này — ghim đúng tập đang có kiểu.
    """
    from app.routes.companies import _TABLE_CONFIG

    styled = {"num", "date", "code-cell", "wrap"}
    emitted: set[str] = set()
    for config in _TABLE_CONFIG.values():
        for column in config.get("view_cols", ()):
            if len(column) >= 3 and column[2]:
                emitted.update(str(column[2]).split())
    missing = sorted(
        name for name in emitted & styled
        if not any(name in _class_names(sel) for sel, _ in _rules())
    )
    assert not missing, f"class ô bảng không còn rule nào: {missing}"


def test_no_selector_declares_the_same_property_twice_with_different_values() -> None:
    """Một bộ chọn, một khai. Hai khai lệch nhau thì chỗ sau thắng mà không ai biết."""
    seen: dict[str, dict[str, set[str]]] = {}
    for sel, body in _rules(top_level_only=True):
        if sel.startswith("@"):
            continue
        for one in (" ".join(s.split()) for s in sel.split(",")):
            if not one:
                continue
            props = seen.setdefault(one, {})
            for decl in body.split(";"):
                name, sep, value = decl.partition(":")
                if sep:
                    props.setdefault(name.strip(), set()).add(" ".join(value.split()))
    clashes = {
        one: sorted(p for p, values in props.items()
                    if len(values) > 1 and p not in CASCADE_OVERRIDES.get(one, ()))
        for one, props in seen.items()
    }
    clashes = {k: v for k, v in clashes.items() if v}
    assert not clashes, f"bộ chọn khai trùng với giá trị xung khắc: {clashes}"


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
