"""Online: sample production traces for a person to review, and turn reviews into golden cases.

In production there is no expected answer, so only reference-free checks run on
every trace (the draft parses; its numbers appear in the articles it cites). The
review queue takes every trace that a check flagged, every escalation, every
thumbs-down, and a small random share of the rest, so the queue also sees
failures no check knows about yet.
"""

from __future__ import annotations

import random

from evals.data import Article, Case
from evals.graders import numbers_supported, schema_valid


def online_checks(trace: dict, kb: dict[str, Article]) -> list[str]:
    """Names of the reference-free checks this trace fails."""
    case = Case(
        trace["trace_id"], "production", trace["plan"], trace["subject"], trace["body"], False, ()
    )
    failed = []
    for check in (schema_valid, numbers_supported):
        if not check(case, trace["draft"], kb).passed:
            failed.append(check.__name__)
    return failed


def sample_for_review(
    traces: list[dict], kb: dict[str, Article], rate: float = 0.1, seed: int = 0
) -> list[dict]:
    rng = random.Random(seed)
    queue = []
    for t in traces:
        failed = online_checks(t, kb)
        if failed:
            reason = "check failed: " + ", ".join(failed)
        elif (t["draft"] or {}).get("escalate"):
            reason = "escalated"
        elif t.get("feedback") == "down":
            reason = "thumbs down"
        elif rng.random() < rate:
            reason = "random sample"
        else:
            continue
        queue.append({**t, "reason": reason})
    return queue


def to_golden_case(trace: dict, review: dict, existing_ids: list[str]) -> dict:
    """A reviewed trace becomes a golden case with the expected values the reviewer set."""
    next_id = f"G{max(int(i[1:]) for i in existing_ids) + 1:02d}"
    return {
        "id": next_id,
        "category": review["category"],
        "plan": trace["plan"],
        "subject": trace["subject"],
        "body": trace["body"],
        "expected": {"escalate": review["escalate"], "must_cite": review["must_cite"]},
        "source": f"production trace {trace['trace_id']}",
    }
