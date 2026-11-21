"""Context policies: what the next request's window holds.

The runner keeps the whole shift as one TicketLog per ticket and asks a policy,
before every request, which messages to send:

    raw          everything, as it happened
    trim         the same as raw; tool results were trimmed when they were added (trim.py)
    clear        raw, but once a ticket is closed its tool results become placeholders
    summary      a running summary of closed tickets, then the current ticket
    summary+pin  the same, with the standing instructions kept word for word outside it
    fresh        a new window per ticket: the opening message, then the current ticket
    compact      server-side compaction (beta): a compaction block from the API stands
                 in for everything it summarised, then the tickets since

Every rebuild (clear, summary, fresh, compact) happens at a ticket boundary, so the
cached prefix breaks once per ticket at most. Adapted from AI Lab experiment 7
(ai-lab-code/context-rot-benchmark/src/ticket_thirty/policies.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from copilot.shift_data import INSTRUCTIONS_BLOCK, OPENING, announce, opening_for

POLICIES = ("raw", "trim", "clear", "summary", "summary+pin", "fresh", "compact")
SUMMARISED = ("summary", "summary+pin")

# The placeholder says what happened and that the ticket needs nothing more.
# Experiment 7's final wording ended "call the tool again if you need the details";
# one short diagnostic run saw Haiku take that invitation, but a full measured shift
# per wording (live_placeholders.py) found 0 re-fetches with it and 1 with this one.
# Both work; the wording that fails is MISLEADING_STUB. Live `clear` cost more than
# `raw` with either wording, because it rebuilds the cache at every ticket boundary.
STUB = (
    "[Result removed from the context after {ticket} was finished, to save space. "
    "You received the full result at the time and acted on it; that ticket is done "
    "and needs no more work. The call was {call}.]"
)

# Experiment 7's final wording, for comparison in live_placeholders.py.
INVITING_STUB = (
    "[Result removed from the context after {ticket} was finished, to save space. "
    "You received the full result at the time and acted on it. The call was {call}; "
    "call the tool again if you need the details.]"
)

# The pilot's first wording. Haiku read it as "you never had this data", decided every
# result it had received was a placeholder, and stopped working on 9 of 24 tickets.
MISLEADING_STUB = "[cleared after {ticket} closed: {call}. Call it again if needed.]"


@dataclass
class TicketLog:
    ticket_id: str
    first: bool = False
    turns: list[dict[str, Any]] = field(default_factory=list)
    closed: bool = False


@dataclass
class Window:
    """What the shift carries besides the ticket logs."""

    opening: str = OPENING
    summary: str | None = None  # summary policies: the running summary
    compaction: dict[str, Any] | None = None  # compact policy: the block, exactly as returned
    compacted: int = 0  # compact policy: how many tickets the block replaces


def close(log: TicketLog) -> None:
    """Freeze a finished ticket before its window is rebuilt.

    Thinking blocks are dropped here: the API needs them only inside the tool loop
    that produced them, and this ticket's loop is over. Only do this when you are
    rebuilding the window anyway; in `raw` it would rewrite the prefix for nothing.
    """
    for m in log.turns:
        if m["role"] == "assistant":
            kept = [b for b in m["content"] if b["type"] not in ("thinking", "redacted_thinking")]
            m["content"] = kept or [{"type": "text", "text": "(done)"}]
    log.closed = True


def stubbed(log: TicketLog, stub: str) -> list[dict[str, Any]]:
    """A closed ticket's turns with every tool result replaced by a placeholder."""
    calls = {
        b["id"]: f"{b['name']}({', '.join(f'{k}={v}' for k, v in b['input'].items())})"
        for m in log.turns
        if m["role"] == "assistant"
        for b in m["content"]
        if b["type"] == "tool_use"
    }
    out = []
    for m in log.turns:
        if m["role"] == "user" and isinstance(m["content"], list):
            content = [
                {
                    **b,
                    "content": stub.format(
                        ticket=log.ticket_id, call=calls.get(b["tool_use_id"], "a tool")
                    ),
                }
                if b.get("type") == "tool_result"
                else b
                for b in m["content"]
            ]
            out.append({"role": "user", "content": content})
        else:
            out.append(m)
    return out


def _add_user(msgs: list[dict[str, Any]], text: str) -> None:
    """Append a user text turn, merging into a previous user turn (a ticket that ran
    out of turns ends on tool results, and two user turns can't follow each other)."""
    block = {"type": "text", "text": text}
    if msgs and msgs[-1]["role"] == "user":
        msgs[-1] = {"role": "user", "content": [*msgs[-1]["content"], block]}
    else:
        msgs.append({"role": "user", "content": [block]})


def build_messages(
    policy: str, logs: list[TicketLog], stub: str = STUB, window: Window | None = None
) -> list[dict[str, Any]]:
    if policy not in POLICIES:
        raise ValueError(f"unknown policy {policy!r}")
    if not logs:
        return []
    w = window or Window()
    current = logs[-1]
    msgs: list[dict[str, Any]] = []

    if policy in ("raw", "trim", "clear"):
        for log in logs:
            _add_user(
                msgs,
                opening_for(log.ticket_id, w.opening) if log.first else announce(log.ticket_id),
            )
            msgs += stubbed(log, stub) if (policy == "clear" and log.closed) else log.turns
        return msgs

    if policy == "compact":
        if w.compaction is None:
            return build_messages("raw", logs, stub, w)
        # The block goes first, exactly as the API returned it (signature included);
        # the messages it summarised are gone.
        msgs.append({"role": "assistant", "content": [w.compaction]})
        for log in logs[w.compacted :]:
            _add_user(msgs, announce(log.ticket_id))
            msgs += log.turns
        return msgs

    if policy == "fresh" or w.summary is None:
        _add_user(msgs, opening_for(current.ticket_id, w.opening))
        return msgs + current.turns

    head = f"Summary of the work so far (it replaces the earlier conversation):\n{w.summary}"
    if policy == "summary+pin":
        pinned = "Standing instructions from the start of the shift, kept word for word:"
        head = f"{pinned}\n{INSTRUCTIONS_BLOCK}\n\n{head}"
    _add_user(msgs, f"{head}\n\n{announce(current.ticket_id)}")
    return msgs + current.turns
