"""Compare two versions of the feature on the same cases without fooling yourself.

- paired(): the four-way split of cases, because only the cases that changed carry signal
- bootstrap_diff(): a confidence interval for the change in pass rate, resampling cases
- cases_needed(): a rough size for a golden set that can see a given change
- corrected_delta(): undo the shrinkage an imperfect judge applies to every change
- pairwise judging with an A/B swap, to expose position bias
"""

from __future__ import annotations

import math
import random

from evals.data import Article, kb_text
from evals.models import Model


def paired(a: dict[str, bool], b: dict[str, bool]) -> dict[str, list[str]]:
    """Split case ids by (passed under A, passed under B)."""
    out: dict[str, list[str]] = {"both_pass": [], "a_only": [], "b_only": [], "both_fail": []}
    for case_id in sorted(a):
        key = {
            (True, True): "both_pass",
            (True, False): "a_only",
            (False, True): "b_only",
            (False, False): "both_fail",
        }[(a[case_id], b[case_id])]
        out[key].append(case_id)
    return out


def bootstrap_diff(
    a: list[bool], b: list[bool], reps: int = 10_000, seed: int = 0
) -> tuple[float, float, float]:
    """Pass rate of B minus A, with a 95% percentile interval from resampling cases (pairs kept)."""
    n = len(a)
    rng = random.Random(seed)
    diff = (sum(b) - sum(a)) / n
    draws = []
    for _ in range(reps):
        idx = [rng.randrange(n) for _ in range(n)]
        draws.append(sum(b[i] - a[i] for i in idx) / n)
    draws.sort()
    return diff, draws[int(0.025 * reps)], draws[int(0.975 * reps) - 1]


def cases_needed(delta: float, discordant: float, z: float = 1.96, z_power: float = 0.84) -> int:
    """Cases for a paired comparison to detect a change of `delta` (95% confidence, 80% power).

    `discordant` is the share of cases whose result differs between versions. This is the
    usual normal approximation for McNemar's test (Connor, 1987).
    """
    top = z * math.sqrt(discordant) + z_power * math.sqrt(discordant - delta * delta)
    return math.ceil((top / delta) ** 2)


def corrected_delta(measured: float, youden: float) -> float:
    """A judge with TPR + TNR - 1 = youden reports youden x the real change in failure rate."""
    return measured / youden


PAIR_SCHEMA = {
    "type": "object",
    "properties": {"better": {"type": "string", "enum": ["A", "B"]}},
    "required": ["better"],
    "additionalProperties": False,
}


def pair_system(kb: dict[str, Article]) -> str:
    return (
        "You compare two draft replies to the same Helpline support ticket.\n"
        "Pick the reply that better answers the question the ticket asked while promising "
        "nothing the knowledge base doesn't support. A reply that says the ticket was passed "
        "to another team can be the better one.\n\n"
        f"Knowledge base:\n\n{kb_text(kb)}"
    )


def pair_user(ticket: str, reply_a: str, reply_b: str) -> str:
    return (
        f"<ticket>\n{ticket}\n</ticket>\n\n"
        f"<reply_a>\n{reply_a}\n</reply_a>\n\n<reply_b>\n{reply_b}\n</reply_b>"
    )


def pair_judge(
    model: Model, ticket: str, reply_a: str, reply_b: str, kb: dict[str, Article]
) -> str | None:
    c = model.complete(pair_system(kb), pair_user(ticket, reply_a, reply_b), PAIR_SCHEMA)
    better = str((c.value or {}).get("better", "")).upper()
    return better if better in ("A", "B") else None


def swap_test(
    model: Model, ticket: str, first: str, second: str, kb: dict[str, Article]
) -> dict[str, object]:
    """Judge (first, second) and then (second, first); report which reply won each time."""
    ab = pair_judge(model, ticket, first, second, kb)
    ba = pair_judge(model, ticket, second, first, kb)
    win_ab = {"A": "first", "B": "second"}.get(ab or "")
    win_ba = {"A": "second", "B": "first"}.get(ba or "")
    return {
        "order_1": win_ab,
        "order_2": win_ba,
        "consistent": win_ab is not None and win_ab == win_ba,
        "position_a_won_both": ab == "A" and ba == "A",
    }
