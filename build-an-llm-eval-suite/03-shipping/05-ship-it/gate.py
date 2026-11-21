"""Run the regression gate on a recorded candidate run.

uv run python gate.py runs/drafts-v2.jsonl          # exit 0 pass, 1 fail, 2 error
"""

from __future__ import annotations

import sys
from pathlib import Path

from evals.data import load_golden, load_kb
from evals.gate import format_result, load_thresholds, run_gate
from evals.models import ReplayModel
from evals.runner import read_jsonl

HERE = Path(__file__).resolve().parent


def main(argv: list[str]) -> int:
    rows = read_jsonl(Path(argv[1]) if len(argv) > 1 else HERE / "runs" / "drafts-v2.jsonl")
    config = load_thresholds(HERE / "gate.json")
    judge_model = ReplayModel(config["judge_model"], HERE / "runs" / "calls.jsonl")
    cases = {c.id: c for c in load_golden()}
    result = run_gate(rows, cases, load_kb(), judge_model, config)
    print(format_result(result))
    return result.exit_code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
