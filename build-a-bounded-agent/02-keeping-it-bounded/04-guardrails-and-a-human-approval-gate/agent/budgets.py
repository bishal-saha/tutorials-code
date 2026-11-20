"""Hard limits on one run: steps, tokens, cost and wall-clock time.

The harness checks them on every step. The model is never asked to respect
them; it can't run past them.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from agent.models import Usage
from agent.pricing import cost_usd


@dataclass(frozen=True)
class Budget:
    max_steps: int = 12
    max_tokens: int = 60_000  # input (cached or not) + output, summed over the run
    max_cost_usd: float = 0.50
    max_seconds: float = 120.0


class BudgetTracker:
    def __init__(self, budget: Budget, model: str, clock: Callable[[], float] = time.monotonic):
        self.budget = budget
        self.model = model
        self.clock = clock
        self.started = clock()
        self.steps = 0
        self.usage = Usage()

    @property
    def cost(self) -> float:
        return cost_usd(self.model, self.usage)

    def before_step(self) -> str | None:
        """Checked before each model call: may we start another step?"""
        if self.steps >= self.budget.max_steps:
            return f"step budget of {self.budget.max_steps} used"
        elapsed = self.clock() - self.started
        if elapsed >= self.budget.max_seconds:
            return f"time budget of {self.budget.max_seconds:g}s used ({elapsed:.1f}s)"
        return None

    def charge(self, usage: Usage) -> str | None:
        """Checked after each model call, with what it actually cost."""
        self.steps += 1
        self.usage = self.usage + usage
        u = self.usage
        # Every token the model read or wrote counts, cached or not.
        tokens = u.input_tokens + u.cache_read + u.cache_write + u.output_tokens
        if tokens > self.budget.max_tokens:
            return f"token budget of {self.budget.max_tokens:,} exceeded ({tokens:,})"
        if self.cost > self.budget.max_cost_usd:
            return f"cost budget of ${self.budget.max_cost_usd:.2f} exceeded (${self.cost:.4f})"
        return None
