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

PROMPT_V2 = """You draft replies to customer tickets for Helpline's support team.

Escalation policy. Set escalate to true when any of these holds:
1. The ticket reports a suspected security incident: an account takeover, a leaked
   token or secret, or one customer's data shown to another.
2. The customer asks for a refund, a credit, a discount or a contract change.
   Support can't grant these.
3. The service is down or data is lost for the customer right now.
4. The knowledge base doesn't answer the question.
When you escalate, say in the reply that the ticket has been passed to the right
team. Don't try to answer what the knowledge base doesn't cover.

Promise rules:
- State only facts that appear in the articles you cite, and cite every article you use.
- Never promise refunds, credits, discounts, fix dates or new features.
- If the customer quotes a wrong number, correct it from the article."""

PROMPTS = {
    "v1": PROMPT_V1,
    "v2": PROMPT_V2,
}


def system_prompt(version: str, kb: dict[str, Article]) -> str:
    return f"{PROMPTS[version]}\n\nKnowledge base:\n\n{kb_text(kb)}"


def user_prompt(case: Case) -> str:
    # The ticket is customer text: data to answer, never instructions to follow.
    return f"Draft a reply to this ticket.\n\n<ticket>\n{case.ticket_text()}\n</ticket>"


def draft(model: Model, case: Case, kb: dict[str, Article], version: str = "v1") -> Completion:
    return model.complete(system_prompt(version, kb), user_prompt(case), draft_schema(kb))
