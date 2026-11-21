"""Run a shift: one conversation, 24 tickets, every request recorded.

Lesson 4 adds the policies that replace history instead of shrinking it: a running
summary (with or without pinned instructions), a fresh window per ticket, and
server-side compaction. A memory directory can carry notes from one shift to the next.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from copilot.model import ModelClient, Usage
from copilot.policies import STUB, SUMMARISED, TicketLog, Window, build_messages, close
from copilot.pricing import price_for
from copilot.prompt import add_operator_note
from copilot.shift_data import OPENING, TICKETS, announce
from copilot.summariser import RuleSummariser, Summariser
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


def _usd(model: str, u: Usage) -> float:
    p = price_for(model, u.prompt_tokens)
    return (
        u.input_tokens * p.input
        + u.output_tokens * p.output
        + u.cache_write_tokens * p.cache_write
        + u.cache_read_tokens * p.cache_read
    ) / 1e6


async def run_shift(
    model: ModelClient,
    *,
    policy: str = "raw",
    stub: str = STUB,
    summariser: Summariser | None = None,
    compact_every: int = 6,
    memory: Any = None,
    opening: str = OPENING,
    system: str | Builder = SYSTEM_PROMPT,
    tools: list[dict[str, Any]] | Builder = TOOLS,
    notes: dict[str, str] | None = None,
    note_mode: Literal["message", "edit_system"] = "message",
    tickets: list[dict[str, Any]] = TICKETS,
    max_usd: float | None = None,
) -> ShiftResult:
    """`system` and `tools` may be values or functions called on every request.
    `notes` maps a ticket id to an operator note that arrives with that ticket.
    `memory` is a memory tool (anthropic.tools.memory); it is offered as a tool."""
    result = ShiftResult(tools=ShiftTools(memory=memory))
    summariser = summariser or RuleSummariser()
    window = Window(opening=opening)
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
            tool_list = tools() if callable(tools) else list(tools)
            if memory is not None:
                tool_list.append(memory.to_dict())
            messages = build_messages(policy, logs, stub, window)
            reply = await model.complete(system=sys_text, messages=messages, tools=tool_list)
            result.requests.append(
                Request(ticket["id"], turn, reply.usage, _usd(model.model, reply.usage))
            )
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
        # --- the ticket boundary: the only place a policy rebuilds the window ---
        if policy in ("clear", *SUMMARISED, "fresh", "compact"):
            close(log)
        if policy in SUMMARISED:
            window.summary = await summariser.summarise(window.summary, log)
        if policy == "compact" and (i + 1) % compact_every == 0 and i + 1 < len(tickets):
            block, usage = await model.compact(
                system=sys_text,
                messages=build_messages(policy, logs, stub, window),
                tools=tool_list,
            )
            window.compaction, window.compacted = block, i + 1
            result.requests.append(Request(ticket["id"], 0, usage, _usd(model.model, usage)))
    result.messages = build_messages(policy, logs, stub, window)
    return result
