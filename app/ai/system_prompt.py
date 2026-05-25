"""Build system prompt cho AI assistant.

3 segment:
1. Head — instructions/boundary/citation rule (~500 token, không cache).
2. Catalog — 16 MVP check + 4 combo signature từ registry (~3-5k token, CACHE).
3. Page context — URL/DN/year/finding hiện tại (~100 token, không cache).
"""

from __future__ import annotations

from functools import lru_cache

from app.checks.combos import COMBO_SPECS
from app.checks.registry import SEVERITY_BADGE, SPECS

HEAD = """Bạn là trợ lý AI cho cán bộ Hải quan Việt Nam dùng hệ thống Audit-HQ (quản lý rủi ro BCQT — Báo cáo Quyết toán).

## Vai trò
Tra cứu dữ liệu, giải thích phát hiện (finding), summarise tình hình doanh nghiệp. KHÔNG thay người dùng quyết định confirm/reject phát hiện — đó là thẩm quyền của cán bộ Hải quan.

## Cách trả lời
- **Tiếng Việt full accents, tone formal** (vd: "cán bộ", "phía Hải quan", "doanh nghiệp"). Nếu user hỏi bằng tiếng Anh thì trả lời tiếng Anh.
- **Cite nguồn cụ thể** cho mọi claim concrete: `[finding:123]`, `[nvl_balances:row_id=45]`, `[check:C2.3]`, `[item:NPL-X]` (trang chi tiết mã NVL/TP). KHÔNG bịa số liệu — nếu không có data, gọi tool để lấy, hoặc nói "tôi chưa có thông tin này".
- **Ngắn gọn**. Trả lời 2-5 câu cho câu hỏi đơn giản. Bullet/table khi liệt kê.
- **Boundary**: nếu user yêu cầu hành động (xoá, confirm, reject finding), giải thích rằng tôi chỉ tra cứu — họ phải tự bấm nút trên UI để thực hiện.

## Khi nào gọi tool
- User hỏi "DN X có findings gì" → gọi `search_findings`.
- User hỏi chi tiết 1 finding cụ thể → gọi `get_finding`.
- Không gọi tool cho câu hỏi general ("tại sao C2.3 quan trọng?") — dùng catalog dưới đây.

## PII & demo data
Dữ liệu trong hệ thống đã anonymize (DN_001..DN_006 thay tên thật, MST giả lập). KHÔNG suy đoán DN thật từ mã code."""


def _catalog_block() -> str:
    """Render catalog dưới dạng compact text — tốn ít token + cache được."""
    lines = ["## Catalog 16 kiểm tra MVP\n"]
    by_group: dict[int, list] = {}
    for code, spec in sorted(SPECS.items()):
        by_group.setdefault(spec.group, []).append((code, spec))
    for group_num in sorted(by_group):
        lines.append(f"### Nhóm {group_num}")
        for code, spec in by_group[group_num]:
            badge = SEVERITY_BADGE.get(spec.default_severity, "")
            lines.append(f"- **{code}** {badge} _{spec.title}_ — {spec.description}")
        lines.append("")

    lines.append("## 4 combo signature (meta-finding)\n")
    for code, spec in COMBO_SPECS.items():
        triggers = "+".join(spec.triggers)
        lines.append(f"- **{code}** — {spec.title} (triggers: {triggers}). {spec.description}")
    lines.append("")

    lines.append("""## Chấm điểm rủi ro (§2.6 đề án)
- 🔴 Nghiêm trọng = 10 đ · 🟡 Cảnh báo = 3 đ · 🔵 Thông tin = 1 đ · Combo fire = +20 đ
- DN_005 = sạch (score ~3) → minh chứng "không phát hiện bừa".
- HONG_AN/DN_003 năm 2024 đã inject 12 finding + combo ACCOUNTING_INCONSISTENT (score 7896) → kịch bản demo gian lận tiêu hao.""")
    return "\n".join(lines)


@lru_cache(maxsize=1)
def cached_catalog() -> str:
    """Catalog cố định từ Python registry → cache forever trong process."""
    return _catalog_block()


def build_page_context(
    page_url: str | None,
    dn_code: str | None,
    year: int | None,
    finding_id: int | None,
) -> str:
    parts = []
    if page_url:
        parts.append(f"URL: `{page_url}`")
    if dn_code:
        parts.append(f"Đang xem DN `{dn_code}`")
    if year:
        parts.append(f"Năm `{year}`")
    if finding_id:
        parts.append(f"Đang xem finding `#{finding_id}`")
    if not parts:
        return ""
    return "## Ngữ cảnh user đang xem\n" + "\n".join(f"- {p}" for p in parts)


def build_messages_system(
    page_context: dict | None = None,
    enable_cache: bool = False,
) -> list[dict]:
    """Trả list system messages cho OpenAI API.

    Nếu enable_cache=True → segment catalog có cache_control (Anthropic-style),
    provider không hỗ trợ sẽ silent skip.
    """
    page_block = ""
    if page_context:
        page_block = build_page_context(
            page_url=page_context.get("url"),
            dn_code=page_context.get("dn_code"),
            year=page_context.get("year"),
            finding_id=page_context.get("finding_id"),
        )

    catalog = cached_catalog()
    if enable_cache:
        # Anthropic-style: content là list of blocks, segment cache đánh dấu ephemeral.
        return [{
            "role": "system",
            "content": [
                {"type": "text", "text": HEAD},
                {"type": "text", "text": catalog, "cache_control": {"type": "ephemeral"}},
                *([{"type": "text", "text": page_block}] if page_block else []),
            ],
        }]
    # Provider không cache → gộp string đơn giản.
    text = HEAD + "\n\n" + catalog + ("\n\n" + page_block if page_block else "")
    return [{"role": "system", "content": text}]
