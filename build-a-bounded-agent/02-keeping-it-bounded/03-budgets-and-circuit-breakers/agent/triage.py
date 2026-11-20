"""The Helpline triage task: what the agent is asked to do."""

from __future__ import annotations

SYSTEM = """You are Helpline's triage assistant. You help a support engineer with one ticket.
Use the tools to read the ticket, look for similar tickets and knowledge-base articles,
and save a draft reply with draft_reply. A person reviews and sends every draft.
Do not call escalate_ticket. If the ticket needs escalation, say so in your final answer.
Finish with a short summary: what you found, the draft id, and whether to escalate."""


def task_for(ticket_id: str) -> str:
    return f"Triage ticket {ticket_id}."
