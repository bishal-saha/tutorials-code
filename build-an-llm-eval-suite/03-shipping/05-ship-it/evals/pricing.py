"""Cost of model calls from the usage the API reports.

Claude API prices (USD per million tokens), checked 2026-11-21 at
https://platform.claude.com/docs/en/about-claude/pricing . Cache writes (5-minute
TTL) cost 1.25x input. Cache hits cost 0.05x input on claude-sonnet-5-5 and 0.1x
on claude-haiku-5-5, so keep a rate per model rather than one multiplier.
"""

from __future__ import annotations

from evals.models import Usage

# model: (input, output, cache write 5m, cache hit)
PRICES = {
    "claude-sonnet-5-5": (2.00, 10.00, 2.50, 0.10),
    "claude-haiku-5-5": (0.10, 0.50, 0.125, 0.01),
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
