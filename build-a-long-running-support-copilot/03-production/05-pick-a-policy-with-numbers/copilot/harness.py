"""The shift harness: run candidate policies on the same shift and compare them.

Each policy gets a fresh model (and so a fresh cache) and the same 24 tickets.
The report is what you choose a policy from: window size, cost, cache-hit rate,
how many tickets were handled, and whether the standing instructions held.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from copilot.grading import grade
from copilot.model import ModelClient
from copilot.shift import run_shift

CANDIDATES: dict[str, dict[str, Any]] = {
    "raw": {},
    "trim": {"policy": "trim"},
    "clear": {"policy": "clear"},
    "summary+pin": {"policy": "summary+pin"},
    "fresh": {"policy": "fresh"},
}


@dataclass(frozen=True)
class PolicyReport:
    name: str
    requests: int
    mean_window: int
    final_window: int
    cache_hit: float
    cache_write_tokens: int
    usd: float
    handled: int
    retention: float

    def row(self) -> str:
        return (
            f"{self.name:<14} {self.mean_window:>8} {self.final_window:>8} {self.cache_hit:>7.1%} "
            f"{self.cache_write_tokens:>9} {self.usd:>8.4f} {self.handled:>4}/24 "
            f"{self.retention:>9.0%}"
        )


HEADER = (
    f"{'policy':<14} {'mean win':>8} {'last win':>8} {'hit':>7} {'cache wr':>9} {'$/shift':>8} "
    f"{'handled':>7} {'retention':>9}"
)


async def measure(name: str, model: ModelClient, **kwargs: Any) -> PolicyReport:
    r = await run_shift(model, **kwargs)
    g = grade(r.tools)
    # Window and cache figures are the copilot's own requests; cost counts everything,
    # including summariser and compaction calls (turn -1 and 0).
    own = [q for q in r.requests if q.turn >= 1]
    prompt = sum(q.usage.prompt_tokens for q in own)
    return PolicyReport(
        name=name,
        requests=len(own),
        mean_window=prompt // max(1, len(own)),
        final_window=own[-1].usage.prompt_tokens if own else 0,
        cache_hit=sum(q.usage.cache_read_tokens for q in own) / prompt if prompt else 0.0,
        cache_write_tokens=sum(q.usage.cache_write_tokens for q in own),
        usd=r.usd,
        handled=g.handled,
        retention=g.retention,
    )


async def compare(
    new_model: Callable[[], ModelClient], candidates: dict[str, dict[str, Any]] = CANDIDATES
) -> list[PolicyReport]:
    return [await measure(name, new_model(), **kwargs) for name, kwargs in candidates.items()]
