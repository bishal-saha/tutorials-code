"""Pick production traces for review and write runs/review-queue.jsonl.

uv run python sample_traces.py
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from evals.data import load_kb
from evals.sampling import sample_for_review

HERE = Path(__file__).resolve().parent


def main() -> None:
    lines = (HERE / "data/production-traces.jsonl").read_text().splitlines()
    traces = [json.loads(x) for x in lines]
    queue = sample_for_review(traces, load_kb(), rate=0.1, seed=0)
    (HERE / "runs/review-queue.jsonl").write_text("".join(json.dumps(t) + "\n" for t in queue))
    print(f"{len(queue)} of {len(traces)} traces queued for review")
    for reason, n in Counter(t["reason"] for t in queue).most_common():
        print(f"  {n:>3}  {reason}")


if __name__ == "__main__":
    main()
