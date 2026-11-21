"""Claude API prices, $ per million tokens, from the pricing page on 2026-11-21.

Cache writes use the 5-minute TTL rate. Haiku 5.5 is priced higher for any single
request whose prompt (cache reads and writes included) is over 100,000 tokens.
Prices change: check the pricing page before you rely on these numbers.
"""

from __future__ import annotations

from dataclasses import dataclass

PRICES_CHECKED_ON = "2026-11-21"


@dataclass(frozen=True)
class Price:
    input: float
    output: float
    cache_write: float
    cache_read: float


SONNET = Price(input=2.00, output=10.00, cache_write=2.50, cache_read=0.10)
HAIKU = Price(input=0.10, output=0.50, cache_write=0.125, cache_read=0.01)
HAIKU_LONG = Price(input=0.50, output=2.50, cache_write=0.625, cache_read=0.05)


def price_for(model: str, prompt_tokens: int) -> Price:
    if model == "claude-sonnet-5-5":
        return SONNET
    if model == "claude-haiku-5-5":
        return HAIKU_LONG if prompt_tokens > 100_000 else HAIKU
    raise KeyError(f"No price pinned for {model!r}")
