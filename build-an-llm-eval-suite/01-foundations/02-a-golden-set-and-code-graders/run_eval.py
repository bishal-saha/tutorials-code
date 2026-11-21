"""Draft a reply for every golden case and grade it.

uv run python run_eval.py                       # replay the recorded run (no key)
uv run python run_eval.py --live --record       # call Claude and record every call
"""

from __future__ import annotations

import argparse
from pathlib import Path

from evals.data import load_golden, load_kb
from evals.drafter import GENERATOR, PROMPTS
from evals.models import AnthropicModel, RecordingModel, ReplayModel
from evals.runner import print_summary, run_drafts, summary, write_jsonl

RUNS = Path(__file__).resolve().parent / "runs"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--prompt", default="v1", choices=sorted(PROMPTS))
    p.add_argument("--live", action="store_true", help="call the API (needs ANTHROPIC_API_KEY)")
    p.add_argument("--record", action="store_true", help="append live calls to runs/calls.jsonl")
    args = p.parse_args()

    kb, cases = load_kb(), load_golden()
    if args.live:
        model = AnthropicModel(GENERATOR, effort="low")
        if args.record:
            model = RecordingModel(model, RUNS / "calls.jsonl")
    else:
        model = ReplayModel(GENERATOR, RUNS / "calls.jsonl")

    rows = run_drafts(model, cases, kb, args.prompt, workers=8 if args.live else 1)
    write_jsonl(RUNS / f"drafts-{args.prompt}.jsonl", rows)
    print_summary(summary(rows))
    for r in rows:
        if not r["passed"]:
            print(f"  FAIL {r['case_id']} ({r['category']}): {r['details']}")


if __name__ == "__main__":
    main()
