"""What one full eval run costs: the drafter over the golden set plus the gate's judge.

uv run python cost_report.py
"""

from __future__ import annotations

import json
from pathlib import Path

from evals.data import load_golden, load_kb
from evals.gate import load_thresholds, run_gate
from evals.models import ReplayModel
from evals.runner import read_jsonl, summary

HERE = Path(__file__).resolve().parent


def main() -> None:
    rows = read_jsonl(HERE / "runs/drafts-v2.jsonl")
    config = load_thresholds(HERE / "gate.json")
    judge_model = ReplayModel(config["judge_model"], HERE / "runs/calls.jsonl")
    result = run_gate(rows, {c.id: c for c in load_golden()}, load_kb(), judge_model, config)
    drafting = summary(rows)
    report = {
        "cases": len(rows),
        "drafter": {
            "model": rows[0]["model"],
            "usage": drafting["usage"],
            "cost_usd": drafting["cost_usd"],
        },
        "judge": {
            "model": config["judge_model"],
            "usage": vars(result.judge_usage),
            "cost_usd": round(result.judge_cost_usd, 4),
        },
    }
    report["total_usd"] = round(drafting["cost_usd"] + result.judge_cost_usd, 4)
    report["per_case_usd"] = round(report["total_usd"] / len(rows), 5)
    (HERE / "runs/cost-report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
