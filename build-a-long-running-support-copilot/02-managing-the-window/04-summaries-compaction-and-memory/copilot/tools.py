"""The copilot's tools, over the synthetic shift data.

get_ticket returns what a real ticketing API tends to return: the fields you need
plus a lot you don't (audit fields, SLA metadata, the customer record). That bulk
is what fills the window over a shift.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from copilot.shift_data import ARTICLES, BY_ID

TOOLS: list[dict[str, Any]] = [
    {
        "name": "get_ticket",
        "description": "Read a ticket: customer, request type, messages and account details.",
        "input_schema": {
            "type": "object",
            "properties": {"ticket_id": {"type": "string", "description": "e.g. HL-2003"}},
            "required": ["ticket_id"],
        },
    },
    {
        "name": "search_kb",
        "description": "Search the knowledge base. Returns matching articles with their full text.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "issue_refund",
        "description": "Refund the customer the amount they asked for on this ticket.",
        "input_schema": {
            "type": "object",
            "properties": {"ticket_id": {"type": "string"}, "amount": {"type": "number"}},
            "required": ["ticket_id", "amount"],
        },
    },
    {
        "name": "hand_to_person",
        "description": "Hand a ticket to a human agent instead of acting on it.",
        "input_schema": {
            "type": "object",
            "properties": {"ticket_id": {"type": "string"}, "reason": {"type": "string"}},
            "required": ["ticket_id", "reason"],
        },
    },
    {
        "name": "draft_reply",
        "description": "Save a draft reply to the customer for review.",
        "input_schema": {
            "type": "object",
            "properties": {"ticket_id": {"type": "string"}, "message": {"type": "string"}},
            "required": ["ticket_id", "message"],
        },
    },
]


def ticket_payload(ticket_id: str) -> dict[str, Any]:
    """The full API response for a ticket, bulk included."""
    t = BY_ID[ticket_id]
    return {
        "ticket": {
            "id": t["id"],
            "subject": t["subject"],
            "kind": t["kind"],
            "customer_name": t["customer_name"],
            "refund_amount": t["refund_amount"],
            "status": "open",
            "priority": "normal",
            "channel": "email",
            "sla": {"first_response_due": "2026-11-21T12:00:00Z", "breached": False},
            "tags": ["billing" if t["kind"] == "refund" else "product", t["customer"]],
            "messages": t["messages"],
        },
        "customer": {
            "id": t["customer"],
            "name": t["customer_name"],
            "plan": t["plan"],
            "seats": 40,
            "billing_contact": "billing@" + t["customer"] + ".example",
            "created_at": "2024-03-02T10:00:00Z",
            "health_score": 0.82,
            "notes": "Synthetic account. " * 6,
        },
        "audit": [
            {"at": m["at"], "event": "message_received", "actor": "customer", "via": "email"}
            for m in t["messages"]
        ]
        * 3,
    }


@dataclass
class ShiftTools:
    """Runs tool calls and records what the copilot did.

    `memory` is the SDK's file-backed memory tool (anthropic.tools.memory), or None.
    """

    memory: Any = None
    refunds: dict[str, float] = field(default_factory=dict)
    handoffs: dict[str, str] = field(default_factory=dict)
    drafts: dict[str, str] = field(default_factory=dict)

    def run(self, name: str, args: dict[str, Any]) -> str:
        if name == "memory" and self.memory is not None:
            try:
                return str(self.memory.call(args))
            except Exception as exc:  # the SDK raises ToolError for bad paths and commands
                return f"Error: {exc}"
        if name == "get_ticket":
            tid = args["ticket_id"].upper()
            if tid not in BY_ID:
                return f"No ticket {tid}."
            return json.dumps(ticket_payload(tid))
        if name == "search_kb":
            words = set(args["query"].lower().split())
            hits = sorted(
                ARTICLES.values(),
                key=lambda a: -len(words & set((a["title"] + " " + a["body"]).lower().split())),
            )[:3]
            return json.dumps({"articles": hits})
        if name == "issue_refund":
            self.refunds[args["ticket_id"]] = float(args["amount"])
            return json.dumps({"refunded": args["amount"], "ticket_id": args["ticket_id"]})
        if name == "hand_to_person":
            self.handoffs[args["ticket_id"]] = args["reason"]
            return json.dumps({"handed_to": "billing team", "ticket_id": args["ticket_id"]})
        if name == "draft_reply":
            self.drafts[args["ticket_id"]] = args["message"]
            return json.dumps({"saved": True, "ticket_id": args["ticket_id"]})
        return f"Unknown tool {name}."
