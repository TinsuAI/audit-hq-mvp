"""Post-process guardrails cho AI assistant response.

Chạy sau khi nhận response từ LLM, trước khi lưu audit log + trả về FE.
Không block response — chỉ log warning và/hoặc thay thế phrase vi phạm.
"""

from __future__ import annotations

import logging
import re

log = logging.getLogger(__name__)

# Phrases AI không được dùng — ngụ ý AI đang thực hiện quyết định thay cán bộ.
_FORBIDDEN_PATTERNS: list[re.Pattern] = [
    re.compile(r"tôi\s+(?:sẽ|đã)\s+(?:confirm|xác nhận)", re.IGNORECASE),
    re.compile(r"tôi\s+(?:sẽ|đã)\s+(?:reject|loại trừ|từ chối)", re.IGNORECASE),
    re.compile(r"tôi\s+(?:sẽ|đã)\s+duyệt", re.IGNORECASE),
    re.compile(r"tôi\s+(?:sẽ|đã)\s+phê duyệt", re.IGNORECASE),
    re.compile(
        r"tôi\s+(?:đã\s+)?(?:xác\s+nhận|kết luận)\s+(?:rằng|là)\s+(?:có|không)\s+vi phạm",
        re.IGNORECASE,
    ),
    re.compile(r"I\s+(?:will|have)\s+(?:confirm|reject|approve)", re.IGNORECASE),
]

# Patterns gợi ý response tham chiếu data cụ thể nhưng không có citation tag.
_CITATION_HINT_RE = re.compile(
    r"(?:theo\s+(?:bảng|M15|M16|BCCT|tờ khai|dữ liệu)|"
    r"số liệu\s+(?:cho thấy|từ)|"
    r"trong\s+(?:hồ sơ|tờ khai|báo cáo))",
    re.IGNORECASE,
)
_CITATION_TAG_RE = re.compile(
    r"\[(?:finding|nvl_balances|m15|m15a|m16|bcct|declaration_lines):", re.IGNORECASE
)


def check_forbidden_phrases(text: str) -> list[str]:
    """Trả về list các phrase vi phạm tìm thấy trong text. Rỗng = OK."""
    violations = []
    for pat in _FORBIDDEN_PATTERNS:
        m = pat.search(text)
        if m:
            violations.append(m.group(0))
    return violations


def redact_forbidden_phrases(text: str) -> tuple[str, list[str]]:
    """Thay thế forbidden phrase bằng [redacted]. Trả về (text đã clean, list violations)."""
    violations = check_forbidden_phrases(text)
    clean = text
    for pat in _FORBIDDEN_PATTERNS:
        clean = pat.sub("[redacted — AI không có thẩm quyền quyết định]", clean)
    return clean, violations


def check_missing_citations(text: str) -> bool:
    """True nếu text nhắc đến data cụ thể nhưng thiếu citation tag."""
    has_hint = bool(_CITATION_HINT_RE.search(text))
    has_citation = bool(_CITATION_TAG_RE.search(text))
    return has_hint and not has_citation


def apply_guardrails(text: str, conv_id: int | None = None) -> str:
    """Apply tất cả guardrails. Log warning nếu vi phạm. Trả về text đã clean."""
    clean, violations = redact_forbidden_phrases(text)

    if violations:
        log.warning(
            "Guardrail: forbidden phrase trong conv=%s: %s",
            conv_id,
            violations,
        )

    if check_missing_citations(clean):
        log.warning(
            "Guardrail: response conv=%s tham chiếu data nhưng thiếu citation tag",
            conv_id,
        )

    return clean
