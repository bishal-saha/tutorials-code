"""Seed a regression: the recorded v2 run, as if an edit had dropped escalation rules 1 and 2.

Security and refund/credit tickets stop escalating. The reply text is unchanged, so
the recorded judgements still apply and the gate can run without the API.

    uv run python scripts/simulate_regression.py
    uv run python gate.py runs/drafts-regressed.jsonl
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

RUNS = Path(__file__).resolve().parent.parent / "runs"
DROPPED = {"security", "promise_bait"}


def regress(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        r = copy.deepcopy(r)
        if r["category"] in DROPPED and r["draft"] is not None:
            r["draft"]["escalate"] = False
        out.append(r)
    return out


if __name__ == "__main__":
    rows = [json.loads(x) for x in (RUNS / "drafts-v2.jsonl").read_text().splitlines()]
    regressed = regress(rows)
    (RUNS / "drafts-regressed.jsonl").write_text("".join(json.dumps(r) + "\n" for r in regressed))
    changed = sum(a["draft"] != b["draft"] for a, b in zip(rows, regressed, strict=True))
    print(f"wrote runs/drafts-regressed.jsonl ({changed} drafts changed)")
