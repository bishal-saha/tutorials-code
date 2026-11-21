"""Ask a judge about one labelled reply, replaying the recorded calls (no key).

uv run python judge_one.py L57 --model claude-sonnet-5-5 --criterion v1
"""

from __future__ import annotations

import argparse
from pathlib import Path

from evals.calibration import load_labels
from evals.data import load_golden, load_kb
from evals.judge import CRITERIA, JUDGES, judge
from evals.metrics import majority
from evals.models import ReplayModel

RUNS = Path(__file__).resolve().parent / "runs"


def main(argv: list[str] | None = None) -> str:
    p = argparse.ArgumentParser()
    p.add_argument("label_id")
    p.add_argument("--model", default="claude-haiku-5-5", choices=JUDGES)
    p.add_argument("--criterion", default="v2", choices=sorted(CRITERIA))
    args = p.parse_args(argv)

    item = next(x for x in load_labels() if x["id"] == args.label_id)
    case = {c.id: c for c in load_golden()}[item["case_id"]]
    model = ReplayModel(args.model, RUNS / "calls.jsonl")
    verdicts = [
        judge(model, case.ticket_text(), item["reply"], load_kb(), args.criterion, r)[0]
        for r in range(3)
    ]
    out = (
        f"{item['id']} ({case.id}: {case.subject})\n"
        f"reply: {item['reply']}\n"
        f"label {item['label']}; {args.model}, criterion {args.criterion}: "
        f"{verdicts} -> {majority([v or 'FAIL' for v in verdicts])}"
    )
    print(out)
    return out


if __name__ == "__main__":
    main()
