"""Cost of a run from the usage the API reports.

Claude API prices (USD per million tokens), checked 2026-11-21 at
https://platform.claude.com/docs/en/about-claude/pricing . For claude-opus-5-5:
input $4, output $20, 5-minute cache writes $5 (1.25x input) and cache hits
$0.20 (0.05x input; most other models use 0.1x, so read the table per model).
"""

from __future__ import annotations

from agent.models import Usage

# model: (input, output, cache write 5m, cache hit)
PRICES = {
    "claude-opus-5-5": (4.00, 20.00, 5.00, 0.20),
    "fake": (0.0, 0.0, 0.0, 0.0),
}


def cost_usd(model: str, usage: Usage) -> float:
    price_in, price_out, price_write, price_hit = PRICES[model]
    total = (
        usage.input_tokens * price_in
        + usage.output_tokens * price_out
        + usage.cache_write * price_write
        + usage.cache_read * price_hit
    ) / 1_000_000
    return round(total, 6)
