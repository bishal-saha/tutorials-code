"""A circuit breaker per tool: stop calling a tool that keeps failing.

closed  -> calls go through; failures are counted
open    -> calls are refused without touching the tool, for `cooldown` seconds
half-open -> one trial call; success closes the breaker, failure opens it again
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class CircuitBreaker:
    failure_threshold: int = 3
    cooldown: float = 30.0
    clock: Callable[[], float] = time.monotonic
    failures: int = 0
    opened_at: float | None = None

    @property
    def state(self) -> str:
        if self.opened_at is None:
            return "closed"
        if self.clock() - self.opened_at >= self.cooldown:
            return "half-open"
        return "open"

    def allow(self) -> bool:
        return self.state != "open"

    def record(self, ok: bool) -> None:
        if ok:
            self.failures, self.opened_at = 0, None
            return
        self.failures += 1
        if self.state == "half-open" or self.failures >= self.failure_threshold:
            self.opened_at = self.clock()


@dataclass
class Breakers:
    """One breaker per tool name, created on first use."""

    failure_threshold: int = 3
    cooldown: float = 30.0
    clock: Callable[[], float] = time.monotonic
    by_tool: dict[str, CircuitBreaker] = field(default_factory=dict)

    def for_tool(self, name: str) -> CircuitBreaker:
        if name not in self.by_tool:
            self.by_tool[name] = CircuitBreaker(self.failure_threshold, self.cooldown, self.clock)
        return self.by_tool[name]
