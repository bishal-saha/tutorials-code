"""Deterministic graders: checks that need no model and never change their mind.

Each grader returns a Grade for one case. They check what code can check:
the shape of the draft, the escalation decision, the citations and the numbers.
Whether the reply actually answers the question is left to the judge (lesson 3).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from evals.data import Article, Case

NUMBER = re.compile(r"\d+(?:[.,]\d+)*")

# Digits that are not claims. Each pattern came from reading a false alarm in a real run.
NOT_CLAIMS = [
    re.compile(r"^\s*\d+[.)]\s", re.MULTILINE),  # numbered steps: "1. Go to Settings"
    re.compile(r"\bKB-\d+\b"),  # article ids: "(KB-112)"
    re.compile(  # calendar dates: "31 December 2025"
        r"\b\d{1,2} (?:January|February|March|April|May|June|July|August|September"
        r"|October|November|December)\b"
    ),
    re.compile(r"\bMicrosoft 365\b"),  # product names
    re.compile(  # US-style dates: "December 31" (found in lesson 4's v1/v2 comparison)
        r"\b(?:January|February|March|April|May|June|July|August|September"
        r"|October|November|December) \d{1,2}\b"
    ),
]


@dataclass(frozen=True)
class Grade:
    name: str
    passed: bool
    detail: str = ""


def schema_valid(case: Case, draft: dict | None, kb: dict[str, Article]) -> Grade:
    if draft is None:
        return Grade("schema_valid", False, "no draft (refusal, truncation or bad JSON)")
    ok = (
        isinstance(draft.get("reply"), str)
        and draft["reply"].strip() != ""
        and isinstance(draft.get("escalate"), bool)
        and isinstance(draft.get("cited_articles"), list)
        and all(a in kb for a in draft["cited_articles"])
    )
    return Grade("schema_valid", ok, "" if ok else "missing field or unknown article id")


def escalation_correct(case: Case, draft: dict | None, kb: dict[str, Article]) -> Grade:
    if draft is None:
        return Grade("escalation_correct", False, "no draft")
    ok = draft.get("escalate") is case.escalate
    return Grade("escalation_correct", ok, "" if ok else f"expected escalate={case.escalate}")


def cites_required(case: Case, draft: dict | None, kb: dict[str, Article]) -> Grade:
    if draft is None:
        return Grade("cites_required", False, "no draft")
    missing = sorted(set(case.must_cite) - set(draft.get("cited_articles", [])))
    return Grade("cites_required", not missing, f"missing {', '.join(missing)}" if missing else "")


def _numbers(text: str) -> set[str]:
    for pattern in NOT_CLAIMS:
        text = pattern.sub(" ", text)
    return {n.replace(",", "") for n in NUMBER.findall(text)}


def numbers_supported(case: Case, draft: dict | None, kb: dict[str, Article]) -> Grade:
    """Every number in the reply must appear in a cited article or in the ticket itself."""
    if draft is None:
        return Grade("numbers_supported", False, "no draft")
    cited = [kb[a].body for a in draft.get("cited_articles", []) if a in kb]
    sources = "\n".join([case.ticket_text(), *cited])
    unsupported = sorted(_numbers(draft.get("reply", "")) - _numbers(sources))
    return Grade(
        "numbers_supported",
        not unsupported,
        f"not in cited articles: {', '.join(unsupported)}" if unsupported else "",
    )


GRADERS = [schema_valid, escalation_correct, cites_required, numbers_supported]


def grade_all(case: Case, draft: dict | None, kb: dict[str, Article]) -> list[Grade]:
    return [g(case, draft, kb) for g in GRADERS]
