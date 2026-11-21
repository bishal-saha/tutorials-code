"""Read five drafts like a reviewer would, then check all forty against what was expected.

The drafts are a recorded run of the Helpline reply drafter (claude-sonnet-5-5,
prompt v1, 2026-11-21), replayed from runs/drafts-v1.jsonl. No API key needed.

    uv run python read_five.py
"""

from __future__ import annotations

import json
import random
from math import comb
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load() -> tuple[list[dict], dict[str, dict]]:
    drafts = [json.loads(x) for x in (HERE / "runs/drafts-v1.jsonl").read_text().splitlines()]
    golden = {c["id"]: c for c in json.loads((HERE / "data/golden.json").read_text())["cases"]}
    return drafts, golden


def sample(drafts: list[dict], n: int = 5, seed: int = 1) -> list[dict]:
    return random.Random(seed).sample(drafts, n)


def escalation_misses(drafts: list[dict], golden: dict[str, dict]) -> list[str]:
    """Cases where the draft's escalate flag differs from the expected one."""
    return [
        d["case_id"]
        for d in drafts
        if d["draft"]["escalate"] != golden[d["case_id"]]["expected"]["escalate"]
    ]


def chance_to_see(failures: int, total: int, read: int) -> float:
    """Probability that `read` drafts picked at random include at least one failure."""
    return 1 - comb(total - failures, read) / comb(total, read)


def main() -> None:
    drafts, golden = load()
    print("Five drafts, picked at random:\n")
    for d in sample(drafts):
        case = golden[d["case_id"]]
        print(f"[{d['case_id']}] {case['subject']}")
        print(f"  escalate={d['draft']['escalate']}  cites={d['draft']['cited_articles']}")
        print("  " + d["draft"]["reply"][:160].replace("\n", " ") + "...\n")

    misses = escalation_misses(drafts, golden)
    print(f"Checked against the expected escalation for all {len(drafts)} cases: {misses}")
    p = chance_to_see(len(misses), len(drafts), 5)
    print(f"Chance that reading 5 random drafts shows any of them: {p:.1%}")


if __name__ == "__main__":
    main()
