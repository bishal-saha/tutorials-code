"""An LLM judge for the one thing code can't check: does the reply do its job?

One criterion, a PASS/FAIL verdict, structured output. The knowledge base and
the criterion sit in a cached system prompt; the ticket and reply are the user turn.
"""

from __future__ import annotations

from evals.data import Article, kb_text
from evals.models import Completion, Model

JUDGES = ["claude-haiku-5-5", "claude-sonnet-5-5"]

CRITERIA = {
    # The first wording: "answers the question" is ambiguous for escalated tickets.
    "v1": (
        "The reply answers the question the ticket asked, and promises nothing "
        "the knowledge base doesn't support."
    ),
    # Sharpened after reading the judge's disagreements with the labels.
    "v2": (
        "The reply answers the question the ticket asked, and promises nothing "
        "the knowledge base doesn't support. A reply that says the ticket has been "
        "passed to another team passes without answering the question itself, "
        "as long as it doesn't attempt an answer the knowledge base doesn't support."
    ),
}

VERDICT_SCHEMA = {
    "type": "object",
    "properties": {"verdict": {"type": "string", "enum": ["PASS", "FAIL"]}},
    "required": ["verdict"],
    "additionalProperties": False,
}


def judge_system(criterion: str, kb: dict[str, Article]) -> str:
    return (
        "You grade draft replies written by Helpline's support assistant.\n\n"
        f"Criterion: {CRITERIA[criterion]}\n"
        "Answer PASS if the reply meets the criterion, FAIL if it doesn't.\n\n"
        f"Knowledge base:\n\n{kb_text(kb)}"
    )


def judge_user(ticket: str, reply: str) -> str:
    return f"<ticket>\n{ticket}\n</ticket>\n\n<reply>\n{reply}\n</reply>"


def judge(
    model: Model,
    ticket: str,
    reply: str,
    kb: dict[str, Article],
    criterion: str = "v2",
    repeat: int = 0,
) -> tuple[str | None, Completion]:
    """Return ("PASS" | "FAIL" | None, the completion). None means no usable verdict."""
    c = model.complete(
        judge_system(criterion, kb),
        judge_user(ticket, reply),
        VERDICT_SCHEMA,
        tag=f"repeat={repeat}",
    )
    # Structured output doesn't guarantee an enum's capitalization: compare case-insensitively.
    verdict = str((c.value or {}).get("verdict", "")).upper()
    return (verdict if verdict in ("PASS", "FAIL") else None), c
