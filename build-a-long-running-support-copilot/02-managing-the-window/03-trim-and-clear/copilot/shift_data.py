"""The shift: 24 synthetic Helpline tickets and two standing instructions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "shift.json"
SHIFT: dict[str, Any] = json.loads(DATA_FILE.read_text())

SHIFT_CODE: str = SHIFT["shift_code"]
STANDING_INSTRUCTIONS: list[str] = SHIFT["standing_instructions"]
TICKETS: list[dict[str, Any]] = SHIFT["tickets"]
ARTICLES: dict[str, dict[str, Any]] = {a["id"]: a for a in SHIFT["articles"]}
BY_ID: dict[str, dict[str, Any]] = {t["id"]: t for t in TICKETS}

INSTRUCTIONS_BLOCK = "Standing instructions for this shift:\n" + "\n".join(
    f"{i}. {s}" for i, s in enumerate(STANDING_INSTRUCTIONS, start=1)
)

OPENING = (
    "You are starting a support shift. I will give you tickets one at a time.\n"
    f"{INSTRUCTIONS_BLOCK}\n"
    "For each ticket: read it, check the knowledge base, issue a refund or hand the ticket "
    "to a person when it asks for money back, then draft a reply."
)


def announce(ticket_id: str) -> str:
    return f"Next ticket: {ticket_id}."


def opening_for(ticket_id: str) -> str:
    return f"{OPENING}\n\n{announce(ticket_id)}"
