"""Lay out every request so the cached prefix survives the whole shift.

The API reads tools, then the system prompt, then the messages. A change to any
byte invalidates the cache from that point on, so the order is stable first,
volatile last:

    tools          fixed order, canonical JSON          never change in a shift
    system prompt  frozen: no clock, no ids, no notes   never changes in a shift
    messages       appended, never edited               grow every turn
"""

from __future__ import annotations

import json
from typing import Any


def stable_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The same tools, always in the same order with the same key order.

    Tool lists built from a registry, a plugin scan or a set can come out in a
    different order on each request. To the cache that is a different prompt.
    """
    canonical = [json.loads(json.dumps(t, sort_keys=True)) for t in tools]
    return sorted(canonical, key=lambda t: t["name"])


class NotePlacementError(ValueError):
    pass


def add_operator_note(messages: list[dict[str, Any]], note: str) -> None:
    """Add a mid-shift instruction from the operator without touching the cached prefix.

    It goes in as a role "system" message appended to the conversation, never as an
    edit to the top-level system prompt (that would rewrite the start of every later
    request). It must follow a plain user turn: on Sonnet 5.5 and Haiku 5.5 a system
    message right after a tool result may be read as untrusted text and ignored, and
    one between a tool_use and its tool_result is a 400.
    """
    if not messages:
        raise NotePlacementError("a system message cannot be the first message")
    last = messages[-1]
    blocks = last["content"] if isinstance(last["content"], list) else []
    if last["role"] != "user" or any(b.get("type") == "tool_result" for b in blocks):
        raise NotePlacementError(
            "add operator notes after a plain user turn, e.g. right after a ticket is announced"
        )
    messages.append({"role": "system", "content": f"Operator note: {note}"})


def first_difference(before: str, after: str) -> int | None:
    """Where `after` stops extending `before`: the first changed character, or None
    when `after` only appends to it (the cache can read all of `before`).

    Render two consecutive requests with copilot.model.render_request and pass them
    in: everything from the returned position on was written to the cache again.
    """
    for i, (a, b) in enumerate(zip(before, after, strict=False)):
        if a != b:
            return i
    return None if len(after) >= len(before) else len(after)
