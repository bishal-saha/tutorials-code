"""The agent loop, bounded and guarded.

Lesson 3's limits (budgets, breakers, retries, repeated calls) plus Lesson 4's
guardrails, all enforced by the harness before a tool runs:
- the task's tool allowlist, both when tools are offered and when one is called
- the scope check: ticket-level writes stay on the task's ticket
- draft checks before draft_reply saves anything
- a human approval gate on irreversible calls, with a decision record
- customer-written tool results delimited as untrusted data
"""

from __future__ import annotations

import json
import time
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import anyio

from agent.approval import ApprovalLog, ApprovalRequest, Approver
from agent.breaker import Breakers
from agent.budgets import Budget, BudgetTracker
from agent.guardrails import IRREVERSIBLE, Policy, check_draft, untrusted
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


@dataclass
class Guards:
    policy: Policy
    approver: Approver
    log: ApprovalLog = field(default_factory=ApprovalLog)


def call_key(name: str, arguments: dict[str, Any]) -> str:
    return name + json.dumps(arguments, sort_keys=True)


async def run_agent(
    model: Model,
    tools: McpTools,
    task: str,
    *,
    system: str,
    guards: Guards,
    limits: Limits | None = None,
) -> RunResult:
    limits = limits or Limits()
    # Offer only the task's tools: the model can't pick what it never sees.
    definitions = [d for d in await tools.definitions() if d["name"] in guards.policy.tools]
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
            outcome, note = await guarded_call(
                tools, limits, guards, seen, call["name"], call["input"]
            )
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
                    "content": untrusted(call["name"], outcome.text),
                    "is_error": outcome.is_error,
                }
            )
        messages.append({"role": "user", "content": results})


async def guarded_call(
    tools: McpTools,
    limits: Limits,
    guards: Guards,
    seen: Counter[str],
    name: str,
    arguments: dict[str, Any],
) -> tuple[ToolOutcome, str]:
    """Run one tool call through the guardrails, then Lesson 3's limits."""
    policy = guards.policy
    if refusal := policy.refusal(name, arguments):
        return ToolOutcome(f"Refused: {refusal}", True), "policy_refused"

    if name == "draft_reply":
        problems = check_draft(str(arguments.get("message", "")), policy)
        if problems:
            text = "Draft not saved. It " + "; it ".join(problems) + ". Fix the text and retry."
            return ToolOutcome(text, True), "draft_check_failed"

    if name in IRREVERSIBLE:
        request = ApprovalRequest(name, arguments, policy.task, policy.ticket_id)
        decision = await guards.approver.decide(request)
        guards.log.record(request, decision)
        if not decision.approved:
            text = f"A person declined this {name} call: {decision.reason}"
            return ToolOutcome(text, True), "approval_denied"

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
            if name in IRREVERSIBLE and not outcome.is_error:
                policy.escalated = True
            return outcome, note
        await limits.sleep(BACKOFF_SECONDS[min(attempt - 1, len(BACKOFF_SECONDS) - 1)])
    raise AssertionError("unreachable")
