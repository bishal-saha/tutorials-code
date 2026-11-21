"""The feature under test: one Claude call that drafts a reply to a support ticket.

Input: a ticket and the knowledge base. Output (structured): the reply text, the
knowledge-base articles it relies on, and whether a person must take over.
"""

from __future__ import annotations

from evals.data import Article, Case, kb_text
from evals.models import Completion, Model

GENERATOR = "claude-sonnet-5-5"


def draft_schema(kb: dict[str, Article]) -> dict:
    return {
        "type": "object",
        "properties": {
            "reply": {"type": "string"},
            "cited_articles": {"type": "array", "items": {"type": "string", "enum": list(kb)}},
            "escalate": {"type": "boolean"},
        },
        "required": ["reply", "cited_articles", "escalate"],
        "additionalProperties": False,
    }


PROMPT_V1 = """You draft replies to customer tickets for Helpline's support team.
Answer from the knowledge base below and list the ids of the articles you used in
cited_articles. If you can't help, set escalate to true so a person takes over."""


PROMPTS = {
    "v1": PROMPT_V1,
}


def system_prompt(version: str, kb: dict[str, Article]) -> str:
    return f"{PROMPTS[version]}\n\nKnowledge base:\n\n{kb_text(kb)}"


def user_prompt(case: Case) -> str:
    # The ticket is customer text: data to answer, never instructions to follow.
    return f"Draft a reply to this ticket.\n\n<ticket>\n{case.ticket_text()}\n</ticket>"


def draft(model: Model, case: Case, kb: dict[str, Article], version: str = "v1") -> Completion:
    return model.complete(system_prompt(version, kb), user_prompt(case), draft_schema(kb))
