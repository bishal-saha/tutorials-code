"""The agent loop, bounded.

Lesson 2's loop plus four limits the harness enforces on every step:
- budgets: steps, tokens, cost and wall-clock time (agent/budgets.py)
- a circuit breaker per tool (agent/breaker.py)
- retries with backoff, only for read-only tools and only for transient failures
- repeated-call detection: the same call with the same arguments is refused
"""

from __future__ import annotations

import json
import time
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import anyio

from agent.breaker import Breakers
from agent.budgets import Budget, BudgetTracker
from agent.models import Model, Turn, Usage
from agent.tools import McpTools, ToolOutcome

MAX_RETRIES = 2
BACKOFF_SECONDS = (0.5, 1.0)
REPEAT_LIMIT = 2  # the third identical call is refused


@dataclass
class RunResult:
    outcome: str  # done | budget_exhausted | truncated | refused | stopped:<reason>
    final_text: str
    steps: int
    usage: Usage
    cost_usd: float = 0.0
    reason: str = ""
    trace: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Limits:
    budget: Budget = field(default_factory=Budget)
    breakers: Breakers = field(default_factory=Breakers)
    clock: Callable[[], float] = time.monotonic
    sleep: Callable[[float], Awaitable[None]] = anyio.sleep


def call_key(name: str, arguments: dict[str, Any]) -> str:
    return name + json.dumps(arguments, sort_keys=True)


async def run_agent(
    model: Model,
    tools: McpTools,
    task: str,
    *,
    system: str,
    limits: Limits | None = None,
) -> RunResult:
    limits = limits or Limits()
    definitions = await tools.definitions()
    tracker = BudgetTracker(limits.budget, model.name, limits.clock)
    messages: list[dict[str, Any]] = [{"role": "user", "content": task}]
    trace: list[dict[str, Any]] = []
    seen: Counter[str] = Counter()
    last_text = ""

    def finish(outcome: str, text: str, reason: str = "") -> RunResult:
        return RunResult(outcome, text, tracker.steps, tracker.usage, tracker.cost, reason, trace)

    while True:
        if reason := tracker.before_step():
            return finish("budget_exhausted", last_text, reason)

        turn: Turn = await model.complete(system=system, tools=definitions, messages=messages)
        over = tracker.charge(turn.usage)
        record: dict[str, Any] = {
            "step": tracker.steps,
            "stop_reason": turn.stop_reason,
            "usage": vars(turn.usage),
            "tool_calls": [],
        }
        trace.append(record)

        if turn.stop_reason == "end_turn":
            return finish("done", turn.text())
        if turn.stop_reason in ("max_tokens", "model_context_window_exceeded"):
            return finish("truncated", turn.text())
        if turn.stop_reason == "refusal":
            return finish("refused", turn.text())
        if over:
            # The step that crossed the line is paid for; its tool calls do not run.
            return finish("budget_exhausted", turn.text() or last_text, over)
        if turn.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": turn.content})
            continue
        if turn.stop_reason != "tool_use":
            return finish(f"stopped:{turn.stop_reason}", turn.text())

        # Only now, with stop_reason known to be tool_use, is the content read.
        last_text = turn.text() or last_text
        messages.append({"role": "assistant", "content": turn.content})
        results = []
        for call in turn.tool_calls():
            outcome, note = await guarded_call(tools, limits, seen, call["name"], call["input"])
            record["tool_calls"].append(
                {
                    "name": call["name"],
                    "input": call["input"],
                    "is_error": outcome.is_error,
                    "note": note,
                }
            )
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": call["id"],
                    "content": outcome.text,
                    "is_error": outcome.is_error,
                }
            )
        messages.append({"role": "user", "content": results})


async def guarded_call(
    tools: McpTools, limits: Limits, seen: Counter[str], name: str, arguments: dict[str, Any]
) -> tuple[ToolOutcome, str]:
    """Run one tool call through the repeat check, the breaker and the retry policy."""
    key = call_key(name, arguments)
    if seen[key] >= REPEAT_LIMIT:
        return (
            ToolOutcome(
                f"Refused: you already called {name} with these exact arguments "
                f"{seen[key]} times and the result will not change. Use what you have, "
                "try different arguments, or finish.",
                True,
            ),
            "repeat_refused",
        )
    seen[key] += 1

    breaker = limits.breakers.for_tool(name)
    if not breaker.allow():
        return (
            ToolOutcome(
                f"{name} is unavailable: it failed {breaker.failures} times in a row. "
                "Continue without it, or finish and say what you could not check.",
                True,
            ),
            "breaker_open",
        )

    attempts = 1 + (MAX_RETRIES if name in tools.read_only else 0)
    for attempt in range(1, attempts + 1):
        outcome = await tools.call(name, arguments)
        failed = outcome.is_error and outcome.transient
        breaker.record(not failed)
        note = f"attempts={attempt}" + ("" if breaker.allow() else ", breaker opened")
        if not failed or attempt == attempts or not breaker.allow():
            return outcome, note
        await limits.sleep(BACKOFF_SECONDS[min(attempt - 1, len(BACKOFF_SECONDS) - 1)])
    raise AssertionError("unreachable")
