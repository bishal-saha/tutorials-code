"""What fills the window over a shift, and what it costs. No API key.

uv run python window.py            # Sonnet 5.5 prices
uv run python window.py --haiku    # Haiku 5.5 prices
"""

import json
import sys
from collections import Counter

import anyio
from copilot.grading import grade
from copilot.model import CacheSim, ShiftModel, tokens
from copilot.shift import SYSTEM_PROMPT, run_shift
from copilot.tools import TOOLS


def anatomy(messages):
    """Tokens in the final window, by what put them there."""
    parts = Counter(
        {"tool definitions": tokens(json.dumps(TOOLS)), "system prompt": tokens(SYSTEM_PROMPT)}
    )
    names = {}
    for m in messages:
        for b in m["content"]:
            if b["type"] == "tool_use":
                names[b["id"]] = b["name"]
                parts["assistant turns"] += tokens(json.dumps(b))
            elif b["type"] == "text":
                kind = "assistant turns" if m["role"] == "assistant" else "user turns"
                parts[kind] += tokens(b["text"])
            elif b["type"] == "tool_result":
                parts[f"{names[b['tool_use_id']]} results"] += tokens(b["content"])
    return parts


async def main(model_name: str) -> None:
    cached = await run_shift(ShiftModel(model_name))
    uncached = await run_shift(ShiftModel(model_name, cache=CacheSim(enabled=False)))

    print(
        f"{'ticket':<8} {'calls':>5} {'window':>7} {'cache read':>10} {'cache write':>11} {'$':>8}"
    )
    for t in dict.fromkeys(r.ticket_id for r in cached.requests):
        rs = [r for r in cached.requests if r.ticket_id == t]
        print(
            f"{t:<8} {len(rs):>5} {rs[-1].usage.prompt_tokens:>7} "
            f"{sum(r.usage.cache_read_tokens for r in rs):>10} "
            f"{sum(r.usage.cache_write_tokens for r in rs):>11} {sum(r.usd for r in rs):>8.4f}"
        )

    print("\nWhat the last request carried:")
    parts = anatomy(cached.messages)
    total = sum(parts.values())
    for name, n in parts.most_common():
        print(f"  {name:<22} {n:>6} tokens  {n / total:>4.0%}")

    g = grade(cached.tools)
    print(
        f"\nshift: {len(cached.requests)} requests, ${cached.usd:.4f} with caching, "
        f"${uncached.usd:.4f} without; standing instructions held on {g.retention:.0%} of tickets"
    )


if __name__ == "__main__":
    anyio.run(main, "claude-haiku-5-5" if "--haiku" in sys.argv else "claude-sonnet-5-5")
