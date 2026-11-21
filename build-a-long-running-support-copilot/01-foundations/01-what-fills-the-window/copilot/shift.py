"""Run a shift: one conversation, 24 tickets, every request recorded.

Lesson 1 keeps everything (the `raw` policy): each ticket's turns are appended
to one growing conversation and the whole thing is sent on every request.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from copilot.model import ModelClient, Usage
from copilot.pricing import price_for
from copilot.shift_data import TICKETS, announce, opening_for
from copilot.tools import TOOLS, ShiftTools

SYSTEM_PROMPT = (
    "You are Helpline's support copilot. You work through a queue of tickets for one shift. "
    "Use the tools; never invent ticket details. Keep replies short and specific."
)
MAX_TURNS_PER_TICKET = 8


@dataclass
class Request:
    """One model call, as the ledger sees it."""

    ticket_id: str
    turn: int
    usage: Usage
    usd: float


@dataclass
class ShiftResult:
    requests: list[Request] = field(default_factory=list)
    tools: ShiftTools = field(default_factory=ShiftTools)
    messages: list[dict[str, Any]] = field(default_factory=list, repr=False)

    @property
    def usd(self) -> float:
        return sum(r.usd for r in self.requests)

    @property
    def usage(self) -> Usage:
        total = Usage()
        for r in self.requests:
            total += r.usage
        return total

    def window_at_end(self, ticket_id: str) -> int:
        """Prompt tokens on the last request for a ticket."""
        return [r for r in self.requests if r.ticket_id == ticket_id][-1].usage.prompt_tokens


def _user(messages: list[dict[str, Any]], text: str) -> None:
    messages.append({"role": "user", "content": [{"type": "text", "text": text}]})


async def run_shift(
    model: ModelClient, *, system: str = SYSTEM_PROMPT, tickets: list[dict[str, Any]] = TICKETS
) -> ShiftResult:
    result = ShiftResult()
    messages = result.messages
    for i, ticket in enumerate(tickets):
        _user(messages, opening_for(ticket["id"]) if i == 0 else announce(ticket["id"]))
        for turn in range(1, MAX_TURNS_PER_TICKET + 1):
            reply = await model.complete(system=system, messages=messages, tools=TOOLS)
            price = price_for(model.model, reply.usage.prompt_tokens)
            u = reply.usage
            usd = (
                u.input_tokens * price.input
                + u.output_tokens * price.output
                + u.cache_write_tokens * price.cache_write
                + u.cache_read_tokens * price.cache_read
            ) / 1e6
            result.requests.append(Request(ticket["id"], turn, u, usd))
            messages.append({"role": "assistant", "content": reply.content})
            calls = reply.tool_calls()
            if not calls:
                break
            messages.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": c["id"],
                            "content": result.tools.run(c["name"], c["input"]),
                        }
                        for c in calls
                    ],
                }
            )
    return result
