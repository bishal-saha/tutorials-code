"""Run a shift: one conversation, 24 tickets, every request recorded.

Lesson 3 keeps the shift as one log per ticket and asks a policy (policies.py)
what each request's window should hold: everything, trimmed results, or closed
tickets with their results cleared.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from copilot.model import ModelClient, Usage
from copilot.policies import STUB, TicketLog, build_messages, close
from copilot.pricing import price_for
from copilot.prompt import add_operator_note
from copilot.shift_data import TICKETS, announce
from copilot.tools import TOOLS, ShiftTools
from copilot.trim import trim_result

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
    stopped_at_cap: bool = False

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


Builder = Callable[[], Any]


async def run_shift(
    model: ModelClient,
    *,
    policy: str = "raw",
    stub: str = STUB,
    system: str | Builder = SYSTEM_PROMPT,
    tools: list[dict[str, Any]] | Builder = TOOLS,
    notes: dict[str, str] | None = None,
    note_mode: Literal["message", "edit_system"] = "message",
    tickets: list[dict[str, Any]] = TICKETS,
    max_usd: float | None = None,
) -> ShiftResult:
    """`system` and `tools` may be values or functions called on every request.
    `notes` maps a ticket id to an operator note that arrives with that ticket.
    `max_usd` stops the shift before any request once spend reaches it."""
    result = ShiftResult()
    logs: list[TicketLog] = []
    system_notes: list[str] = []
    for i, ticket in enumerate(tickets):
        log = TicketLog(ticket["id"], first=i == 0)
        logs.append(log)
        if notes and ticket["id"] in notes:
            if note_mode == "message":
                lead = [
                    {"role": "user", "content": [{"type": "text", "text": announce(ticket["id"])}]}
                ]
                add_operator_note(lead, notes[ticket["id"]])
                log.turns.append(lead[-1])
            else:  # the mistake: grow the top-level system prompt
                system_notes.append(f"Operator note: {notes[ticket['id']]}")
        for turn in range(1, MAX_TURNS_PER_TICKET + 1):
            if max_usd is not None and result.usd >= max_usd:
                result.stopped_at_cap = True  # checked before every request
                break
            sys_text = "\n".join([system() if callable(system) else system, *system_notes])
            tool_list = tools() if callable(tools) else tools
            messages = build_messages(policy, logs, stub)
            reply = await model.complete(system=sys_text, messages=messages, tools=tool_list)
            price = price_for(model.model, reply.usage.prompt_tokens)
            u = reply.usage
            usd = (
                u.input_tokens * price.input
                + u.output_tokens * price.output
                + u.cache_write_tokens * price.cache_write
                + u.cache_read_tokens * price.cache_read
            ) / 1e6
            result.requests.append(Request(ticket["id"], turn, u, usd))
            log.turns.append({"role": "assistant", "content": reply.content})
            calls = reply.tool_calls()
            if not calls:
                break
            results = []
            for c in calls:
                out = result.tools.run(c["name"], c["input"])
                if policy == "trim":
                    out = trim_result(c["name"], out)  # once, at the boundary
                results.append({"type": "tool_result", "tool_use_id": c["id"], "content": out})
            log.turns.append({"role": "user", "content": results})
        if result.stopped_at_cap:
            break
        if policy == "clear":
            close(log)
    result.messages = build_messages(policy, logs, stub)
    return result
