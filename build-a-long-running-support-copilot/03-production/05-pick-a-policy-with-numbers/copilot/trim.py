"""Trim a tool result at the boundary: once, when it is added, never later.

A trimmed result is part of the conversation from the start, so the cached prefix
never has to change for it. Each tool gets a trimmer that keeps what the copilot
acts on and drops the bulk (audit trails, account metadata, full article bodies).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any


def _ticket(data: dict[str, Any]) -> dict[str, Any]:
    t = data["ticket"]
    return {
        "ticket": {
            "id": t["id"],
            "subject": t["subject"],
            "kind": t["kind"],
            "customer_name": t["customer_name"],
            "refund_amount": t["refund_amount"],
            "messages": [m["body"] for m in t["messages"]],
        }
    }


def _kb(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "articles": [
            {"id": a["id"], "title": a["title"], "summary": a["body"].split(". ")[0] + "."}
            for a in data["articles"]
        ]
    }


TRIMMERS: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
    "get_ticket": _ticket,
    "search_kb": _kb,
}


def trim_result(tool: str, text: str) -> str:
    """The trimmed result, or the original when there is no trimmer or it isn't JSON."""
    trimmer = TRIMMERS.get(tool)
    if trimmer is None:
        return text
    try:
        return json.dumps(trimmer(json.loads(text)))
    except (ValueError, KeyError):
        return text
