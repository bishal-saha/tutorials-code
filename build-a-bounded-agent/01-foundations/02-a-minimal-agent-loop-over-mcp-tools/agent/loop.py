"""The agent loop: call the model, run the tools it asks for, send the results back.

This is the minimal version. It stops when the model says it is done, or when
something other than a tool call ends the turn. The only limit is a safety cap
on steps; Lesson 3 replaces it with real budgets.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agent.models import Model, Turn, Usage
from agent.tools import McpTools

SAFETY_CAP_STEPS = 25


class SafetyCapReached(RuntimeError):
    """The run hit the step cap. In a minimal loop this is the only brake."""


@dataclass
class RunResult:
    outcome: str  # done | truncated | refused | stopped:<reason>
    final_text: str
    steps: int
    usage: Usage
    trace: list[dict[str, Any]] = field(default_factory=list)


async def run_agent(
    model: Model,
    tools: McpTools,
    task: str,
    *,
    system: str,
    max_steps: int = SAFETY_CAP_STEPS,
) -> RunResult:
    definitions = await tools.definitions()
    messages: list[dict[str, Any]] = [{"role": "user", "content": task}]
    usage = Usage()
    trace: list[dict[str, Any]] = []

    for step in range(1, max_steps + 1):
        turn: Turn = await model.complete(system=system, tools=definitions, messages=messages)
        usage = usage + turn.usage
        record: dict[str, Any] = {
            "step": step,
            "stop_reason": turn.stop_reason,
            "usage": vars(turn.usage),
            "tool_calls": [],
        }
        trace.append(record)

        # Read stop_reason before content: it says what the content is.
        if turn.stop_reason == "end_turn":
            return RunResult("done", turn.text(), step, usage, trace)
        if turn.stop_reason in ("max_tokens", "model_context_window_exceeded"):
            # Cut off (output limit or context window): a half-written tool call must not run.
            return RunResult("truncated", turn.text(), step, usage, trace)
        if turn.stop_reason == "refusal":
            return RunResult("refused", turn.text(), step, usage, trace)
        if turn.stop_reason == "pause_turn":
            # A server-side tool paused the turn: send it back unchanged to continue.
            messages.append({"role": "assistant", "content": turn.content})
            continue
        if turn.stop_reason != "tool_use":
            return RunResult(f"stopped:{turn.stop_reason}", turn.text(), step, usage, trace)

        # The assistant turn goes back exactly as received, thinking blocks included.
        messages.append({"role": "assistant", "content": turn.content})
        results = []
        for call in turn.tool_calls():
            outcome = await tools.call(call["name"], call["input"])
            record["tool_calls"].append(
                {"name": call["name"], "input": call["input"], "is_error": outcome.is_error}
            )
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": call["id"],
                    "content": outcome.text,
                    "is_error": outcome.is_error,
                }
            )
        # Every result for this turn goes back in one user message.
        messages.append({"role": "user", "content": results})

    raise SafetyCapReached(f"stopped after {max_steps} steps without finishing")
