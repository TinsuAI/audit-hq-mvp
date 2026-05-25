"""Cost estimate cho mỗi turn AI — pricing table per 1M tokens.

Số liệu pricing (USD / 1M token) cập nhật 2026-05-25 từ OpenRouter / Anthropic /
OpenAI. KHÔNG dependent — purely informational cho tracking.

Fallback DEFAULT_PRICE dùng cho model lạ (provider mới hoặc model self-host
không có pricing).
"""

from __future__ import annotations

from dataclasses import dataclass

# USD per 1M tokens — chia 1_000_000 khi tính.
PRICING: dict[str, dict[str, float]] = {
    # Anthropic via OpenRouter (alias prefix `~` cho floating "latest").
    "~anthropic/claude-sonnet-latest": {"input": 3.0, "output": 15.0, "cache_read": 0.30},
    "~anthropic/claude-haiku-latest":  {"input": 1.0, "output": 5.0,  "cache_read": 0.10},
    "~anthropic/claude-opus-latest":   {"input": 15.0, "output": 75.0, "cache_read": 1.50},
    "anthropic/claude-opus-4.7":       {"input": 15.0, "output": 75.0, "cache_read": 1.50},
    "anthropic/claude-opus-4.7-fast":  {"input": 15.0, "output": 75.0, "cache_read": 1.50},
    "anthropic/claude-opus-4.6-fast":  {"input": 15.0, "output": 75.0, "cache_read": 1.50},

    # OpenAI
    "openai/gpt-4o":      {"input": 2.5, "output": 10.0},
    "openai/gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "openai/gpt-5.5":     {"input": 5.0, "output": 20.0},
    "openai/gpt-5.5-pro": {"input": 10.0, "output": 40.0},
    "openai/gpt-5.4":     {"input": 3.0, "output": 12.0},
    "openai/gpt-5.4-mini": {"input": 0.3, "output": 1.2},

    # Google
    "google/gemini-3.5-flash":      {"input": 0.15, "output": 0.60},
    "google/gemini-3.5-pro":        {"input": 2.5, "output": 10.0},
    "google/gemini-3.1-flash":      {"input": 0.075, "output": 0.30},
    "google/gemini-3.1-flash-lite": {"input": 0.05, "output": 0.20},

    # DeepSeek (cheap)
    "deepseek/deepseek-v4-flash": {"input": 0.10, "output": 0.30},
    "deepseek/deepseek-v4-pro":   {"input": 0.50, "output": 1.50},
}

# Fallback cho model không có trong table — assume "mid-tier".
DEFAULT_PRICE = {"input": 1.0, "output": 5.0}


@dataclass(frozen=True)
class CostBreakdown:
    model: str
    tokens_in: int
    tokens_out: int
    input_usd: float
    output_usd: float
    total_usd: float
    pricing_known: bool


def estimate_cost(model: str, tokens_in: int, tokens_out: int) -> CostBreakdown:
    """Estimate cost cho 1 API call.

    Trả về breakdown chi tiết. `pricing_known` = False → dùng DEFAULT_PRICE,
    số liệu chỉ là approximation, audit log nên flag để admin biết.
    """
    price = PRICING.get(model)
    known = price is not None
    if not known:
        price = DEFAULT_PRICE

    input_usd = (tokens_in or 0) * price["input"] / 1_000_000
    output_usd = (tokens_out or 0) * price["output"] / 1_000_000

    return CostBreakdown(
        model=model,
        tokens_in=tokens_in or 0,
        tokens_out=tokens_out or 0,
        input_usd=round(input_usd, 6),
        output_usd=round(output_usd, 6),
        total_usd=round(input_usd + output_usd, 6),
        pricing_known=known,
    )
